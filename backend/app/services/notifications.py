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


def try_claim_notification(db: Session, user_id: int, job_id: int, channel: str, event_type: str = "new_match") -> bool:
    """
    Tenta reservar atomicamente o envio da notificação via UniqueConstraint.
    Garante que entre 2 ou mais processos concorrentes, apenas 1 realiza o envio real.
    Estratégia insert-first: tenta inserir diretamente e trata IntegrityError,
    eliminando a janela check-then-insert.
    """
    notif = Notification(
        user_id=user_id,
        job_id=job_id,
        channel=channel,
        event_type=event_type,
        status="processing",
        attempts=1,
    )
    try:
        db.add(notif)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        # Já existe intenção lógica: permite retry apenas se anterior falhou
        existing = db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.job_id == job_id,
                Notification.channel == channel,
            )
        )
        if existing is None:
            return False
        if existing.status in ("sent", "processing"):
            return False
        existing.status = "processing"
        existing.attempts = (existing.attempts or 0) + 1
        try:
            db.commit()
            return True
        except Exception:
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
    error: str = "",
    event_type: str = "new_match",
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
        from datetime import timedelta
        notif = Notification(
            user_id=user_id,
            job_id=job_id,
            channel=channel,
            event_type=event_type,
            status=status,
            error=error[:2000],
            last_error=error[:2000],
            attempts=1,
            next_attempt_at=(datetime.now(timezone.utc) + timedelta(minutes=5 * 1)) if status == "failed" else None,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None
        )
        db.add(notif)
    else:
        notif.status = status
        notif.error = error[:2000]
        notif.last_error = error[:2000]
        if status == "sent":
            notif.sent_at = datetime.now(timezone.utc)
            notif.next_attempt_at = None
        elif status == "failed":
            from datetime import timedelta
            notif.attempts = (notif.attempts or 0) + 1
            backoff_min = min(60, 2 ** min(notif.attempts, 6))
            notif.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_min)

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

    # Snapshot de prefs/user ANTES do claim (o claim faz commit e expira objetos ORM).
    try:
        user_id = int(user.id)
        user_email = str(getattr(user, "email", "") or "")
        user_tg = str(getattr(user, "telegram_chat_id", "") or "")
    except Exception:
        return
    try:
        tg_enabled = bool(getattr(prefs, "telegram_enabled", False))
        tg_token = getattr(prefs, "telegram_bot_token", None)
        tg_chat = getattr(prefs, "telegram_chat_id", None)
        dc_enabled = bool(getattr(prefs, "discord_enabled", False))
        dc_webhook = getattr(prefs, "discord_webhook_url", None)
        em_enabled = bool(getattr(prefs, "email_enabled", False))
        digest_mode = getattr(prefs, "email_digest_mode", "immediately") or "immediately"
    except Exception:
        return

    # 1. Telegram
    if tg_enabled:
        if try_claim_notification(db, user_id, job_id, "telegram"):
            token = tg_token
            chat_id = tg_chat or user_tg
            if chat_id:
                try:
                    provider = TelegramProvider(token=token) if token else TelegramProvider()
                    job_with_id = {**job_dict, "id": job_id}
                    await provider.send_job_notification(chat_id, job_with_id, score, reasoning)
                    record_notification_result(db, user_id=user_id, job_id=job_id, channel="telegram", status="sent")
                    log_event("NOTIFICATION_SENT", channel="telegram", job_id=job_id)
                except Exception as e:
                    record_notification_result(db, user_id=user_id, job_id=job_id, channel="telegram",
                                               status="failed", error=str(e))
                    log_event("NOTIFICATION_FAILED", channel="telegram", job_id=job_id, error=str(e)[:200])
            else:
                record_notification_result(db, user_id=user_id, job_id=job_id, channel="telegram",
                                           status="failed", error="chat_id not configured")

    # 2. Discord
    if dc_enabled:
        if try_claim_notification(db, user_id, job_id, "discord"):
            webhook_url = dc_webhook
            try:
                provider = DiscordProvider(webhook_url=webhook_url) if webhook_url else DiscordProvider()
                await provider.send_job_notification(job_dict, score, reasoning)
                record_notification_result(db, user_id=user_id, job_id=job_id, channel="discord", status="sent")
                log_event("NOTIFICATION_SENT", channel="discord", job_id=job_id)
            except Exception as e:
                record_notification_result(db, user_id=user_id, job_id=job_id, channel="discord",
                                           status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="discord", job_id=job_id, error=str(e)[:200])

    # 3. E-mail
    if em_enabled and digest_mode == "immediately":
        if try_claim_notification(db, user_id, job_id, "email"):
            try:
                await EmailProvider().send_job_notification(user_email, job_dict, score, reasoning)
                record_notification_result(db, user_id=user_id, job_id=job_id, channel="email", status="sent")
                log_event("NOTIFICATION_SENT", channel="email", job_id=job_id)
            except Exception as e:
                record_notification_result(db, user_id=user_id, job_id=job_id, channel="email",
                                           status="failed", error=str(e))
                log_event("NOTIFICATION_FAILED", channel="email", job_id=job_id, error=str(e)[:200])
