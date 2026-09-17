from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from app.models.entities import UserFavorite, Job, JobMatch


def add_favorite(db: Session, user_id: int, job_id: int, notes: str = "") -> UserFavorite:
    """Adiciona uma vaga aos favoritos do usuário de forma idempotente."""
    existing = db.scalar(
        select(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.job_id == job_id
        )
    )
    if existing:
        if notes and existing.notes != notes:
            existing.notes = notes
            db.commit()
            db.refresh(existing)
        return existing

    fav = UserFavorite(user_id=user_id, job_id=job_id, notes=notes)
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return fav


def remove_favorite(db: Session, user_id: int, job_id: int) -> bool:
    """Remove uma vaga dos favoritos do usuário."""
    result = db.execute(
        delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.job_id == job_id
        )
    )
    db.commit()
    return (result.rowcount or 0) > 0


def is_favorite(db: Session, user_id: int, job_id: int) -> bool:
    """Verifica se uma vaga está favoritada pelo usuário."""
    fav = db.scalar(
        select(UserFavorite.id).where(
            UserFavorite.user_id == user_id,
            UserFavorite.job_id == job_id
        )
    )
    return fav is not None


def list_favorites(db: Session, user_id: int) -> list[dict]:
    """Retorna lista de vagas favoritadas com detalhes e pontuação."""
    rows = db.execute(
        select(UserFavorite, Job)
        .join(Job, UserFavorite.job_id == Job.id)
        .where(UserFavorite.user_id == user_id)
        .order_by(UserFavorite.id.desc())
    ).all()

    items = []
    for fav, job in rows:
        items.append({
            "favorite_id": fav.id,
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "work_mode": job.work_mode,
            "employment_type": job.employment_type,
            "url": job.url,
            "source": job.source,
            "notes": fav.notes,
            "favorited_at": fav.created_at.isoformat() if fav.created_at else None,
        })
    return items
