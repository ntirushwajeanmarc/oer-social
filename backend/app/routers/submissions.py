from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import ContentPack, Question, Submission, User
from app.schemas import AnswerRequest, SubmissionOut
from app.services import openai_service
from app.services.program_brief import active_grounding
from app.services.security import get_current_user

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("/questions/{question_id}", response_model=SubmissionOut)
async def submit_answer(
    question_id: str,
    payload: AnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Submission:
    result = await db.execute(
        select(Question)
        .options(selectinload(Question.pack))
        .where(Question.id == question_id)
    )
    question = result.scalar_one_or_none()
    if not question or not question.pack or question.pack.status != "published":
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        domain_grounding = await active_grounding(db)
        learner_profile = (
            f"Education level: {user.education_level or 'not provided'}\n"
            f"Clinical experience: {user.experience_years} years\n"
            f"Learning goals: {user.learning_goals or 'not provided'}\n"
            f"Topics of interest: {user.topics_of_interest or 'not provided'}\n"
            f"Preferred language: {user.preferred_language or 'English'}\n"
            f"Local training context and resources: {user.local_context or 'not provided'}"
        )
        score, feedback = await openai_service.grade_answer(
            question=question.prompt,
            rubric=question.rubric,
            answer=payload.answer,
            case_study=question.pack.case_study,
            cadre=user.cadre,
            learner_profile=learner_profile,
            domain_grounding=domain_grounding,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OpenAI error: {exc}") from exc

    submission = Submission(
        user_id=user.id,
        question_id=question.id,
        answer=payload.answer.strip(),
        score=score,
        feedback=feedback,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission


@router.get("/me", response_model=list[SubmissionOut])
async def my_submissions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Submission]:
    result = await db.execute(
        select(Submission).where(Submission.user_id == user.id).order_by(Submission.created_at.desc())
    )
    return list(result.scalars().all())
