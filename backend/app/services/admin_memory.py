from __future__ import annotations

import re

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContentPack

_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "then",
    "so",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "about",
    "into",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "as",
    "at",
    "by",
    "we",
    "you",
    "i",
    "me",
    "my",
    "our",
    "your",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "why",
    "can",
    "could",
    "would",
    "should",
    "please",
    "help",
    "make",
    "need",
    "want",
    "just",
    "also",
    "very",
    "more",
    "some",
    "any",
    "not",
    "do",
    "does",
    "did",
    "done",
    "have",
    "has",
    "had",
    "will",
    "shall",
    "than",
    "too",
    "here",
    "there",
}


def significant_tokens(query: str, *, min_len: int = 3, limit: int = 12) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{1,}", query or "")
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw:
        low = tok.lower()
        if len(low) < min_len or low in _STOP or low in seen:
            continue
        seen.add(low)
        out.append(tok)
        if len(out) >= limit:
            break
    return out


def _or_tsquery(tokens: list[str]) -> str:
    parts: list[str] = []
    for tok in tokens[:10]:
        cleaned = re.sub(r"[^A-Za-z0-9\-]", "", tok)
        if len(cleaned) < 3:
            continue
        parts.append(f"{cleaned}:*")
    return " | ".join(parts)


def _window_snippet(text_body: str, tokens: list[str], *, max_chars: int = 1600) -> str:
    body = (text_body or "").strip()
    if not body:
        return ""
    if len(body) <= max_chars:
        return body
    lower = body.lower()
    best = 0
    for tok in tokens:
        idx = lower.find(tok.lower())
        if idx >= 0:
            best = max(0, idx - max_chars // 3)
            break
    snippet = body[best : best + max_chars].strip()
    if best > 0:
        snippet = "…" + snippet
    if best + max_chars < len(body):
        snippet = snippet + "…"
    return snippet


async def _org_admin_ids(db: AsyncSession, admin_id: str) -> list[str]:
    """Include sibling admin accounts so ZIP memory stays available after re-bootstrap."""
    result = await db.execute(
        text(
            """
            SELECT id::text
            FROM users
            WHERE role = 'admin'
            """
        )
    )
    ids = [str(r[0]) for r in result.all()]
    if admin_id not in ids:
        ids.append(admin_id)
    return ids or [admin_id]


async def retrieve_admin_memory(
    db: AsyncSession,
    *,
    admin_id: str,
    query: str,
    limit: int | None = None,
    max_chars: int | None = None,
    profile: str = "pack",
    exclude_chat_id: str | None = None,
) -> str:
    """Retrieve ChatGPT-imported history, platform packs, and prior workspace chats.

    profile:
      - pack: tighter budget for content-pack generation
      - chat: larger budget + cross-chat recall for the admin workspace
    """
    if profile == "chat":
        conv_limit = limit if limit is not None else 8
        char_budget = max_chars if max_chars is not None else 14000
        pack_limit = 6
        platform_chat_limit = 6
        snippet_chars = 1800
    else:
        conv_limit = limit if limit is not None else 5
        char_budget = max_chars if max_chars is not None else 9000
        pack_limit = 5
        platform_chat_limit = 0
        snippet_chars = 1400

    cleaned_query = " ".join((query or "").split()).strip()
    tokens = significant_tokens(cleaned_query)
    admin_ids = await _org_admin_ids(db, admin_id)
    sections: list[str] = []
    used = 0
    seen_keys: set[str] = set()

    def _append(section: str) -> bool:
        nonlocal used
        remaining = char_budget - used
        if remaining <= 0:
            return False
        clipped = section[:remaining].strip()
        if not clipped:
            return True
        sections.append(clipped)
        used += len(clipped) + 8
        return used < char_budget

    def _take(key: str, title: str, body: str, *, label: str) -> bool:
        if key in seen_keys:
            return True
        seen_keys.add(key)
        snippet = _window_snippet(body, tokens, max_chars=snippet_chars)
        if not snippet:
            return True
        return _append(f"{label}: {title or 'Untitled'}\n{snippet}")

    # 0) CircuitNotion vector recall (semantic)
    if cleaned_query:
        try:
            from app.services.embeddings import embed_query
            from app.services.memory_index import vector_search_chunks

            query_vec = await embed_query(cleaned_query)
            if query_vec:
                vec_rows = await vector_search_chunks(
                    db,
                    admin_ids=admin_ids,
                    query_embedding=query_vec,
                    limit=conv_limit + 2,
                )
                for conv_id, title, content, distance in vec_rows:
                    key = f"import:{conv_id}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    label = f"Semantic memory match (d={distance:.3f})"
                    if not _append(
                        f"{label}: {title or 'Untitled'}\n{(content or '')[:snippet_chars]}"
                    ):
                        break
        except Exception:  # noqa: BLE001
            pass

    # 1) Exact-ish FTS on imports
    if cleaned_query:
        fts_rows = await _fts_imports(
            db,
            admin_ids=admin_ids,
            query=cleaned_query,
            limit=conv_limit,
        )
        for row_id, title, body, headline in fts_rows:
            text_body = headline.strip() if headline and headline.strip() else body
            if not _take(f"import:{row_id}", title, text_body, label="Imported conversation"):
                break

    # 2) OR / prefix FTS fallback when few hits
    if cleaned_query and len(seen_keys) < max(3, conv_limit // 2):
        or_q = _or_tsquery(tokens)
        if or_q:
            or_rows = await _fts_imports_or(
                db,
                admin_ids=admin_ids,
                tsquery=or_q,
                limit=conv_limit,
            )
            for row_id, title, body, headline in or_rows:
                text_body = headline.strip() if headline and headline.strip() else body
                if not _take(f"import:{row_id}", title, text_body, label="Imported conversation"):
                    break

    # 3) Title / text ILIKE fallback for short clinical tokens FTS may miss
    if tokens and len([k for k in seen_keys if k.startswith("import:")]) < 2:
        like_rows = await _ilike_imports(
            db, admin_ids=admin_ids, tokens=tokens[:6], limit=4
        )
        for row_id, title, body in like_rows:
            if not _take(f"import:{row_id}", title, body, label="Imported conversation"):
                break

    # 4) Durable preference / identity pins (always try)
    pref_rows = await _preference_imports(db, admin_ids=admin_ids, limit=3)
    for row_id, title, body in pref_rows:
        if not _take(f"import:{row_id}", title, body, label="Admin preference / profile memory"):
            break

    # 5) If still empty, recent imports so the agent is never amnesiac
    if not any(k.startswith("import:") for k in seen_keys):
        recent = await _recent_imports(db, admin_ids=admin_ids, limit=3)
        for row_id, title, body in recent:
            if not _take(f"import:{row_id}", title, body, label="Recent imported conversation"):
                break

    # 6) Prior platform packs
    for section in await retrieve_prior_packs(
        db, admin_ids=admin_ids, query=cleaned_query, limit=pack_limit
    ):
        if not _append(section):
            break

    # 7) Prior workspace chats (chat profile only; current admin only)
    if platform_chat_limit > 0:
        for section in await retrieve_prior_workspace_chats(
            db,
            admin_id=admin_id,
            query=cleaned_query,
            tokens=tokens,
            limit=platform_chat_limit,
            snippet_chars=snippet_chars,
            exclude_chat_id=exclude_chat_id,
        ):
            if not _append(section):
                break

    return "\n\n---\n\n".join(sections)


async def _fts_imports(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    query: str,
    limit: int,
) -> list[tuple[str, str, str, str]]:
    statement = text(
        """
        SELECT id, title, user_text,
               ts_headline(
                 'english',
                 coalesce(user_text, ''),
                 plainto_tsquery('english', :query),
                 'MaxFragments=3, MinWords=18, MaxWords=60, StartSel=, StopSel=, FragmentDelimiter= ... '
               ) AS headline
        FROM admin_memory_conversations
        WHERE admin_id IN :admin_ids
          AND to_tsvector(
                'english',
                coalesce(title, '') || ' ' || coalesce(user_text, '')
              ) @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank(
                   to_tsvector(
                     'english',
                     coalesce(title, '') || ' ' || coalesce(user_text, '')
                   ),
                   plainto_tsquery('english', :query)
                 ) DESC,
                 conversation_updated_at DESC NULLS LAST
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))
    result = await db.execute(
        statement,
        {"admin_ids": admin_ids, "query": query, "limit": limit},
    )
    return [(str(r[0]), r[1] or "", r[2] or "", r[3] or "") for r in result.all()]


async def _fts_imports_or(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    tsquery: str,
    limit: int,
) -> list[tuple[str, str, str, str]]:
    statement = text(
        """
        SELECT id, title, user_text,
               ts_headline(
                 'english',
                 coalesce(user_text, ''),
                 to_tsquery('english', :tsquery),
                 'MaxFragments=3, MinWords=18, MaxWords=50, StartSel=, StopSel=, FragmentDelimiter= ... '
               ) AS headline
        FROM admin_memory_conversations
        WHERE admin_id IN :admin_ids
          AND to_tsvector(
                'english',
                coalesce(title, '') || ' ' || coalesce(user_text, '')
              ) @@ to_tsquery('english', :tsquery)
        ORDER BY ts_rank(
                   to_tsvector(
                     'english',
                     coalesce(title, '') || ' ' || coalesce(user_text, '')
                   ),
                   to_tsquery('english', :tsquery)
                 ) DESC,
                 conversation_updated_at DESC NULLS LAST
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))
    try:
        result = await db.execute(
            statement,
            {"admin_ids": admin_ids, "tsquery": tsquery, "limit": limit},
        )
    except Exception:  # noqa: BLE001
        return []
    return [(str(r[0]), r[1] or "", r[2] or "", r[3] or "") for r in result.all()]


async def _ilike_imports(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    tokens: list[str],
    limit: int,
) -> list[tuple[str, str, str]]:
    if not tokens:
        return []
    clauses = []
    params: dict[str, object] = {"admin_ids": admin_ids, "limit": limit}
    for i, tok in enumerate(tokens):
        key = f"tok{i}"
        params[key] = f"%{tok}%"
        clauses.append(f"(title ILIKE :{key} OR user_text ILIKE :{key})")
    statement = text(
        f"""
        SELECT id, title, user_text
        FROM admin_memory_conversations
        WHERE admin_id IN :admin_ids
          AND ({' OR '.join(clauses)})
        ORDER BY conversation_updated_at DESC NULLS LAST
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))
    result = await db.execute(statement, params)
    return [(str(r[0]), r[1] or "", r[2] or "") for r in result.all()]


async def _preference_imports(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    limit: int = 3,
) -> list[tuple[str, str, str]]:
    statement = text(
        """
        SELECT id, title, user_text
        FROM admin_memory_conversations
        WHERE admin_id IN :admin_ids
          AND to_tsvector(
                'english',
                coalesce(title, '') || ' ' || coalesce(user_text, '')
              ) @@ to_tsquery(
                'english',
                'prefer | preference | style | design | brand | tone | voice | '
                'want | need | MACCE | curriculum | organization | organisation | '
                'profile | personal | CircuitNotion | OER | teaching | poster'
              )
        ORDER BY conversation_updated_at DESC NULLS LAST
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))
    result = await db.execute(
        statement, {"admin_ids": admin_ids, "limit": limit}
    )
    return [(str(r[0]), r[1] or "", r[2] or "") for r in result.all()]


