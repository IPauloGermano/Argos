from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.entities import JobFeedback, Job, JobMatch


def record_feedback(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    is_positive: bool,
    feedback_type: str = "relevant",
    comment: str = ""
) -> JobFeedback:
    """
    Registra feedback 👍 / 👎 de um usuário para uma vaga.
    Idempotente: se já existir, atualiza a avaliação.
    """
    fb = db.scalar(
        select(JobFeedback).where(
            JobFeedback.user_id == user_id,
            JobFeedback.job_id == job_id
        )
    )
    if fb:
        fb.is_positive = is_positive
        fb.feedback_type = feedback_type
        fb.comment = comment
    else:
        fb = JobFeedback(
            user_id=user_id,
            job_id=job_id,
            is_positive=is_positive,
            feedback_type=feedback_type,
            comment=comment
        )
        db.add(fb)

    # Ajuste controlado no score da vaga correspondente para este usuário
    # Não distorce excessivamente (limite de +/- 5%)
    job_match = db.scalar(
        select(JobMatch).where(
            JobMatch.job_id == job_id
        )
    )
    if job_match:
        delta = 5 if is_positive else -10
        new_score = max(0, min(100, job_match.score + delta))
        job_match.score = new_score

    db.commit()
    db.refresh(fb)
    return fb


def get_user_feedback(db: Session, user_id: int, job_id: int) -> Optional[dict]:
    """Retorna o feedback registrado pelo usuário para a vaga."""
    fb = db.scalar(
        select(JobFeedback).where(
            JobFeedback.user_id == user_id,
            JobFeedback.job_id == job_id
        )
    )
    if not fb:
        return None
    return {
        "id": fb.id,
        "is_positive": fb.is_positive,
        "feedback_type": fb.feedback_type,
        "comment": fb.comment,
        "created_at": fb.created_at.isoformat() if fb.created_at else None
    }
