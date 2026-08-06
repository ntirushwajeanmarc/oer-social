from __future__ import annotations

import argparse
import asyncio
import json
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import Base, SessionLocal, engine
from app.models import AdminMemoryConversation, User


def recover_complete_entries(path: Path) -> Iterator[tuple[str, bytes]]:
    """Read complete local ZIP entries even when the central directory is missing."""
    data = path.read_bytes()
    position = 0
    while position + 30 <= len(data) and data[position : position + 4] == b"PK\x03\x04":
        (
            _signature,
            _version,
            flags,
            method,
            _mtime,
            _mdate,
            _crc,
            compressed_size,
            _uncompressed_size,
            name_length,
            extra_length,
        ) = struct.unpack_from("<IHHHHHIIIHH", data, position)
        if flags & 0x08:
            raise RuntimeError(
                "Archive uses ZIP data descriptors; re-download a complete export before importing."
            )

        name_start = position + 30
        name = data[name_start : name_start + name_length].decode("utf-8", "replace")
        payload_start = name_start + name_length + extra_length
        payload_end = payload_start + compressed_size
        if payload_end > len(data):
            print(f"Skipping truncated entry: {name}")
            break

        compressed = data[payload_start:payload_end]
        if method == 0:
            raw = compressed
        elif method == 8:
            raw = zlib.decompress(compressed, -15)
        else:
            print(f"Skipping unsupported compression method {method}: {name}")
            raw = b""

        if raw:
            yield name, raw
        position = payload_end


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    values: list[str] = []
    for part in parts:
        if isinstance(part, str):
            value = part.strip()
            if value:
                values.append(value)
    return "\n".join(values)


def user_transcript(conversation: dict[str, Any]) -> str:
    messages: list[tuple[float, str]] = []
    for node in (conversation.get("mapping") or {}).values():
        message = node.get("message") or {}
        if (message.get("author") or {}).get("role") != "user":
            continue
        metadata = message.get("metadata") or {}
        if metadata.get("is_visually_hidden_from_conversation"):
            continue
        text = message_text(message)
        if not text:
            continue
        created = message.get("create_time")
        try:
            timestamp = float(created or 0)
        except (TypeError, ValueError):
            timestamp = 0
        messages.append((timestamp, text))
    messages.sort(key=lambda item: item[0])
    return "\n\n".join(text for _, text in messages)[:200_000]


def to_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC) if value else None
    except (TypeError, ValueError, OSError):
        return None


async def import_archive(path: Path, admin_email: str) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        admin = await db.scalar(
            select(User).where(User.email == admin_email.lower().strip())
        )
        if not admin:
            raise RuntimeError(f"Admin account not found: {admin_email}")
        if admin.role != "admin":
            raise RuntimeError(f"Account is not an admin: {admin_email}")

        imported = 0
        skipped_private = 0
        skipped_empty = 0
        source = path.name

        for entry_name, raw in recover_complete_entries(path):
            if not entry_name.startswith("conversations-") or not entry_name.endswith(
                ".json"
            ):
                continue
            conversations = json.loads(raw)
            print(f"Reading {entry_name}: {len(conversations)} conversations")
            for conversation in conversations:
                if conversation.get("is_do_not_remember"):
                    skipped_private += 1
                    continue
                transcript = user_transcript(conversation)
                if not transcript:
                    skipped_empty += 1
                    continue
                conversation_id = str(
                    conversation.get("conversation_id")
                    or conversation.get("id")
                    or ""
                )
                if not conversation_id:
                    skipped_empty += 1
                    continue

                statement = (
                    insert(AdminMemoryConversation)
                    .values(
                        admin_id=admin.id,
                        source_conversation_id=conversation_id,
                        source_filename=source,
                        title=str(conversation.get("title") or "Untitled")[:500],
                        user_text=transcript,
                        conversation_created_at=to_datetime(
                            conversation.get("create_time")
                        ),
                        conversation_updated_at=to_datetime(
                            conversation.get("update_time")
                        ),
                    )
                    .on_conflict_do_update(
                        constraint="uq_admin_memory_source_conversation",
                        set_={
                            "source_filename": source,
                            "title": str(
                                conversation.get("title") or "Untitled"
                            )[:500],
                            "user_text": transcript,
                            "conversation_created_at": to_datetime(
                                conversation.get("create_time")
                            ),
                            "conversation_updated_at": to_datetime(
                                conversation.get("update_time")
                            ),
                            "imported_at": datetime.now(UTC),
                        },
                    )
                )
                await db.execute(statement)
                imported += 1

        await db.commit()
        print(
            f"Imported/updated {imported} conversations for {admin_email}; "
            f"skipped private={skipped_private}, empty={skipped_empty}."
        )

    # Index embeddings after import (CircuitNotion text-embedding-3-small → pgvector)
    try:
        from app.services.memory_index import backfill_memory_embeddings

        stats = await backfill_memory_embeddings(batch_conversations=6)
        print(f"Embedding backfill: {stats}")
    except Exception as exc:  # noqa: BLE001
        print(f"Embedding backfill skipped/failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import recoverable ChatGPT export conversations as admin memory."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--admin-email", required=True)
    args = parser.parse_args()
    if not args.archive.is_file():
        raise SystemExit(f"Archive not found: {args.archive}")
    asyncio.run(import_archive(args.archive, args.admin_email))


if __name__ == "__main__":
    main()
