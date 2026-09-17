from __future__ import annotations
from datetime import datetime, timezone
from app.workers.celery_app import celery_app


@celery_app.task(name="hermes.run_search", bind=True, max_retries=2)
def run_search_task(self):
    try:
        from app.services.pipeline import run_search_sync

        return run_search_sync()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="hermes.periodic_search_if_due")
def periodic_search_if_due():
    """Roda busca se passou search_frequency_minutes desde a última (e agente não pausado)."""
    from app.core.database import SessionLocal, get_redis_client
    from sqlalchemy import select
    from app.models.entities import SearchPreferences, User

    try:
        r = get_redis_client()
        if r.get("hermes:agent:paused") == "1":
            return {"skipped": "paused"}
        last = r.get("hermes:agent:last_run")
    except Exception:
        r = None
        last = None
    db = SessionLocal()
    try:
        prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
        freq = prefs.search_frequency_minutes if prefs else 60
        if last:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
                if elapsed < freq:
                    return {"skipped": "not_due", "elapsed_min": round(elapsed, 1)}
            except Exception:
                pass
        return run_search_task.delay().id
    finally:
        db.close()


def _digest_task(period: str, mode: str):
    from app.core.database import SessionLocal
    from sqlalchemy import select
    from app.models.entities import User, SearchPreferences, Job, JobMatch
    import asyncio

    db = SessionLocal()
    try:
        users = db.scalars(select(User)).all()
        sent = 0
        for user in users:
            prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
            if not prefs or not prefs.email_enabled or (prefs.email_digest_mode or "") != mode:
                continue
            rows = db.execute(
                select(Job, JobMatch).join(JobMatch, JobMatch.job_id == Job.id)
                .where(JobMatch.score >= (prefs.minimum_match_score or 0))
                .order_by(JobMatch.score.desc()).limit(30)
            ).all()
            items = [{"job": {"title": j.title, "company": j.company, "url": j.url}, "score": m.score}
                     for j, m in rows][:30]
            if not items:
                continue
            try:
                from app.providers.email.client import EmailProvider

                asyncio.run(EmailProvider().send_digest(user.email, items, period))
                sent += 1
            except Exception:
                continue
        return {"period": period, "sent": sent}
    finally:
        db.close()


@celery_app.task(name="hermes.hourly_digest")
def hourly_digest():
    return _digest_task("hourly", "hourly")


@celery_app.task(name="hermes.daily_digest")
def daily_digest():
    return _digest_task("daily", "daily")