async def _recent_imports(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    limit: int = 3,
) -> list[tuple[str, str, str]]:
    statement = text(
        """
        SELECT id, title, user_text
        FROM admin_memory_conversations
        WHERE admin_id IN :admin_ids
        ORDER BY conversation_updated_at DESC NULLS LAST, imported_at DESC
        LIMIT :limit
        """
    ).bindparams(bindparam("admin_ids", expanding=True))
    result = await db.execute(
        statement, {"admin_ids": admin_ids, "limit": limit}
    )
    return [(str(r[0]), r[1] or "", r[2] or "") for r in result.all()]


async def retrieve_prior_packs(
    db: AsyncSession,
    *,
    admin_ids: list[str],
    query: str,
    limit: int = 5,
) -> list[str]:
    """Return summaries of previous packs for generation continuity."""
    result = await db.execute(
        select(ContentPack)
        .where(ContentPack.author_id.in_(admin_ids))
        .order_by(ContentPack.created_at.desc())
        .limit(30)
    )
    packs = list(result.scalars().all())
    if not packs:
        return []

    tokens = [t.lower() for t in significant_tokens(query)]
    related: list[ContentPack] = []
    recent: list[ContentPack] = []
    for pack in packs:
        blob = (
            f"{pack.topic} {pack.poster_title} {pack.poster_caption} "
            f"{pack.elaboration or ''}"
        ).lower()
        if tokens and any(tok in blob for tok in tokens):
            related.append(pack)
        else:
            recent.append(pack)

    chosen = (related + recent)[:limit]
    out: list[str] = []
    for pack in chosen:
        out.append(
            "Previous platform pack:\n"
            f"- Topic requested: {pack.topic}\n"
            f"- Title produced: {pack.poster_title}\n"
            f"- Status: {pack.status}\n"
            f"- Caption: {(pack.poster_caption or '')[:320]}\n"
            f"- Elaboration opening: {(pack.elaboration or '')[:280]}\n"
            f"- Case opening: {(pack.case_study or '')[:240]}"
        )
    return out


