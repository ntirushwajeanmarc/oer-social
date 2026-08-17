from __future__ import annotations

import base64
import json
import logging
import re
import struct

import httpx

from app.config import settings

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
    """Normalize CircuitNotion/OpenAI embedding payloads to float32 lists."""
    if raw is None:
        raise RuntimeError("Embedding API returned an empty vector")

    if isinstance(raw, dict):
        raw = raw.get("embedding") or raw.get("vector") or raw.get("data")

    if isinstance(raw, (list, tuple)):
        if not raw:
            raise RuntimeError("Embedding API returned an empty vector")
        first = raw[0]
        if isinstance(first, (int, float)) and not isinstance(first, bool):
            return [float(x) for x in raw]
        if isinstance(first, str) and len(raw) == 1:
            return coerce_embedding(first)
        # SDK sometimes splits a base64 string into one-character items.
        if isinstance(first, str) and all(isinstance(x, str) and len(x) == 1 for x in raw[:12]):
            return coerce_embedding("".join(str(x) for x in raw))
        if isinstance(first, str):
            return coerce_embedding(first)
        return [float(x) for x in raw]

    if isinstance(raw, (bytes, bytearray)):
        return _floats_from_base64_bytes(bytes(raw))

    text = str(raw).strip()
    if not text:
        raise RuntimeError("Embedding API returned an empty vector")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None and parsed is not raw:
        if isinstance(parsed, (list, tuple, dict, str)):
            return coerce_embedding(parsed)
    return _floats_from_base64_bytes(base64.b64decode(text, validate=False))


def _floats_from_base64_bytes(buf: bytes) -> list[float]:
    if len(buf) < 16 or len(buf) % 4:
        raise RuntimeError("Embedding API returned a non-numeric vector")
    count = len(buf) // 4
    return list(struct.unpack("<" + "f" * count, buf[: count * 4]))


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Create embeddings via CircuitNotion OpenAI-compatible API."""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return []
    if not settings.memory_embed_enabled:
        return []

    api_key = (settings.circuitnotion_api_key or settings.openai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("CIRCUITNOTION_API_KEY is not set")
    model = (settings.openai_embedding_model or "text-embedding-3-small").strip()
    url = f"{settings.openai_base_url.rstrip('/')}/embeddings"

    out: list[list[float]] = []
    batch_size = 8
    async with httpx.AsyncClient(timeout=120.0) as http:
        for i in range(0, len(cleaned), batch_size):
            batch = cleaned[i : i + batch_size]
            res = await http.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": batch,
                    "encoding_format": "float",
                },
            )
            if res.status_code >= 400:
                raise RuntimeError(
                    f"Embedding API failed: {res.status_code} {res.text[:500]}"
                )
            payload = res.json()
            rows = payload.get("data") or []
            ordered = sorted(rows, key=lambda d: int(d.get("index", 0)))
            for item in ordered:
                vec = coerce_embedding(item.get("embedding"))
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
