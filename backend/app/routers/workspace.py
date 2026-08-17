from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import (
    AdminMemoryConversation,
    AiChat,
    AiMessage,
    AiProject,
    ContentPack,
    Question,
    User,
)
from app.schemas import (
    AiChatCreate,
    AiChatListItem,
    AiChatOut,
    AiChatUpdate,
    AiImageCreate,
    AiMessageCreate,
    AiMessageOut,
    AiMessageResponse,
    AiMessageUpdate,
    AiProjectCreate,
    AiProjectOut,
    ContinueImportRequest,
    HistoryItem,
    ImportConversationOut,
    MessageToFeedRequest,
    MessageToFeedResponse,
)
from app.services import openai_service
from app.services.admin_memory import build_memory_query, retrieve_admin_memory
from app.services.chatgpt_export import parse_transcript_turns
from app.services.program_brief import active_grounding, get_active_brief, render_brief
from app.services.security import require_admin

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/projects", response_model=list[AiProjectOut])
async def list_projects(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AiProject]:
    result = await db.execute(
        select(AiProject)
        .where(AiProject.admin_id == admin.id)
        .order_by(AiProject.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("/projects", response_model=AiProjectOut, status_code=201)
async def create_project(
    payload: AiProjectCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiProject:
    project = AiProject(
        admin_id=admin.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/history", response_model=list[HistoryItem])
async def list_history(
    q: str = Query(default="", max_length=400),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[HistoryItem]:
    cleaned = " ".join(q.split()).strip().lower()
    items: list[HistoryItem] = []

    chat_q = select(AiChat).where(AiChat.admin_id == admin.id)
    if cleaned:
        chat_q = chat_q.where(AiChat.title.ilike(f"%{cleaned}%"))
    chat_q = chat_q.order_by(AiChat.updated_at.desc()).limit(80)
    chats = list((await db.execute(chat_q)).scalars().all())
    for chat in chats:
        items.append(
            HistoryItem(
                id=chat.id,
                title=chat.title or "Untitled chat",
                source="platform",
                mode=chat.mode,
                updated_at=chat.updated_at,
                preview="",
            )
        )

    import_q = select(AdminMemoryConversation)
    # Org-wide imported corpus (shared across admin accounts)
    if cleaned:
        import_q = import_q.where(
            or_(
                AdminMemoryConversation.title.ilike(f"%{cleaned}%"),
                AdminMemoryConversation.user_text.ilike(f"%{cleaned}%"),
            )
        )
    import_q = import_q.order_by(
        AdminMemoryConversation.conversation_updated_at.desc().nullslast()
    ).limit(200)
    imports = list((await db.execute(import_q)).scalars().all())
    for row in imports:
        preview = (row.user_text or "").strip().replace("\n", " ")
        items.append(
            HistoryItem(
                id=row.id,
                title=row.title or "Imported conversation",
                source="import",
                mode=None,
                updated_at=row.conversation_updated_at or row.imported_at,
                preview=preview[:180],
            )
        )

    items.sort(key=lambda i: i.updated_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return items[:250]


@router.get("/imports/{import_id}", response_model=ImportConversationOut)
async def get_import(
    import_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminMemoryConversation:
    row = await db.get(AdminMemoryConversation, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="Imported conversation not found")
    return row


@router.post("/imports/{import_id}/continue", response_model=AiChatOut, status_code=201)
async def continue_import(
    import_id: str,
    payload: ContinueImportRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiChat:
    """Start a new CircuitNotion chat seeded with an imported ChatGPT conversation."""
    row = await db.get(AdminMemoryConversation, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="Imported conversation not found")

    project_id = payload.project_id
    if project_id:
        project = await db.get(AiProject, project_id)
        if not project or project.admin_id != admin.id:
            raise HTTPException(status_code=404, detail="Project not found")

    title = f"Continue: {row.title or 'Imported chat'}".strip()[:500]
    chat = AiChat(
        admin_id=admin.id,
        project_id=project_id,
        title=title,
        mode=payload.mode,
    )
    db.add(chat)
    await db.flush()

    transcript = (row.user_text or "").strip()
    turns = parse_transcript_turns(transcript)
    if not turns and transcript:
        turns = [{"role": "user", "content": transcript}]

    db.add(
        AiMessage(
            chat_id=chat.id,
            role="system",
            content=(
                "CONTINUATION CONTEXT — imported ChatGPT conversation.\n"
                f"Title: {row.title or 'Untitled'}\n"
                "The following user and assistant messages are the original thread. "
                "Continue from where it left off. Do not restart unless asked. "
                "Do not invent clinical protocols."
            ),
        )
    )
    # Keep the visible thread complete; the model still uses a recent window.
    for turn in turns[:400]:
        role = turn["role"] if turn["role"] in {"user", "assistant"} else "user"
        db.add(
            AiMessage(
                chat_id=chat.id,
                role=role,
                content=turn["content"][:12000],
                image_path="",
            )
        )
    if not turns:
        db.add(
            AiMessage(
                chat_id=chat.id,
                role="assistant",
                content=(
                    f"Continuing from **{row.title or 'your imported conversation'}**.\n\n"
                    "I loaded that history. What should we pick up next?"
                ),
            )
        )
    chat.updated_at = datetime.now(UTC)
    await db.commit()
    return await _load_chat(db, chat.id, admin.id)


@router.get("/chats", response_model=list[AiChatListItem])
async def list_chats(
    mode: str | None = Query(default=None, pattern="^(work|personal)$"),
    project_id: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AiChat]:
    stmt = select(AiChat).where(AiChat.admin_id == admin.id)
    if mode:
        stmt = stmt.where(AiChat.mode == mode)
    if project_id:
        stmt = stmt.where(AiChat.project_id == project_id)
    stmt = stmt.order_by(AiChat.updated_at.desc()).limit(200)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/chats", response_model=AiChatOut, status_code=201)
async def create_chat(
    payload: AiChatCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiChat:
    project_id = payload.project_id
    if project_id:
        project = await db.get(AiProject, project_id)
        if not project or project.admin_id != admin.id:
            raise HTTPException(status_code=404, detail="Project not found")
    title = payload.title.strip() or ("Personal chat" if payload.mode == "personal" else "New chat")
    chat = AiChat(
        admin_id=admin.id,
        project_id=project_id,
        title=title[:500],
        mode=payload.mode,
    )
    db.add(chat)
    await db.commit()
    return await _load_chat(db, chat.id, admin.id)


@router.get("/chats/{chat_id}", response_model=AiChatOut)
async def get_chat(
    chat_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiChat:
    return await _load_chat(db, chat_id, admin.id)


@router.patch("/chats/{chat_id}", response_model=AiChatOut)
async def rename_chat(
    chat_id: str,
    payload: AiChatUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiChat:
    chat = await _load_chat(db, chat_id, admin.id)
    chat.title = payload.title.strip()[:500] or chat.title
    chat.updated_at = datetime.now(UTC)
    await db.commit()
    return await _load_chat(db, chat.id, admin.id)


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    chat = await _load_chat(db, chat_id, admin.id)
    await db.delete(chat)
    await db.commit()


@router.post("/chats/{chat_id}/messages", response_model=AiMessageResponse)
async def send_message(
    chat_id: str,
    payload: AiMessageCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiMessageResponse:
    chat = await _load_chat(db, chat_id, admin.id)
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_msg = AiMessage(chat_id=chat.id, role="user", content=content, image_path="")
    db.add(user_msg)

    if chat.title in ("New chat", "Personal chat") or not chat.title:
        chat.title = content[:80].strip() or chat.title

    try:
        assistant_msg, draft_pack_id = await _complete_assistant_turn(
            db,
            chat=chat,
            admin=admin,
            user_content=content,
            make_feed=payload.make_feed,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"CircuitNotion chat error: {exc}") from exc

    await db.commit()
    await db.refresh(assistant_msg)
    return AiMessageResponse(
        message=AiMessageOut.model_validate(assistant_msg),
        draft_pack_id=draft_pack_id,
        chat=AiChatOut.model_validate(await _load_chat(db, chat.id, admin.id)),
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post("/chats/{chat_id}/messages/stream")
async def send_message_stream(
    chat_id: str,
    payload: AiMessageCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream assistant tokens as SSE: user → delta* → done | error."""
    chat = await _load_chat(db, chat_id, admin.id)
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_msg = AiMessage(chat_id=chat.id, role="user", content=content, image_path="")
    db.add(user_msg)
    if chat.title in ("New chat", "Personal chat") or not chat.title:
        chat.title = content[:80].strip() or chat.title
    await db.flush()
    await db.refresh(user_msg)

    try:
        llm_messages, temperature = await _build_turn_messages(
            db,
            chat=chat,
            admin=admin,
            user_content=content,
            make_feed=payload.make_feed,
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Chat prep failed: {exc}") from exc

    await db.commit()
    user_out = AiMessageOut.model_validate(user_msg).model_dump(mode="json")
    chat_id_val = chat.id
    admin_id = admin.id
    make_feed = payload.make_feed
    user_content = content

    async def events() -> AsyncIterator[str]:
        yield _sse({"type": "user", "message": user_out})
        chunks: list[str] = []
        try:
            async for delta in openai_service.chat_completion_stream(
                messages=llm_messages,
                temperature=temperature,
            ):
                chunks.append(delta)
                yield _sse({"type": "delta", "text": delta})

            reply = "".join(chunks).strip() or (
                "I could not generate a reply. Please try again."
            )
            # Persist the assistant reply immediately so the UI can reconcile even
            # if the client disconnects during a slow make_feed step.
            async with SessionLocal() as session:
                live = await _load_chat(session, chat_id_val, admin_id)
                assistant_msg = AiMessage(
                    chat_id=live.id,
                    role="assistant",
                    content=reply,
                    image_path="",
                )
                session.add(assistant_msg)
                live.updated_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(assistant_msg)
                chat_out = await _load_chat(session, chat_id_val, admin_id)
                yield _sse(
                    {
                        "type": "done",
                        "message": AiMessageOut.model_validate(
                            assistant_msg
                        ).model_dump(mode="json"),
                        "draft_pack_id": None,
                        "chat": AiChatOut.model_validate(chat_out).model_dump(
                            mode="json"
                        ),
                    }
                )

            if make_feed:
                try:
                    async with SessionLocal() as session:
                        admin_row = await session.get(User, admin_id)
                        if not admin_row:
                            raise RuntimeError("Admin account not found")
                        draft_pack_id = await _create_draft_pack_from_chat(
                            session,
                            admin=admin_row,
                            user_message=user_content,
                            assistant_reply=reply,
                        )
                        await session.commit()
                    yield _sse(
                        {"type": "feed", "draft_pack_id": draft_pack_id}
                    )
                except Exception as feed_exc:  # noqa: BLE001
                    yield _sse(
                        {
                            "type": "feed_error",
                            "detail": (
                                f"Reply saved, but draft feed pack failed: {feed_exc}"
                            ),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "detail": f"CircuitNotion chat error: {exc}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/chats/{chat_id}/messages/{message_id}", response_model=AiMessageResponse)
async def edit_message(
    chat_id: str,
    message_id: str,
    payload: AiMessageUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiMessageResponse:
    chat = await _load_chat(db, chat_id, admin.id)
    target = next((m for m in chat.messages if m.id == message_id), None)
    if not target or target.role != "user":
        raise HTTPException(status_code=404, detail="User message not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    ordered = sorted(
        chat.messages,
        key=lambda m: (m.created_at or datetime.min.replace(tzinfo=UTC), m.id),
    )
    try:
        idx = next(i for i, m in enumerate(ordered) if m.id == target.id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="User message not found") from exc
    for msg in ordered[idx + 1 :]:
        await db.delete(msg)

    target.content = content
    chat.updated_at = datetime.now(UTC)
    await db.flush()
    chat = await _load_chat(db, chat_id, admin.id)

    draft_pack_id: str | None = None
    assistant_msg: AiMessage | None = None
    if payload.regenerate:
        try:
            assistant_msg, draft_pack_id = await _complete_assistant_turn(
                db,
                chat=chat,
                admin=admin,
                user_content=content,
                make_feed=False,
            )
        except Exception as exc:  # noqa: BLE001
            await db.commit()
            raise HTTPException(
                status_code=502,
                detail=f"Message edited, but regenerate failed: {exc}",
            ) from exc

    await db.commit()
    chat_out = await _load_chat(db, chat.id, admin.id)
    if assistant_msg is None:
        # Return the edited user message when not regenerating.
        edited = next(m for m in chat_out.messages if m.id == message_id)
        return AiMessageResponse(
            message=AiMessageOut.model_validate(edited),
            draft_pack_id=None,
            chat=AiChatOut.model_validate(chat_out),
        )
    await db.refresh(assistant_msg)
    return AiMessageResponse(
        message=AiMessageOut.model_validate(assistant_msg),
        draft_pack_id=draft_pack_id,
        chat=AiChatOut.model_validate(chat_out),
    )


@router.delete("/chats/{chat_id}/messages/{message_id}", status_code=204)
async def delete_message(
    chat_id: str,
    message_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    chat = await _load_chat(db, chat_id, admin.id)
    target = next((m for m in chat.messages if m.id == message_id), None)
    if not target or target.role == "system":
        raise HTTPException(status_code=404, detail="Message not found")
    await db.delete(target)
    chat.updated_at = datetime.now(UTC)
    await db.commit()


@router.post(
    "/chats/{chat_id}/messages/{message_id}/to-feed",
    response_model=MessageToFeedResponse,
)
async def message_to_feed(
    chat_id: str,
    message_id: str,
    payload: MessageToFeedRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageToFeedResponse:
    """Turn an assistant reply into an OER pack for signed-up learners."""
    chat = await _load_chat(db, chat_id, admin.id)
    target = next((m for m in chat.messages if m.id == message_id), None)
    if not target or target.role != "assistant":
        raise HTTPException(status_code=404, detail="Assistant message not found")

    user_content = ""
    for msg in reversed(chat.messages):
        if msg.created_at and target.created_at and msg.created_at > target.created_at:
            continue
        if msg.id == target.id:
            continue
        if msg.role == "user" and (msg.content or "").strip():
            user_content = msg.content.strip()
            break
    if not user_content:
        user_content = (target.content or "").strip()[:800] or chat.title or "Teaching pack"

    try:
        pack_id = await _create_draft_pack_from_chat(
            db,
            admin=admin,
            user_message=user_content,
            assistant_reply=target.content or "",
            existing_image_path=target.image_path or "",
        )
        pack = await db.get(ContentPack, pack_id)
        if not pack:
            raise RuntimeError("Pack was not created")
        if payload.publish:
            pack.status = "published"
            pack.published_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(pack)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Could not create feed pack: {exc}",
        ) from exc

    return MessageToFeedResponse(
        pack_id=pack.id,
        status=pack.status,
        poster_title=pack.poster_title or pack.topic,
    )


@router.post("/chats/{chat_id}/images", response_model=AiMessageResponse)
async def generate_chat_image(
    chat_id: str,
    payload: AiImageCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiMessageResponse:
    chat = await _load_chat(db, chat_id, admin.id)
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    user_msg = AiMessage(
        chat_id=chat.id,
        role="user",
        content=f"Generate image: {prompt}",
        image_path="",
    )
    db.add(user_msg)
    if chat.title in ("New chat", "Personal chat") or not chat.title:
        chat.title = f"Image: {prompt[:60]}".strip()

    try:
        image_path = await openai_service.generate_image(
            prompt=prompt,
            filename_stem=chat.id,
            subdir="chat",
            educational_poster=payload.style == "poster",
            title=prompt[:120],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}") from exc

    assistant_msg = AiMessage(
        chat_id=chat.id,
        role="assistant",
        content=f"Here’s an image for: **{prompt}**",
        image_path=image_path,
    )
    db.add(assistant_msg)
    chat.updated_at = datetime.now(UTC)

    draft_pack_id: str | None = None
    if payload.make_feed:
        try:
            draft_pack_id = await _create_draft_pack_from_chat(
                db,
                admin=admin,
                user_message=prompt,
                assistant_reply=f"Teaching visual for: {prompt}",
                existing_image_path=image_path,
            )
        except Exception as exc:  # noqa: BLE001
            await db.commit()
            await db.refresh(assistant_msg)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Image saved in chat, but draft feed pack failed: {exc}. "
                    "You can still download the image or retry feed creation."
                ),
            ) from exc

    await db.commit()
    await db.refresh(assistant_msg)
    return AiMessageResponse(
        message=AiMessageOut.model_validate(assistant_msg),
        draft_pack_id=draft_pack_id,
        chat=AiChatOut.model_validate(await _load_chat(db, chat.id, admin.id)),
    )


@router.post("/chats/{chat_id}/images/stream")
async def generate_chat_image_stream(
    chat_id: str,
    payload: AiImageCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Generate an image with SSE keepalives so Cloudflare does not 502."""
    chat = await _load_chat(db, chat_id, admin.id)
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    user_msg = AiMessage(
        chat_id=chat.id,
        role="user",
        content=f"Generate image: {prompt}",
        image_path="",
    )
    db.add(user_msg)
    if chat.title in ("New chat", "Personal chat") or not chat.title:
        chat.title = f"Image: {prompt[:60]}".strip()
    await db.commit()
    await db.refresh(user_msg)

    user_out = AiMessageOut.model_validate(user_msg).model_dump(mode="json")
    chat_id_val = chat.id
    admin_id = admin.id
    make_feed = payload.make_feed
    style = payload.style

    async def events() -> AsyncIterator[str]:
        yield _sse({"type": "user", "message": user_out})
        yield _sse({"type": "status", "text": "Generating image…"})
        try:
            gen_task = asyncio.create_task(
                openai_service.generate_image(
                    prompt=prompt,
                    filename_stem=chat_id_val,
                    subdir="chat",
                    educational_poster=style == "poster",
                    title=prompt[:120],
                )
            )
            while not gen_task.done():
                done, _ = await asyncio.wait({gen_task}, timeout=8.0)
                if not done:
                    yield ": keepalive\n\n"
                    yield _sse({"type": "status", "text": "Still generating…"})
            image_path = await gen_task

            async with SessionLocal() as session:
                live = await _load_chat(session, chat_id_val, admin_id)
                assistant_msg = AiMessage(
                    chat_id=live.id,
                    role="assistant",
                    content=f"Here’s an image for: **{prompt}**",
                    image_path=image_path,
                )
                session.add(assistant_msg)
                live.updated_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(assistant_msg)
                chat_out = await _load_chat(session, chat_id_val, admin_id)
                yield _sse(
                    {
                        "type": "done",
                        "message": AiMessageOut.model_validate(
                            assistant_msg
                        ).model_dump(mode="json"),
                        "draft_pack_id": None,
                        "chat": AiChatOut.model_validate(chat_out).model_dump(
                            mode="json"
                        ),
                    }
                )

            if make_feed:
                yield _sse({"type": "status", "text": "Preparing feed pack…"})
                try:
                    async with SessionLocal() as session:
                        admin_row = await session.get(User, admin_id)
                        if not admin_row:
                            raise RuntimeError("Admin account not found")
                        draft_pack_id = await _create_draft_pack_from_chat(
                            session,
                            admin=admin_row,
                            user_message=prompt,
                            assistant_reply=f"Teaching visual for: {prompt}",
                            existing_image_path=image_path,
                        )
                        await session.commit()
                    yield _sse({"type": "feed", "draft_pack_id": draft_pack_id})
                except Exception as feed_exc:  # noqa: BLE001
                    yield _sse(
                        {
                            "type": "feed_error",
                            "detail": (
                                f"Image saved, but draft feed pack failed: {feed_exc}"
                            ),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            yield _sse(
                {"type": "error", "detail": f"Image generation failed: {exc}"}
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _build_turn_messages(
    db: AsyncSession,
    *,
    chat: AiChat,
    admin: User,
    user_content: str,
    make_feed: bool,
) -> tuple[list[dict[str, str]], float]:
    brief_text = ""
    project_note = ""
    project_name = ""
    project_description = ""
    if chat.mode == "work":
        brief = await get_active_brief(db)
        brief_text = render_brief(brief) if brief else await active_grounding(db)
        if chat.project_id:
            project = await db.get(AiProject, chat.project_id)
            if project:
                project_name = project.name
                project_description = project.description or ""
                project_note = f"Project: {project.name}\n{project.description}".strip()

    recent_user = [
        m.content
        for m in chat.messages
        if m.role == "user" and (m.content or "").strip()
    ][-3:]
    memory_query = build_memory_query(
        current_message=user_content,
        chat_title=chat.title or "",
        project_name=project_name,
        project_description=project_description,
        recent_user_messages=recent_user,
    )
    memory = await retrieve_admin_memory(
        db,
        admin_id=admin.id,
        query=memory_query,
        profile="chat",
        exclude_chat_id=chat.id,
    )
    continuation = "\n\n".join(
        m.content for m in chat.messages if m.role == "system" and (m.content or "").strip()
    )
    system = _system_prompt(
        mode=chat.mode,
        make_feed=make_feed,
        brief_text=brief_text,
        project_note=project_note,
        memory=memory,
        continuation=continuation,
    )
    history_messages = [
        {"role": m.role, "content": m.content}
        for m in chat.messages
        if m.role in ("user", "assistant")
    ][-28:]
    if not history_messages or history_messages[-1].get("content") != user_content:
        history_messages.append({"role": "user", "content": user_content})

    temperature = 0.55 if chat.mode == "personal" else 0.45
    return [{"role": "system", "content": system}, *history_messages], temperature


async def _complete_assistant_turn(
    db: AsyncSession,
    *,
    chat: AiChat,
    admin: User,
    user_content: str,
    make_feed: bool,
) -> tuple[AiMessage, str | None]:
    llm_messages, temperature = await _build_turn_messages(
        db,
        chat=chat,
        admin=admin,
        user_content=user_content,
        make_feed=make_feed,
    )
    reply = await openai_service.chat_completion(
        messages=llm_messages,
        temperature=temperature,
    )
    if not reply:
        reply = "I could not generate a reply. Please try again."

    assistant_msg = AiMessage(
        chat_id=chat.id, role="assistant", content=reply, image_path=""
    )
    db.add(assistant_msg)
    chat.updated_at = datetime.now(UTC)

    draft_pack_id: str | None = None
    if make_feed:
        draft_pack_id = await _create_draft_pack_from_chat(
            db,
            admin=admin,
            user_message=user_content,
            assistant_reply=reply,
        )
    return assistant_msg, draft_pack_id


def _system_prompt(
    *,
    mode: str,
    make_feed: bool,
    brief_text: str,
    project_note: str,
    memory: str,
    continuation: str = "",
) -> str:
    memory_block = (
        "\n\nRELEVANT ADMIN MEMORY (imported ChatGPT history, preference pins, "
        "prior packs, and earlier workspace chats). Treat this as durable context about "
        "this admin's projects, voice, and prior decisions. Prefer continuity with it. "
        "Do not invent clinical protocols or contradict safer local practice:\n"
        + memory
        if memory
        else ""
    )
    continuation_block = (
        "\n\n" + continuation.strip()
        if continuation.strip()
        else ""
    )
    feed_note = (
        "\nThis turn may become a draft OER teaching pack for the learner feed. "
        "Keep content clinically safe, educational, and suitable for open educational use."
        if make_feed
        else ""
    )
    style = (
        "\nTone: professional educator. Clear structure, precise language, minimal filler. "
        "Prefer short sections and actionable next steps when planning. "
        "Use markdown sparingly for headings and lists."
    )
    if mode == "personal":
        return (
            "You are a professional personal assistant for an educational leader on "
            "CircuitNotion (not ChatGPT). Support planning, reflection, curriculum ideas, "
            "and organization tied to their teaching work. Be concise and practical. "
            "When memory is present, recall preferences and unfinished threads explicitly."
            + style
            + feed_note
            + continuation_block
            + memory_block
        )

    parts = [
        "You are the professional educational workspace assistant for OER Social Learning "
        "on CircuitNotion.",
        "Support curriculum planning, teaching content design, continuity of prior work, "
        "and project notes for clinical educators.",
        "Stay clinically safe; prefer open educational framing; do not invent site-specific protocols.",
        "Use retrieved memory to continue themes already covered and avoid repeating finished packs.",
        style.strip(),
    ]
    if feed_note:
        parts.append(feed_note)
    if brief_text:
        parts.append("\nACTIVE PROGRAM BRIEF:\n" + brief_text)
    if project_note:
        parts.append("\nCURRENT PROJECT:\n" + project_note)
    if continuation_block:
        parts.append(continuation_block)
    if memory_block:
        parts.append(memory_block)
    return "\n".join(parts)


async def _create_draft_pack_from_chat(
    db: AsyncSession,
    *,
    admin: User,
    user_message: str,
    assistant_reply: str,
    existing_image_path: str = "",
) -> str:
    extracted = await openai_service.extract_pack_topic(
        user_message=user_message,
        assistant_reply=assistant_reply,
    )
    topic = extracted["topic"]
    focus = extracted["focus"]
    admin_memory = await retrieve_admin_memory(
        db,
        admin_id=admin.id,
        query=f"{topic} {focus} {user_message[:400]}",
        profile="pack",
    )
    domain_grounding = await active_grounding(db)
    data = await openai_service.generate_content_pack(
        topic=topic,
        focus=focus,
        admin_memory=admin_memory,
        domain_grounding=domain_grounding,
    )

    pack = ContentPack(
        author_id=admin.id,
        status="draft",
        topic=topic.strip(),
        poster_title=str(data.get("poster_title", topic))[:240],
        poster_caption=str(data.get("poster_caption", "")),
        poster_visual_prompt=str(data.get("poster_visual_prompt", "")),
        poster_image_path=existing_image_path or "",
        elaboration=str(data.get("elaboration", "")),
        case_study=str(data.get("case_study", "")),
    )
    db.add(pack)
    await db.flush()

    questions = data.get("questions") or []
    if not isinstance(questions, list):
        questions = []
    for i, q in enumerate(questions[:5]):
        if not isinstance(q, dict):
            continue
        db.add(
            Question(
                pack_id=pack.id,
                prompt=str(q.get("prompt", "Reflect on this case.")),
                question_type=str(q.get("question_type", "short_answer")),
                rubric=str(q.get("rubric", "")),
                sort_order=i,
            )
        )

    if not pack.poster_image_path and (settings.openai_image_model or "").strip():
        try:
            pack.poster_image_path = await openai_service.generate_poster_image(
                visual_prompt=pack.poster_visual_prompt,
                title=pack.poster_title,
                pack_id=pack.id,
            )
        except Exception:  # noqa: BLE001
            # Draft text is enough; image can be regenerated later.
            pack.poster_image_path = ""

    await db.flush()
    return pack.id


async def _load_chat(db: AsyncSession, chat_id: str, admin_id: str) -> AiChat:
    result = await db.execute(
        select(AiChat)
        .options(selectinload(AiChat.messages))
        .where(AiChat.id == chat_id, AiChat.admin_id == admin_id)
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.messages.sort(key=lambda m: m.created_at or datetime.min.replace(tzinfo=UTC))
    return chat
