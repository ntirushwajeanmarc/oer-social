from __future__ import annotations

import logging
import re

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
            raw = item.embedding
            if isinstance(raw, str):
                # Some proxies return a JSON string; parse if possible.
                import json

                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("Embedding API returned a non-numeric vector") from exc
            vec = [float(x) for x in list(raw)]
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
