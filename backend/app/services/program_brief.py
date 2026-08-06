from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProgramBrief, User
from app.services.grounding import load_grounding


async def get_active_brief(db: AsyncSession) -> ProgramBrief | None:
    return await db.scalar(
        select(ProgramBrief)
        .where(ProgramBrief.is_active.is_(True))
        .order_by(ProgramBrief.version.desc())
        .limit(1)
    )


def render_brief(brief: ProgramBrief) -> str:
    return "\n".join(
        [
            f"Program/topic: {brief.program_topic}",
            f"Target learners: {brief.target_learners}",
            f"Why OER is appropriate: {brief.oer_rationale}",
            f"Distribution channels: {brief.distribution_channels}",
            f"Learning objectives: {brief.learning_objectives}",
            f"Approved references and protocols: {brief.approved_references or 'None specified; follow local protocols.'}",
            f"Local context: {brief.local_context or 'Multiple training sites and professional cadres.'}",
            f"Preferred language: {brief.preferred_language or 'English'}",
            f"Restricted/excluded content: {brief.restricted_topics or 'No patient-specific prescribing or invented protocols.'}",
            f"Brand and teaching tone: {brief.brand_tone or 'Professional, clear, open, clinically safe.'}",
            f"Responsible educator: {brief.responsible_educator or 'Not specified'}",
            f"Brief version: {brief.version}",
        ]
    )


async def active_grounding(db: AsyncSession) -> str:
    brief = await get_active_brief(db)
    return render_brief(brief) if brief else load_grounding()


async def seed_initial_brief(db: AsyncSession, admin: User) -> ProgramBrief:
    existing = await get_active_brief(db)
    if existing:
        return existing

    brief = ProgramBrief(
        version=1,
        is_active=True,
        program_topic="Education in Anesthesia, Perioperative Medicine and Critical Care",
        target_learners=(
            "Anesthesia practitioners; perioperative health professionals including "
            "surgeons, physicians, nurses, clinical officers and students; trainers "
            "and other health-professions educators."
        ),
        oer_rationale=(
            "Education and coaching should be shared freely across professional cadres, "
            "trainers, trainees and different training sites, with open reflection and discussion."
        ),
        distribution_channels=(
            "Instagram, X, WhatsApp status, educational posters and videos, Zoom webinars, "
            "YouTube demonstrations, podcasts and customizable OER platforms."
        ),
        learning_objectives=(
            "Understand and remember basic resuscitation principles aligned to an OSCE curriculum; "
            "apply safe anesthesia and perioperative principles; apply postoperative care; "
            "prevent and manage postoperative pain."
        ),
        approved_references=(
            "Initial source: accademy3.txt OER design brief. Admin must add approved local, "
            "national and institutional clinical protocols before production publication."
        ),
        local_context=(
            "Content must work across different health centres, training sites, resource levels "
            "and professional cadres."
        ),
        preferred_language="English",
        restricted_topics=(
            "Do not invent drug doses, protocols, citations or patient facts. Do not provide "
            "patient-specific treatment orders. Do not include patient-identifying information."
        ),
        brand_tone=(
            "Professional, clinically precise, encouraging and accessible; Swiss-Nordic visual "
            "clarity; suitable for open medical education and social media."
        ),
        responsible_educator=admin.name,
        edited_by_id=admin.id,
    )
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return brief
