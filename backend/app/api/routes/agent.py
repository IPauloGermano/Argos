from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.core.config import settings
from app.core.database import get_db, get_redis_client
from app.models.entities import SearchPreferences, Job, JobMatch, Notification, SearchRun
from app.services.circuit_breaker import get_all_circuit_breakers
from app.services.scheduler import (
    get_scheduler_status, pause_scheduler, resume_scheduler, trigger_run_now
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _redis_get(key: str):
    try:
        r = get_redis_client()
        r.ping()
        return r.get(key)
    except Exception:
        return None


@router.get("/status")
def agent_status(db: Session = Depends(get_db)):
    sched_status = get_scheduler_status()
    last_stats = {}
    raw_stats = _redis_get("hermes:agent:last_stats")
    if raw_stats:
        try:
            last_stats = json.loads(raw_stats)
        except Exception:
            pass

    # Se não houver no Redis, busca a última execução do SearchRun no banco
    if not last_stats:
        last_run_db = db.scalar(select(SearchRun).order_by(SearchRun.id.desc()).limit(1))
        if last_run_db:
            last_stats = {
                "run_id": last_run_db.run_id,
                "found": last_run_db.jobs_found,
                "valid": last_run_db.valid_count,
                "deduplicated": last_run_db.duplicates_count,
                "discarded": last_run_db.discarded_count,
                "new": last_run_db.new_count,
                "updated": last_run_db.updated_count,
                "notified": last_run_db.notified_count,
                "errors": last_run_db.errors,
                "pages_crawled": last_run_db.pages_crawled
            }
            if not sched_status["last_search"]:
                sched_status["last_search"] = last_run_db.started_at.isoformat()

    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    freq = prefs.search_frequency_minutes if prefs else settings.DEFAULT_SEARCH_FREQUENCY_MINUTES
    enabled_sources = (prefs.enabled_sources if prefs and prefs.enabled_sources else None) or [
        s.strip() for s in settings.JOB_SOURCES.split(",") if s.strip()
    ]

    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    active_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "active")) or 0

    is_executing = sched_status["is_executing_cycle"]
    try:
        r = get_redis_client()
        if r.get("hermes:agent:is_running") == "1":
            is_executing = True
    except Exception:
        pass

    return {
        "running": sched_status["running"],
        "is_paused": sched_status["is_paused"],
        "is_executing_cycle": is_executing,
        "last_search": sched_status["last_search"],
        "next_search": sched_status["next_search"],
        "frequency_minutes": freq,
        "sources": enabled_sources,
        "last_stats": last_stats,
        "jobs_total": total_jobs,
        "jobs_active": active_jobs,
        "circuit_breakers": get_all_circuit_breakers()
    }


@router.post("/run")
async def agent_run():
    """Dispara execução imediata da busca em todas as fontes."""
    try:
        from app.workers.tasks import run_search_task
        task = run_search_task.delay()
        return {"triggered": True, "mode": "celery", "task_id": task.id}
    except Exception:
        # Executa via thread assíncrona local
        result = await trigger_run_now()
        return {"triggered": True, "mode": "standalone_scheduler", "result": result}


@router.post("/start")
def agent_start():
    resume_scheduler()
    try:
        r = get_redis_client()
        r.delete("hermes:agent:paused")
    except Exception:
        pass
    return {"running": True, "message": "Agente 24/7 iniciado / retomado"}


@router.post("/pause")
def agent_pause():
    pause_scheduler()
    try:
        r = get_redis_client()
        r.set("hermes:agent:paused", "1")
    except Exception:
        pass
    return {"running": False, "message": "Agente 24/7 pausado"}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), limit: int = 15):
    """Retorna histórico e telemetria detalhada das últimas execuções de busca."""
    runs = db.scalars(select(SearchRun).order_by(SearchRun.id.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "pages_crawled": r.pages_crawled,
            "jobs_found": r.jobs_found,
            "valid_count": r.valid_count,
            "duplicates_count": r.duplicates_count,
            "discarded_count": r.discarded_count,
            "new_count": r.new_count,
            "updated_count": r.updated_count,
            "notified_count": r.notified_count,
            "errors": r.errors or [],
            "source_stats": r.source_stats or {},
            "discard_reasons": r.discard_reasons or {}
        }
        for r in runs
    ]


@router.get("/metrics")
def agent_metrics(db: Session = Depends(get_db)):
    """Métricas consolidadas de observabilidade do agente."""
    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    active_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "active")) or 0
    ghost_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "potential_ghost")) or 0
    closed_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "closed")) or 0

    # Vagas por fonte
    sources_count = db.execute(
        select(Job.source, func.count(Job.id)).group_by(Job.source)
    ).all()
    by_source = {src: count for src, count in sources_count}

    # Notificações enviadas
    total_notifications = db.scalar(
        select(func.count(Notification.id)).where(Notification.status == "sent")
    ) or 0

    # Agregação de execuções
    total_runs = db.scalar(select(func.count(SearchRun.id))) or 0
    total_duplicates = db.scalar(select(func.sum(SearchRun.duplicates_count))) or 0
    total_discarded = db.scalar(select(func.sum(SearchRun.discarded_count))) or 0
    total_pages = db.scalar(select(func.sum(SearchRun.pages_crawled))) or 0

    return {
        "jobs": {
            "total": total_jobs,
            "active": active_jobs,
            "potential_ghost": ghost_jobs,
            "closed": closed_jobs,
            "by_source": by_source
        },
        "telemetry": {
            "total_runs": total_runs,
            "total_pages_crawled": total_pages,
            "total_duplicates_detected": total_duplicates,
            "total_discarded": total_discarded,
            "notifications_sent": total_notifications
        },
        "circuit_breakers": get_all_circuit_breakers()
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Job.id))) or 0
    relevant = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.score >= 70)) or 0
    best = db.scalar(select(func.max(JobMatch.score))) or 0
    sent = db.scalar(select(func.count(Notification.id)).where(Notification.status == "sent")) or 0
    
    sched = get_scheduler_status()
    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    freq = prefs.search_frequency_minutes if prefs else 60

    recent = db.execute(
        select(Job, JobMatch).outerjoin(JobMatch, JobMatch.job_id == Job.id)
        .order_by(Job.id.desc()).limit(8)
    ).all()

    return {
        "jobs_today": total,
        "relevant": relevant,
        "best_score": best,
        "notifications_sent": sent,
        "last_search": sched["last_search"],
        "next_search": sched["next_search"],
        "running": sched["running"],
        "frequency_minutes": freq,
        "recent": [
            {
                "id": j.id,
                "uuid": j.uuid,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "work_mode": j.work_mode,
                "source": j.source,
                "score": m.score if m else None,
                "reasoning": (m.reasoning if m else []) or []
            }
            for j, m in recent
        ]
    }
