from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from uuid import uuid4
from app.core.config import settings
from app.core.security import require_admin_token
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


def _resolve_agent_monitoring(db: Session) -> dict:
    sched_status = get_scheduler_status()
    is_paused = sched_status.get("is_paused", False)
    try:
        r = get_redis_client()
        if r.get("hermes:agent:paused") == "1":
            is_paused = True
    except Exception:
        pass

    is_executing = sched_status.get("is_executing_cycle", False)
    try:
        r = get_redis_client()
        if r.get("hermes:agent:is_running") == "1":
            is_executing = True
    except Exception:
        pass

    # Checa também se no banco há SearchRun recente (< 15 min) com status 'running'
    if not is_executing:
        active_run = db.scalar(
            select(SearchRun)
            .where(SearchRun.status == "running")
            .where(SearchRun.started_at > datetime.now(timezone.utc) - timedelta(minutes=15))
            .limit(1)
        )
        if active_run:
            is_executing = True

    # 1. Recupera timestamp da última verificação (last_search)
    last_search = _redis_get("hermes:agent:last_run")
    last_run_db = None

    if not last_search:
        last_run_db = db.scalar(select(SearchRun).order_by(SearchRun.id.desc()).limit(1))
        if last_run_db and (last_run_db.finished_at or last_run_db.started_at):
            dt = last_run_db.finished_at or last_run_db.started_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            last_search = dt.isoformat()
        elif sched_status.get("last_search"):
            last_search = sched_status["last_search"]

    # 2. Recupera estatísticas da última verificação (last_stats)
    last_stats = {}
    raw_stats = _redis_get("hermes:agent:last_stats")
    if raw_stats:
        try:
            last_stats = json.loads(raw_stats)
        except Exception:
            pass

    if not last_stats:
        if last_run_db is None:
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
                "errors": last_run_db.errors or [],
                "pages_crawled": last_run_db.pages_crawled,
                "source_stats": last_run_db.source_stats or {},
                "discard_reasons": last_run_db.discard_reasons or {},
            }

    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    freq = prefs.search_frequency_minutes if prefs else settings.DEFAULT_SEARCH_FREQUENCY_MINUTES

    # 3. Calcula next_search com precisão
    next_search = None
    running = not is_paused
    if running:
        now_utc = datetime.now(timezone.utc)
        if is_executing:
            next_search = (now_utc + timedelta(minutes=freq)).isoformat()
        elif last_search:
            try:
                dt_str = last_search.replace("Z", "+00:00")
                last_dt = datetime.fromisoformat(dt_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                expected_next = last_dt + timedelta(minutes=freq)
                if expected_next > now_utc:
                    next_search = expected_next.isoformat()
                else:
                    next_search = now_utc.isoformat()
            except Exception:
                next_search = sched_status.get("next_search")
        else:
            next_search = sched_status.get("next_search") or (now_utc + timedelta(minutes=freq)).isoformat()

    return {
        "running": running,
        "is_paused": is_paused,
        "is_executing_cycle": is_executing,
        "last_search": last_search,
        "next_search": next_search,
        "frequency_minutes": freq,
        "last_stats": last_stats,
        "prefs": prefs,
    }


@router.get("/status")
def agent_status(db: Session = Depends(get_db)):
    info = _resolve_agent_monitoring(db)
    prefs = info["prefs"]
    enabled_sources = (prefs.enabled_sources if prefs and prefs.enabled_sources else None) or [
        s.strip() for s in settings.JOB_SOURCES.split(",") if s.strip()
    ]

    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    active_jobs = db.scalar(select(func.count(Job.id)).where(Job.status == "active")) or 0

    return {
        "running": info["running"],
        "is_paused": info["is_paused"],
        "is_executing_cycle": info["is_executing_cycle"],
        "last_search": info["last_search"],
        "next_search": info["next_search"],
        "frequency_minutes": info["frequency_minutes"],
        "sources": enabled_sources,
        "last_stats": info["last_stats"],
        "jobs_total": total_jobs,
        "jobs_active": active_jobs,
        "circuit_breakers": get_all_circuit_breakers()
    }


@router.post("/run", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin_token)])
async def agent_run(background_tasks: BackgroundTasks):
    """Dispara execução imediata da busca em todas as fontes (não-bloqueante)."""
    try:
        r = get_redis_client()
        r.ping()
        from app.workers.tasks import run_search_task
        task = run_search_task.apply_async(retry=False)
        return {"triggered": True, "mode": "celery", "task_id": str(task.id), "status": "queued"}
    except Exception:
        # Fallback assíncrono em background sem prender a conexão HTTP
        run_uuid = str(uuid4())
        background_tasks.add_task(trigger_run_now)
        return {"triggered": True, "mode": "background_task", "run_id": run_uuid, "status": "accepted"}


@router.post("/start", dependencies=[Depends(require_admin_token)])
def agent_start():
    resume_scheduler()
    try:
        r = get_redis_client()
        r.delete("hermes:agent:paused")
    except Exception:
        pass
    return {"running": True, "message": "Agente 24/7 iniciado / retomado"}


@router.post("/pause", dependencies=[Depends(require_admin_token)])
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
    
    info = _resolve_agent_monitoring(db)

    recent = db.execute(
        select(Job, JobMatch).outerjoin(JobMatch, JobMatch.job_id == Job.id)
        .order_by(Job.id.desc()).limit(8)
    ).all()

    return {
        "jobs_today": total,
        "relevant": relevant,
        "best_score": best,
        "notifications_sent": sent,
        "last_search": info["last_search"],
        "next_search": info["next_search"],
        "running": info["running"],
        "frequency_minutes": info["frequency_minutes"],
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
