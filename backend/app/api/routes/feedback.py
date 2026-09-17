from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.models.entities import User, Job
from app.services.feedback import record_feedback, get_user_feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _get_current_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    return user


@router.post("/jobs/{job_id}")
def submit_job_feedback(
    job_id: int,
    is_positive: bool = Body(..., embed=True),
    feedback_type: str = Body("relevant", embed=True),
    comment: str = Body("", embed=True),
    db: Session = Depends(get_db)
):
    user = _get_current_user(db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada")
    fb = record_feedback(
        db,
        user_id=user.id,
        job_id=job_id,
        is_positive=is_positive,
        feedback_type=feedback_type,
        comment=comment
    )
    return {"status": "ok", "feedback_id": fb.id, "job_id": job_id, "is_positive": fb.is_positive}


@router.get("/jobs/{job_id}")
def fetch_job_feedback(job_id: int, db: Session = Depends(get_db)):
    user = _get_current_user(db)
    return get_user_feedback(db, user.id, job_id) or {"feedback": None}
