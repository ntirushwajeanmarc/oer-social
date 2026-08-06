from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
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
    AiMessageCreate,
    AiMessageOut,
    AiMessageResponse,
    AiProjectCreate,
    AiProjectOut,
    HistoryItem,
    ImportConversationOut,
)
from app.services import openai_service
from app.services.admin_memory import build_memory_query, retrieve_admin_memory
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
    chat_q = chat_q.order_by(AiChat.updated_at.desc()).limit(40)
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
    ).limit(40)
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
    return items[:60]


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
    stmt = stmt.order_by(AiChat.updated_at.desc()).limit(50)
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

    user_msg = AiMessage(chat_id=chat.id, role="user", content=content)
    db.add(user_msg)

    if chat.title in ("New chat", "Personal chat") or not chat.title:
        chat.title = content[:80].strip() or chat.title

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
        current_message=content,
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

    system = _system_prompt(
        mode=chat.mode,
        make_feed=payload.make_feed and chat.mode == "personal",
        brief_text=brief_text,
        project_note=project_note,
        memory=memory,
    )

    history_messages = [
        {"role": m.role, "content": m.content}
        for m in chat.messages
        if m.role in ("user", "assistant")
    ][-28:]
    history_messages.append({"role": "user", "content": content})

    try:
        reply = await openai_service.chat_completion(
            messages=[{"role": "system", "content": system}, *history_messages],
            temperature=0.55 if chat.mode == "personal" else 0.45,
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"CircuitNotion chat error: {exc}") from exc

    if not reply:
        reply = "I could not generate a reply. Please try again."

    assistant_msg = AiMessage(chat_id=chat.id, role="assistant", content=reply)
    db.add(assistant_msg)
    chat.updated_at = datetime.now(UTC)

    draft_pack_id: str | None = None
    if payload.make_feed and chat.mode == "personal":
        try:
            draft_pack_id = await _create_draft_pack_from_chat(
                db,
                admin=admin,
                user_message=content,
                assistant_reply=reply,
            )
        except Exception as exc:  # noqa: BLE001
            # Keep the chat reply even if pack draft fails.
            await db.commit()
            await db.refresh(assistant_msg)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Chat reply saved, but draft feed pack failed: {exc}. "
                    "You can retry with the feed toggle, or generate a pack from Create."
                ),
            ) from exc

    await db.commit()
    await db.refresh(assistant_msg)
    return AiMessageResponse(
        message=AiMessageOut.model_validate(assistant_msg),
        draft_pack_id=draft_pack_id,
    )


def _system_prompt(
    *,
    mode: str,
    make_feed: bool,
    brief_text: str,
    project_note: str,
    memory: str,
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
    if mode == "personal":
        feed_note = (
            "\nThe admin may turn this turn into a draft OER teaching pack for the learner feed. "
            "Keep content clinically safe, educational, and suitable for open educational use."
            if make_feed
            else ""
        )
        return (
            "You are the admin's personal AI organization assistant on CircuitNotion "
            "(not ChatGPT). Help with planning, reflection, curriculum ideas, and "
            "personal organization tied to their educational work. Be concise and practical. "
            "When memory is present, recall preferences and unfinished threads explicitly."
            + feed_note
            + memory_block
        )

    parts = [
        "You are the admin's educational workspace assistant on CircuitNotion for OER Social Learning.",
        "Help with curriculum planning, teaching content ideas, continuity of prior work, and project notes.",
        "Stay clinically safe; prefer open educational framing; do not invent site-specific protocols.",
        "Use retrieved memory to continue themes already covered and avoid repeating finished packs.",
    ]
    if brief_text:
        parts.append("\nACTIVE PROGRAM BRIEF:\n" + brief_text)
    if project_note:
        parts.append("\nCURRENT PROJECT:\n" + project_note)
    if memory_block:
        parts.append(memory_block)
    return "\n".join(parts)


async def _create_draft_pack_from_chat(
    db: AsyncSession,
    *,
    admin: User,
    user_message: str,
    assistant_reply: str,
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
        poster_image_path="",
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

    if (settings.openai_image_model or "").strip():
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
