from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import ContentPack, Question, SocialPost, User
from app.schemas import GeneratePackRequest, PackListItem, PackOut, SocialExportOut
from app.services import openai_service, social
from app.services.admin_memory import retrieve_admin_memory
from app.services.program_brief import active_grounding
from app.services.security import get_current_user, require_admin

router = APIRouter(prefix="/packs", tags=["packs"])


@router.post("/generate", response_model=PackOut)
async def generate_pack(
    payload: GeneratePackRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentPack:
    try:
        admin_memory = await retrieve_admin_memory(
            db,
            admin_id=admin.id,
            query=f"{payload.topic} {payload.focus}",
            profile="pack",
        )
        domain_grounding = await active_grounding(db)
        data = await openai_service.generate_content_pack(
            topic=payload.topic,
            focus=payload.focus,
            admin_memory=admin_memory,
            domain_grounding=domain_grounding,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OpenAI text error: {exc}") from exc

    pack = ContentPack(
        author_id=admin.id,
        status="draft",
        topic=payload.topic.strip(),
        poster_title=str(data.get("poster_title", payload.topic))[:240],
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
        except Exception as exc:  # noqa: BLE001
            await db.commit()
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Pack text saved as draft, but poster image failed: {exc}. "
                    "Open the pack and use Regenerate image, or check OPENAI_IMAGE_MODEL / API access."
                ),
            ) from exc
    else:
        pack.poster_image_path = ""

    await db.commit()
    return await _load_pack(db, pack.id)


@router.post("/{pack_id}/regenerate-image", response_model=PackOut)
async def regenerate_image(
    pack_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentPack:
    pack = await db.get(ContentPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    try:
        pack.poster_image_path = await openai_service.generate_poster_image(
            visual_prompt=pack.poster_visual_prompt,
            title=pack.poster_title,
            pack_id=pack.id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}") from exc
    await db.commit()
    return await _load_pack(db, pack.id)


@router.get("/admin", response_model=list[PackListItem])
async def list_admin_packs(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PackListItem]:
    result = await db.execute(select(ContentPack).order_by(ContentPack.created_at.desc()))
    packs = list(result.scalars().all())
    items: list[PackListItem] = []
    for p in packs:
        count = await db.scalar(select(func.count(Question.id)).where(Question.pack_id == p.id))
        items.append(
            PackListItem(
                id=p.id,
                status=p.status,
                topic=p.topic,
                poster_title=p.poster_title,
                poster_image_path=p.poster_image_path or "",
                created_at=p.created_at,
                published_at=p.published_at,
                question_count=int(count or 0),
            )
        )
    return items


@router.get("/feed", response_model=list[PackListItem])
async def learner_feed(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PackListItem]:
    result = await db.execute(
        select(ContentPack)
        .where(ContentPack.status == "published")
        .order_by(ContentPack.published_at.desc().nullslast())
    )
    packs = list(result.scalars().all())
    items: list[PackListItem] = []
    for p in packs:
        count = await db.scalar(select(func.count(Question.id)).where(Question.pack_id == p.id))
        items.append(
            PackListItem(
                id=p.id,
                status=p.status,
                topic=p.topic,
                poster_title=p.poster_title,
                poster_image_path=p.poster_image_path or "",
                created_at=p.created_at,
                published_at=p.published_at,
                question_count=int(count or 0),
            )
        )
    return items


@router.get("/{pack_id}", response_model=PackOut)
async def get_pack(
    pack_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentPack:
    pack = await _load_pack(db, pack_id)
    if pack.status != "published" and user.role != "admin":
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack


@router.post("/{pack_id}/publish", response_model=PackOut)
async def publish_pack(
    pack_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentPack:
    pack = await db.get(ContentPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    pack.status = "published"
    pack.published_at = datetime.now(UTC)
    await db.commit()
    return await _load_pack(db, pack.id)


@router.delete("/{pack_id}", status_code=204)
async def delete_pack(
    pack_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    pack = await _load_pack(db, pack_id)
    await db.delete(pack)
    await db.commit()


@router.post("/{pack_id}/publish-social", response_model=list[SocialExportOut])
async def publish_social(
    pack_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SocialExportOut]:
    """Post poster + caption to Instagram and X when configured."""
    pack = await _load_pack(db, pack_id)
    if pack.status != "published":
        raise HTTPException(status_code=400, detail="Publish the pack to the feed before posting socially")
    if not pack.poster_image_path:
        raise HTTPException(status_code=400, detail="Pack has no poster image — regenerate image first")

    caption = (
        f"{pack.poster_title}\n\n{pack.poster_caption}\n\n"
        f"#OER #Anesthesia #CriticalCare #MedEdAfrica"
    )[:2200]

    results: list[SocialExportOut] = []

    x_id, x_err = await social.post_to_x(caption=caption, poster_image_path=pack.poster_image_path)
    x_status = "posted" if x_id and not x_err else ("ready_to_export" if "not configured" in x_err else "failed")
    x_post = SocialPost(
        pack_id=pack.id,
        platform="x",
        status=x_status,
        caption=caption,
        external_id=x_id,
        error_message=x_err,
    )
    db.add(x_post)
    await db.flush()
    results.append(_social_out(x_post, pack))

    ig_id, ig_err = await social.post_to_instagram(
        caption=caption, poster_image_path=pack.poster_image_path
    )
    ig_status = (
        "posted"
        if ig_id and not ig_err
        else ("ready_to_export" if ("not configured" in ig_err or "public HTTPS" in ig_err) else "failed")
    )
    ig_post = SocialPost(
        pack_id=pack.id,
        platform="instagram",
        status=ig_status,
        caption=caption,
        external_id=ig_id,
        error_message=ig_err,
    )
    db.add(ig_post)
    await db.flush()
    results.append(_social_out(ig_post, pack))

    await db.commit()
    return results


@router.post("/{pack_id}/export-social", response_model=list[SocialExportOut])
async def export_social(
    pack_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SocialExportOut]:
    return await publish_social(pack_id, admin, db)


def _social_out(post: SocialPost, pack: ContentPack) -> SocialExportOut:
    return SocialExportOut(
        id=post.id,
        pack_id=pack.id,
        platform=post.platform,
        status=post.status,
        caption=post.caption,
        visual_prompt=pack.poster_visual_prompt,
        poster_title=pack.poster_title,
        poster_image_path=pack.poster_image_path or "",
        external_id=post.external_id or "",
        error_message=post.error_message or "",
        created_at=post.created_at or datetime.now(UTC),
    )


async def _load_pack(db: AsyncSession, pack_id: str) -> ContentPack:
    result = await db.execute(
        select(ContentPack)
        .options(selectinload(ContentPack.questions))
        .where(ContentPack.id == pack_id)
    )
    pack = result.scalar_one_or_none()
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    pack.questions.sort(key=lambda q: q.sort_order)
    return pack
