from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.config import settings
from app.core.logging import log_event

_scheduler: Optional[AsyncIOScheduler] = None
_is_paused: bool = False
_is_running_task: bool = False
_last_run: Optional[str] = None
_next_run: Optional[str] = None
_current_interval_minutes: int = settings.DEFAULT_SEARCH_FREQUENCY_MINUTES


async def _scheduled_job():
    global _is_running_task, _last_run, _next_run, _is_paused
    if _is_paused or _is_running_task:
        return

    _is_running_task = True
    _last_run = datetime.now(timezone.utc).isoformat()
    try:
        from app.services.pipeline import run_search_sync
        log_event("SCHEDULER_CYCLE_STARTED")
        # Executa síncrono em thread pool para não bloquear event loop
        result = await asyncio.to_thread(run_search_sync)
        log_event("SCHEDULER_CYCLE_FINISHED", **{k: v for k, v in result.items() if k != "discard_reasons"})
    except Exception as e:
        log_event("SCHEDULER_CYCLE_ERROR", error=str(e))
    finally:
        _is_running_task = False
        _next_run = (datetime.now(timezone.utc) + timedelta(minutes=_current_interval_minutes)).isoformat()


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler(interval_minutes: Optional[int] = None):
    global _current_interval_minutes, _next_run, _is_paused
    sched = get_scheduler()

    if interval_minutes is not None:
        _current_interval_minutes = max(5, interval_minutes)

    _is_paused = False

    if sched.get_job("job_hunter_agent"):
        sched.reschedule_job(
            "job_hunter_agent",
            trigger=IntervalTrigger(minutes=_current_interval_minutes)
        )
    else:
        sched.add_job(
            _scheduled_job,
            trigger=IntervalTrigger(minutes=_current_interval_minutes),
            id="job_hunter_agent",
            name="Hermes 24/7 Job Search Cycle",
            replace_existing=True
        )

    if not sched.running:
        sched.start()

    _next_run = (datetime.now(timezone.utc) + timedelta(minutes=_current_interval_minutes)).isoformat()
    log_event("SCHEDULER_STARTED", interval_minutes=_current_interval_minutes)


def pause_scheduler():
    global _is_paused
    _is_paused = True
    log_event("SCHEDULER_PAUSED")


def resume_scheduler():
    global _is_paused
    _is_paused = False
    log_event("SCHEDULER_RESUMED")


async def trigger_run_now() -> dict:
    """Executa ciclo de busca imediatamente."""
    from app.services.pipeline import run_search_sync
    return await asyncio.to_thread(run_search_sync)


def get_scheduler_status() -> dict:
    global _last_run, _next_run, _is_paused, _is_running_task, _current_interval_minutes
    sched = get_scheduler()
    job = sched.get_job("job_hunter_agent") if sched.running else None
    next_time = None
    if job and job.next_run_time:
        next_time = job.next_run_time.isoformat()
    elif _next_run:
        next_time = _next_run

    return {
        "running": sched.running and not _is_paused,
        "is_paused": _is_paused,
        "is_executing_cycle": _is_running_task,
        "last_search": _last_run,
        "next_search": next_time,
        "frequency_minutes": _current_interval_minutes
    }
