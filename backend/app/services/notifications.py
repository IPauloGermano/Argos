from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.entities import Notification
from app.core.logging import log_event


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


def try_claim_notification(db: Session, user_id: int, job_id: int, channel: str) -> bool:
    """
    Tenta reservar atomicamente o envio da notificação via UniqueConstraint.
    Garante que entre 2 ou mais processos concorrentes, apenas 1 realiza o envio real.
    """
    existing = db.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.job_id == job_id,
            Notification.channel == channel
        )
    )
    if existing:
        if existing.status in ("sent", "processing"):
            return False
        # Permite retry se o status anterior era failed
        existing.status = "processing"
        try:
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    notif = Notification(
        user_id=user_id,
        job_id=job_id,
        channel=channel,
        status="processing"
    )
    try:
        db.add(notif)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    except Exception:
        db.rollback()
        return False


def record_notification_result(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    channel: str,
    status: str,
    error: str = ""
) -> Optional[Notification]:
    """Atualiza o resultado da notificação (sent ou failed) com segurança transacional."""
    notif = db.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.job_id == job_id,
            Notification.channel == channel
        )
    )
    if not notif:
        notif = Notification(
            user_id=user_id,
            job_id=job_id,
            channel=channel,
            status=status,
            error=error[:2000],
            sent_at=datetime.now(timezone.utc) if status == "sent" else None
        )
        db.add(notif)
    else:
        notif.status = status
        notif.error = error[:2000]
        if status == "sent":
            notif.sent_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(notif)
        return notif
    except Exception:
        db.rollback()
        return notif


# Alias de retrocompatibilidade
record_notification = record_notification_result


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
    Envio multi-canal com concorrência segura (lock atômico no banco via UniqueConstraint)
    e isolamento de falhas para não interromper outros canais ou perder a vaga salva.
    """
    from app.providers.telegram.client import TelegramProvider
    from app.providers.email.client import EmailProvider
    from app.providers.discord.client import DiscordProvider

    # 1. Telegram
    if getattr(prefs, "telegram_enabled", False):
        if try_claim_notification(db, user.id, job_id, "telegram"):
            token = getattr(prefs, "telegram_bot_token", None)
            chat_id = getattr(prefs, "telegram_chat_id", None) or getattr(user, "telegram_chat_id", None)
            if chat_id:
                try:
                    provider = TelegramProvider(token=token) if token else TelegramProvider()
                    job_with_id = {**job_dict, "id": job_id}
                    await provider.send_job_notification(chat_id, job_with_id, score, reasoning)
                    record_notification_result(db, user_id=user.id, job_id=job_id, channel="telegram", status="sent")
                    log_event("NOTIFICATION_SENT", channel="telegram", job_id=job_id)
                except Exception as e:
                    record_notification_result(db, user_id=user.id, job_id=job_id, channel="telegram",
                                               status="failed", error=str(e))
                    log_event("NOTIFICATION_FAILED", channel="telegram", job_id=job_id, error=str(e)[:200])
            else:
                record_notification_result(db, user_id=user.id, job_id=job_id, channel="telegram",
                                           status="failed", error="chat_id not configured")

    # 2. Discord
    if getattr(prefs, "discord_enabled", False):
        if try_claim_notification(db, user.id, job_id, "discord"):
            webhook_url = getattr(prefs, "discord_webhook_url", None)
            try:
                provider = DiscordProvider(webhook_url=webhook_url) if webhook_url else DiscordProvider()
                await provider.send_job_notification(job_dict, score, reasoning)
                record_notification_result(db, user_id=user.id, job_id=job_id, channel="discord", status="sent")
                log_event("NOTIFICATION_SENT", channel="discord", job_id=job_id)
            except Exception as e:
                record_notification_result(db, user_id=user.id, job_id=job_id, channel="discord",
                                           status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="discord", job_id=job_id, error=str(e)[:200])

    # 3. E-mail
    digest_mode = getattr(prefs, "email_digest_mode", "immediately") or "immediately"
    if getattr(prefs, "email_enabled", False) and digest_mode == "immediately":
        if try_claim_notification(db, user.id, job_id, "email"):
            try:
                await EmailProvider().send_job_notification(user.email, job_dict, score, reasoning)
                record_notification_result(db, user_id=user.id, job_id=job_id, channel="email", status="sent")
                log_event("NOTIFICATION_SENT", channel="email", job_id=job_id)
            except Exception as e:
                record_notification_result(db, user_id=user.id, job_id=job_id, channel="email",
                                           status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="email", job_id=job_id, error=str(e)[:200])
