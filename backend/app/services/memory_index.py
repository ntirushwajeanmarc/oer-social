from __future__ import annotations

import logging

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.models import AdminMemoryChunk, AdminMemoryConversation
from app.services.embeddings import chunk_text, embed_texts

logger = logging.getLogger("oer.memory_index")


async def index_conversation(
    db: AsyncSession,
    conversation: AdminMemoryConversation,
    *,
    force: bool = False,
) -> int:
    """Chunk + embed one imported conversation. Returns chunks written."""
    if not settings.memory_embed_enabled:
        return 0

    existing = await db.scalar(
        select(AdminMemoryChunk.id)
        .where(AdminMemoryChunk.conversation_id == conversation.id)
        .limit(1)
    )
    if existing and not force:
        return 0

    await db.execute(
        delete(AdminMemoryChunk).where(
            AdminMemoryChunk.conversation_id == conversation.id
        )
    )

    pieces = chunk_text(
        conversation.user_text or "",
        title=conversation.title or "",
        chunk_chars=settings.memory_embed_chunk_chars,
        max_chunks=settings.memory_embed_max_chunks_per_conversation,
    )
    if not pieces:
        return 0

    try:
        vectors = await embed_texts(pieces)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Embedding failed for conversation %s (%s): %s",
            conversation.id,
            conversation.title,
            exc,
        )
        return 0

    if len(vectors) != len(pieces):
        logger.warning(
            "Embedding count mismatch for %s: texts=%s vectors=%s",
            conversation.id,
            len(pieces),
            len(vectors),
        )
        return 0

    for idx, (content, vector) in enumerate(zip(pieces, vectors, strict=True)):
        db.add(
            AdminMemoryChunk(
                conversation_id=conversation.id,
                admin_id=conversation.admin_id,
                chunk_index=idx,
                content=content,
                embedding=vector,
            )
        )
    await db.flush()
    return len(pieces)


async def backfill_memory_embeddings(
    *,
    batch_conversations: int = 8,
    max_conversations: int | None = None,
) -> dict[str, int]:
    """Embed imported conversations that do not yet have chunks."""
    if not settings.memory_embed_enabled:
        return {"indexed": 0, "chunks": 0, "skipped": 0}

    indexed = 0
    chunks = 0
    skipped = 0
    processed = 0

    async with SessionLocal() as db:
        # Conversations with no chunks yet
        statement = text(
            """
            SELECT c.id
            FROM admin_memory_conversations c
            LEFT JOIN admin_memory_chunks ch ON ch.conversation_id = c.id
            WHERE ch.id IS NULL
            ORDER BY c.conversation_updated_at DESC NULLS LAST, c.imported_at DESC
            LIMIT :limit
            """
        )
        limit = max_conversations or 10_000
        result = await db.execute(statement, {"limit": limit})
        pending_ids = [str(r[0]) for r in result.all()]

    for i in range(0, len(pending_ids), batch_conversations):
        batch_ids = pending_ids[i : i + batch_conversations]
        async with SessionLocal() as db:
            rows = list(
                (
                    await db.execute(
                        select(AdminMemoryConversation).where(
                            AdminMemoryConversation.id.in_(batch_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for conv in rows:
                written = await index_conversation(db, conv, force=False)
                processed += 1
                if written:
                    indexed += 1
                    chunks += written
                else:
                    skipped += 1
            await db.commit()
        logger.info(
            "Memory embed progress: processed=%s indexed=%s chunks=%s",
            processed,
            indexed,
            chunks,
        )

    return {"indexed": indexed, "chunks": chunks, "skipped": skipped, "pending": len(pending_ids)}


async def vector_search_chunks(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    query_embedding: list[float],
    limit: int = 8,
) -> list[tuple[str, str, str, float]]:
    """Return (conversation_id, title, chunk_content, distance) by cosine distance."""
    if not query_embedding or not admin_ids:
        return []

    # pgvector cosine distance: smaller is closer
    statement = text(
        """
        SELECT ch.conversation_id::text,
               coalesce(c.title, '') AS title,
               ch.content,
               (ch.embedding <=> CAST(:embedding AS vector)) AS distance
        FROM admin_memory_chunks ch
        JOIN admin_memory_conversations c ON c.id = ch.conversation_id
        WHERE ch.admin_id IN :admin_ids
          AND ch.embedding IS NOT NULL
        ORDER BY ch.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))

    emb = "[" + ",".join(f"{x:.8f}" for x in query_embedding) + "]"
    try:
        result = await db.execute(
            statement,
            {"admin_ids": admin_ids, "embedding": emb, "limit": limit},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector search failed: %s", exc)
        return []

    return [
        (str(r[0]), r[1] or "", r[2] or "", float(r[3] if r[3] is not None else 1.0))
        for r in result.all()
    ]
