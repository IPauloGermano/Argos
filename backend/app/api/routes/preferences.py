from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import require_admin_token
from app.models.entities import User, SearchPreferences
from app.schemas import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def _get_prefs(db: Session) -> SearchPreferences:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        user = User(name="Usuário", email="user@hermes.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
    if not prefs:
        prefs = SearchPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.get("", response_model=PreferencesOut)
def get_preferences(db: Session = Depends(get_db)):
    return _get_prefs(db)


@router.put("", response_model=PreferencesOut, dependencies=[Depends(require_admin_token)])
def update_preferences(body: PreferencesUpdate, db: Session = Depends(get_db)):
    prefs = _get_prefs(db)
    if body.email_digest_mode and body.email_digest_mode not in ("immediately", "hourly", "daily"):
        raise HTTPException(400, "email_digest_mode deve ser immediately|hourly|daily")

    data = body.model_dump(exclude_unset=True)
    if "min_salary" in data:
        min_s = data.pop("min_salary")
        if "minimum_salary" not in data and min_s is not None:
            data["minimum_salary"] = min_s
    if "max_salary" in data:
        max_s = data.pop("max_salary")
        if "maximum_salary" not in data and max_s is not None:
            data["maximum_salary"] = max_s

    for k, v in data.items():
        if hasattr(prefs, k):
            setattr(prefs, k, v)

    db.commit()
    db.refresh(prefs)

    # Se a frequência de busca foi alterada, reprograma o scheduler 24/7 dinamicamente
    if body.search_frequency_minutes is not None:
        try:
            from app.services.scheduler import start_scheduler
            start_scheduler(body.search_frequency_minutes)
        except Exception:
            pass

    # Se a idade máxima de vagas foi alterada, executa limpeza automática imediata
    if body.max_job_age_days is not None:
        try:
            from app.services.cleanup import purge_expired_jobs
            purge_expired_jobs(db, max_age_days=body.max_job_age_days)
        except Exception:
            pass

    return prefs

