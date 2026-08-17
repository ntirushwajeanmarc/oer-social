from __future__ import annotations

import base64
import json
import logging
import re
import struct

from app.config import settings
from app.services.openai_service import get_client

logger = logging.getLogger("oer.embeddings")


def chunk_text(
    text: str,
    *,
    chunk_chars: int | None = None,
    max_chunks: int | None = None,
    title: str = "",
) -> list[str]:
    """Split long imported conversations into embeddable windows."""
    body = (text or "").strip()
    if not body:
        return []

    size = chunk_chars or settings.memory_embed_chunk_chars
    cap = max_chunks or settings.memory_embed_max_chunks_per_conversation
    prefix = f"{title.strip()}\n\n" if title.strip() else ""

    paragraphs = re.split(r"\n\s*\n+", body)
    chunks: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        piece = buf.strip()
        if piece:
            chunks.append((prefix + piece).strip()[: size + 400])
        buf = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > size:
            flush()
            for i in range(0, len(para), size):
                chunks.append((prefix + para[i : i + size]).strip())
                if len(chunks) >= cap:
                    return chunks[:cap]
            continue
        if buf and len(buf) + 2 + len(para) > size:
            flush()
        buf = f"{buf}\n\n{para}".strip() if buf else para

    flush()
    if not chunks:
        chunks = [(prefix + body[:size]).strip()]
    return chunks[:cap]


def coerce_embedding(raw: object) -> list[float]:
    """Normalize CircuitNotion/OpenAI embedding payloads to float32 lists.

    Some routes return a JSON array; others return a base64 float32 buffer
    (string often starts with 'A'), which must not be iterated as characters.
    """
    if raw is None:
        raise RuntimeError("Embedding API returned an empty vector")

    if isinstance(raw, dict):
        raw = raw.get("embedding") or raw.get("vector") or raw.get("data")

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise RuntimeError("Embedding API returned an empty vector")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [float(x) for x in parsed]
        if isinstance(parsed, str):
            text = parsed
        buf = base64.b64decode(text, validate=False)
        if len(buf) < 16 or len(buf) % 4:
            raise RuntimeError("Embedding API returned a non-numeric vector")
        count = len(buf) // 4
        return list(struct.unpack("<" + "f" * count, buf[: count * 4]))

    if isinstance(raw, (bytes, bytearray)):
        buf = bytes(raw)
        if len(buf) < 16 or len(buf) % 4:
            raise RuntimeError("Embedding API returned a non-numeric vector")
        count = len(buf) // 4
        return list(struct.unpack("<" + "f" * count, buf[: count * 4]))

    return [float(x) for x in list(raw)]  # type: ignore[arg-type]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Create embeddings via CircuitNotion OpenAI-compatible API."""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return []
    if not settings.memory_embed_enabled:
        return []

    client = get_client()
    model = (settings.openai_embedding_model or "text-embedding-3-small").strip()
    # Batch conservatively for long imported chats
    out: list[list[float]] = []
    batch_size = 16
    for i in range(0, len(cleaned), batch_size):
        batch = cleaned[i : i + batch_size]
        result = await client.embeddings.create(model=model, input=batch)
        # API may return out of order; sort by index
        ordered = sorted(result.data, key=lambda d: d.index)
        for item in ordered:
            vec = coerce_embedding(item.embedding)
            if settings.openai_embedding_dims and len(vec) != settings.openai_embedding_dims:
                logger.warning(
                    "Embedding dim mismatch: got %s expected %s",
                    len(vec),
                    settings.openai_embedding_dims,
                )
            out.append(vec)
    return out


async def embed_query(query: str) -> list[float] | None:
    q = " ".join((query or "").split()).strip()
    if not q:
        return None
    try:
        vectors = await embed_texts([q[:8000]])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Query embedding failed: %s", exc)
        return None
    return vectors[0] if vectors else None
