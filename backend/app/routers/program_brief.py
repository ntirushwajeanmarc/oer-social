from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ProgramBrief, User
from app.schemas import ProgramBriefOut, ProgramBriefUpdate
from app.services.program_brief import get_active_brief
from app.services.security import require_admin

router = APIRouter(prefix="/program-brief", tags=["program brief"])


@router.get("/current", response_model=ProgramBriefOut)
async def current_brief(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProgramBrief:
    brief = await get_active_brief(db)
    if not brief:
        raise HTTPException(status_code=404, detail="Program brief not configured")
    return brief


@router.get("/history", response_model=list[ProgramBriefOut])
async def brief_history(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ProgramBrief]:
    result = await db.execute(
        select(ProgramBrief).order_by(ProgramBrief.version.desc())
    )
    return list(result.scalars().all())


@router.put("/current", response_model=ProgramBriefOut)
async def update_brief(
    payload: ProgramBriefUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProgramBrief:
    current = await get_active_brief(db)
    next_version = (current.version + 1) if current else 1

    await db.execute(
        update(ProgramBrief)
        .where(ProgramBrief.is_active.is_(True))
        .values(is_active=False)
    )
    brief = ProgramBrief(
        version=next_version,
        is_active=True,
        edited_by_id=admin.id,
        **payload.model_dump(),
    )
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return brief
