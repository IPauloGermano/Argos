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


@celery_app.task(name="hermes.dispatch_notification_outbox", bind=True, max_retries=3)
def dispatch_notification_outbox(self, batch_size: int = 50):
    """Dispatcher do outbox: envia pendentes com retry/backoff (at-least-once + dedupe)."""
    from app.core.database import SessionLocal
    from sqlalchemy import select
    from app.models.entities import Notification, User, SearchPreferences, Job
    from app.services.notifications import record_notification_result
    import asyncio

    db = SessionLocal()
    sent = failed = skipped = 0
    try:
        now = datetime.now(timezone.utc)
        pending = db.scalars(
            select(Notification)
            .where(Notification.status.in_(["pending", "failed"]))
            .where((Notification.next_attempt_at.is_(None)) | (Notification.next_attempt_at <= now))
            .order_by(Notification.id)
            .limit(batch_size)
        ).all()
        for n in pending:
            # Marca como enviando para evitar duplo envio entre workers
            if n.status == "pending":
                n.status = "sending"
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    skipped += 1
                    continue
            else:
                n.status = "sending"
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    skipped += 1
                    continue
            try:
                user = db.get(User, n.user_id)
                job = db.get(Job, n.job_id)
                prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == n.user_id))
                if not user or not job:
                    record_notification_result(db, user_id=n.user_id, job_id=n.job_id,
                                               channel=n.channel, status="failed", error="user/job missing")
                    failed += 1
                    continue
                job_dict = {"title": job.title, "company": job.company, "url": job.url,
                            "location": job.location, "id": job.id}
                if n.channel == "telegram":
                    from app.providers.telegram.client import TelegramProvider
                    chat_id = (prefs.telegram_chat_id if prefs else None) or user.telegram_chat_id
                    provider = TelegramProvider(token=(prefs.telegram_bot_token if prefs else None) or None) if (prefs and prefs.telegram_bot_token) else TelegramProvider()
                    asyncio.run(provider.send_job_notification(chat_id or "", job_dict, 80, ["Outbox retry"]))
                elif n.channel == "discord":
                    from app.providers.discord.client import DiscordProvider
                    provider = DiscordProvider(webhook_url=(prefs.discord_webhook_url if prefs else None) or None) if (prefs and prefs.discord_webhook_url) else DiscordProvider()
                    asyncio.run(provider.send_job_notification(job_dict, 80, ["Outbox retry"]))
                elif n.channel == "email":
                    from app.providers.email.client import EmailProvider
                    asyncio.run(EmailProvider().send_job_notification(user.email, job_dict, 80, ["Outbox retry"]))
                else:
                    raise ValueError(f"unknown channel {n.channel}")
                record_notification_result(db, user_id=n.user_id, job_id=n.job_id,
                                           channel=n.channel, status="sent")
                sent += 1
            except Exception as e:
                try:
                    record_notification_result(db, user_id=n.user_id, job_id=n.job_id,
                                               channel=n.channel, status="failed", error=str(e)[:500])
                except Exception:
                    pass
                failed += 1
        return {"sent": sent, "failed": failed, "skipped": skipped}
    finally:
        db.close()
