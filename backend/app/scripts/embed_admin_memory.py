"""Backfill CircuitNotion embeddings for imported admin memory.

Usage:
  python -m app.scripts.embed_admin_memory
  python -m app.scripts.embed_admin_memory --max 50
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.services.memory_index import backfill_memory_embeddings

logging.basicConfig(level=logging.INFO)


async def run(max_conversations: int | None) -> None:
    stats = await backfill_memory_embeddings(
        batch_conversations=6,
        max_conversations=max_conversations,
    )
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed admin memory into pgvector")
    parser.add_argument("--max", type=int, default=None, help="Max conversations to index")
    args = parser.parse_args()
    asyncio.run(run(args.max))


if __name__ == "__main__":
    main()