async def retrieve_prior_workspace_chats(
    db: AsyncSession,
    *,
    admin_id: str,
    query: str,
    tokens: list[str],
    limit: int = 6,
    snippet_chars: int = 1400,
    exclude_chat_id: str | None = None,
) -> list[str]:
    """Pull relevant turns from earlier workspace chats for continuity."""
    params: dict[str, object] = {
        "admin_id": admin_id,
        "limit": max(limit * 4, 12),
    }
    exclude_sql = ""
    if exclude_chat_id:
        exclude_sql = "AND c.id <> :exclude_chat_id"
        params["exclude_chat_id"] = exclude_chat_id

    like_sql = ""
    if tokens:
        clauses = []
        for i, tok in enumerate(tokens[:6]):
            key = f"wtok{i}"
            params[key] = f"%{tok}%"
            clauses.append(f"(c.title ILIKE :{key} OR m.content ILIKE :{key})")
        like_sql = "AND (" + " OR ".join(clauses) + ")"

    statement = text(
        f"""
        SELECT c.id, c.title, c.mode, m.role, m.content, m.created_at
        FROM ai_messages m
        JOIN ai_chats c ON c.id = m.chat_id
        WHERE c.admin_id = :admin_id
          AND m.role IN ('user', 'assistant')
          {exclude_sql}
          {like_sql}
        ORDER BY m.created_at DESC
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(statement, params)
        rows = list(result.all())
    except Exception:  # noqa: BLE001
        return []

    if not rows and tokens:
        # Fall back to most recent turns across chats
        statement2 = text(
            f"""
            SELECT c.id, c.title, c.mode, m.role, m.content, m.created_at
            FROM ai_messages m
            JOIN ai_chats c ON c.id = m.chat_id
            WHERE c.admin_id = :admin_id
              AND m.role IN ('user', 'assistant')
              {exclude_sql}
            ORDER BY m.created_at DESC
            LIMIT :limit
            """
        )
        result = await db.execute(
            statement2,
            {
                "admin_id": admin_id,
                "limit": max(limit * 3, 8),
                **({"exclude_chat_id": exclude_chat_id} if exclude_chat_id else {}),
            },
        )
        rows = list(result.all())

    # Group by chat, keep a compact exchange
    by_chat: dict[str, list] = {}
    for row in rows:
        by_chat.setdefault(str(row[0]), []).append(row)

    out: list[str] = []
    for chat_id, msgs in list(by_chat.items())[:limit]:
        title = msgs[0][1] or "Untitled chat"
        mode = msgs[0][2] or "work"
        # chronological within chat slice
        ordered = sorted(msgs, key=lambda r: r[5] or r[4])
        lines = [f"Prior workspace chat ({mode}): {title}"]
        for _cid, _title, _mode, role, content, _ts in ordered[-4:]:
            snippet = _window_snippet(content or "", tokens, max_chars=snippet_chars // 2)
            if snippet:
                lines.append(f"{role}: {snippet}")
        if len(lines) > 1:
            out.append("\n".join(lines))
    return out


def build_memory_query(
    *,
    current_message: str,
    chat_title: str = "",
    project_name: str = "",
    project_description: str = "",
    recent_user_messages: list[str] | None = None,
) -> str:
    """Blend live turn + project + recent turns into a stronger retrieval query."""
    parts: list[str] = []
    if project_name:
        parts.append(project_name)
    if project_description:
        parts.append(project_description[:400])
    if chat_title and chat_title not in ("New chat", "Personal chat"):
        parts.append(chat_title)
    for msg in (recent_user_messages or [])[-3:]:
        if msg.strip():
            parts.append(msg.strip()[:400])
    if current_message.strip():
        parts.append(current_message.strip())
    return "\n".join(parts)
