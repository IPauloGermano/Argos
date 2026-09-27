from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import require_admin_token
from app.models.entities import User, WeeklyReport
from app.services.reports import generate_weekly_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_current_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    return user


@router.get("/weekly")
def get_latest_weekly_report(db: Session = Depends(get_db)):
    user = _get_current_user(db)
    rep = db.scalar(
        select(WeeklyReport)
        .where(WeeklyReport.user_id == user.id)
        .order_by(WeeklyReport.id.desc())
        .limit(1)
    )
    if not rep:
        # Gera o primeiro relatório caso ainda não exista
        return generate_weekly_report(db, user.id, top_limit=10)

    return {
        "report_id": rep.id,
        "week_start": rep.week_start.isoformat() if rep.week_start else None,
        "week_end": rep.week_end.isoformat() if rep.week_end else None,
        "summary": {
            "total_analyzed": rep.total_jobs_analyzed,
            "compatible": rep.total_compatible,
            "new": rep.total_new,
            "remote": rep.total_remote,
            "hybrid": rep.total_hybrid,
            "onsite": rep.total_onsite,
            "internships": rep.total_internships,
        },
        "top_jobs": rep.top_jobs or []
    }


@router.post("/weekly/generate", dependencies=[Depends(require_admin_token)])
def create_weekly_report(top_limit: int = 10, db: Session = Depends(get_db)):
    user = _get_current_user(db)
    return generate_weekly_report(db, user.id, top_limit=top_limit, force_new=True)
