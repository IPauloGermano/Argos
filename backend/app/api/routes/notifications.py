from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import require_admin_token
from app.core.rate_limit import limit_notify_test
from app.models.entities import Notification, Job, User, SearchPreferences
from app.services.notifications import notify_job

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class TestNotificationRequest(BaseModel):
    channel: str = "telegram"  # telegram | discord | email


@router.get("")
def list_notifications(db: Session = Depends(get_db), limit: int = 50):
    rows = db.execute(
        select(Notification, Job.title, Job.company)
        .outerjoin(Job, Job.id == Notification.job_id)
        .order_by(Notification.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": n.id,
            "job_id": n.job_id,
            "job_title": t,
            "company": c,
            "channel": n.channel,
            "status": n.status,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            "error": n.error
        }
        for n, t, c in rows
    ]


@router.post("/test", dependencies=[Depends(require_admin_token), Depends(limit_notify_test)])
async def test_notification(body: TestNotificationRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).order_by(User.id).limit(1))
    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    if not user or not prefs:
        raise HTTPException(400, "Perfil ou preferências ainda não inicializados")

    sample_job = {
        "title": "Backend Developer Python / FastAPI (Teste Hermes)",
        "company": "Hermes Tech",
        "area": "Tecnologia",
        "location": "Remoto - Brasil",
        "work_mode": "remote",
        "employment_type": "CLT",
        "source": "Teste",
        "url": "https://github.com/nousresearch/hermes-agent"
    }

    try:
        if body.channel == "telegram":
            from app.providers.telegram.client import TelegramProvider
            chat_id = prefs.telegram_chat_id or user.telegram_chat_id
            token = prefs.telegram_bot_token
            p = TelegramProvider(token=token) if token else TelegramProvider()
            await p.send_job_notification(chat_id or "", sample_job, 98, ["✓ Vaga de teste enviada com sucesso"])
            return {"status": "ok", "message": "Mensagem de teste enviada via Telegram"}

        elif body.channel == "discord":
            from app.providers.discord.client import DiscordProvider
            p = DiscordProvider(webhook_url=prefs.discord_webhook_url)
            await p.send_job_notification(sample_job, 98, ["✓ Embed de teste enviado com sucesso ao Discord"])
            return {"status": "ok", "message": "Embed de teste enviado via Discord"}

        else:
            raise HTTPException(400, f"Canal não suportado para teste: {body.channel}")
    except Exception as e:
        raise HTTPException(500, f"Falha ao enviar notificação de teste: {str(e)}")
