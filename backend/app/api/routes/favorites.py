from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.models.entities import User, Job
from app.services.favorites import add_favorite, remove_favorite, list_favorites, is_favorite

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def _get_current_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    return user


@router.get("")
def get_favorites(db: Session = Depends(get_db)):
    user = _get_current_user(db)
    return list_favorites(db, user.id)


@router.post("/{job_id}")
def create_favorite(job_id: int, notes: str = "", db: Session = Depends(get_db)):
    user = _get_current_user(db)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada")
    fav = add_favorite(db, user.id, job_id, notes=notes)
    return {"status": "ok", "favorite_id": fav.id, "job_id": job_id}


@router.delete("/{job_id}")
def delete_favorite(job_id: int, db: Session = Depends(get_db)):
    user = _get_current_user(db)
    removed = remove_favorite(db, user.id, job_id)
    return {"status": "ok", "removed": removed}
