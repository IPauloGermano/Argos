from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.entities import Notification
from app.core.logging import log_event


def record_notification(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    channel: str,
    status: str,
    error: str = ""
) -> Notification:
    """Registra histórico de notificação enviada ou falha."""
    n = Notification(
        user_id=user_id,
        job_id=job_id,
        channel=channel,
        status=status,
        error=error[:2000],
        sent_at=datetime.now(timezone.utc) if status == "sent" else None
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def was_already_notified(db: Session, user_id: int, job_id: int, channel: str) -> bool:
    """Verifica se o usuário já recebeu com sucesso a notificação desta vaga no canal."""
    existing = db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.job_id == job_id,
            Notification.channel == channel,
            Notification.status == "sent"
        )
    )
    return existing is not None


async def notify_job(
    db: Session,
    *,
    user,
    job_dict: dict,
    job_id: int,
    score: int,
    reasoning: list[str],
    prefs
) -> None:
    """
    Envio multi-canal com idempotência estrita (1 vaga -> 1 notificação por canal)
    e isolamento de falhas para não interromper os demais canais.
    """
    from app.providers.telegram.client import TelegramProvider
    from app.providers.email.client import EmailProvider
    from app.providers.discord.client import DiscordProvider

    # 1. Telegram
    if getattr(prefs, "telegram_enabled", False):
        if not was_already_notified(db, user.id, job_id, "telegram"):
            token = getattr(prefs, "telegram_bot_token", None)
            chat_id = getattr(prefs, "telegram_chat_id", None) or getattr(user, "telegram_chat_id", None)
            if chat_id:
                try:
                    provider = TelegramProvider(token=token) if token else TelegramProvider()
                    job_with_id = {**job_dict, "id": job_id}
                    await provider.send_job_notification(chat_id, job_with_id, score, reasoning)
                    record_notification(db, user_id=user.id, job_id=job_id, channel="telegram", status="sent")
                    log_event("NOTIFICATION_SENT", channel="telegram", job_id=job_id)
                except Exception as e:
                    record_notification(db, user_id=user.id, job_id=job_id, channel="telegram",
                                        status="failed", error=str(e))
                    log_event("NOTIFICATION_FAILED", channel="telegram", job_id=job_id, error=str(e)[:200])

    # 2. Discord
    if getattr(prefs, "discord_enabled", False):
        if not was_already_notified(db, user.id, job_id, "discord"):
            webhook_url = getattr(prefs, "discord_webhook_url", None)
            try:
                provider = DiscordProvider(webhook_url=webhook_url) if webhook_url else DiscordProvider()
                await provider.send_job_notification(job_dict, score, reasoning)
                record_notification(db, user_id=user.id, job_id=job_id, channel="discord", status="sent")
                log_event("NOTIFICATION_SENT", channel="discord", job_id=job_id)
            except Exception as e:
                record_notification(db, user_id=user.id, job_id=job_id, channel="discord",
                                    status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="discord", job_id=job_id, error=str(e)[:200])

    # 3. E-mail
    digest_mode = getattr(prefs, "email_digest_mode", "immediately") or "immediately"
    if getattr(prefs, "email_enabled", False) and digest_mode == "immediately":
        if not was_already_notified(db, user.id, job_id, "email"):
            try:
                await EmailProvider().send_job_notification(user.email, job_dict, score, reasoning)
                record_notification(db, user_id=user.id, job_id=job_id, channel="email", status="sent")
                log_event("NOTIFICATION_SENT", channel="email", job_id=job_id)
            except Exception as e:
                record_notification(db, user_id=user.id, job_id=job_id, channel="email",
                                    status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="email", job_id=job_id, error=str(e)[:200])
