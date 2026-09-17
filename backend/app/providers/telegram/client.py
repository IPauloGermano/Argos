from __future__ import annotations
import html
from datetime import datetime
from typing import Optional
import httpx
from app.core.config import settings


def format_job_message(job: dict, score: int, reasoning: list[str]) -> str:
    """Formata o card de notificação da vaga com HTML seguro."""
    pub = job.get("published_at")
    if isinstance(pub, datetime):
        pub_str = pub.strftime("%d/%m/%Y")
    elif pub:
        pub_str = str(pub)[:10]
    else:
        pub_str = "Recente"

    title = html.escape(str(job.get("title", "Oportunidade")))
    company = html.escape(str(job.get("company", "Empresa")))
    area = html.escape(str(job.get("area", "Tecnologia")))
    location = html.escape(str(job.get("location", "Brasil")))
    work_mode = html.escape(str(job.get("work_mode", "N/A"))).capitalize()
    emp_type = html.escape(str(job.get("employment_type", "N/A"))).upper()
    source = html.escape(str(job.get("source", "Web"))).upper()
    url = job.get("url", "")

    bullets = "\n".join(f"• {html.escape(r)}" for r in (reasoning or [])[:3])
    
    msg = (
        f"🎯 <b>OPORTUNIDADE EM DESTAQUE ({score}% Match)</b>\n\n"
        f"💼 <b>{title}</b>\n"
        f"🏢 <b>Empresa:</b> {company}\n"
        f"📍 <b>Local:</b> {location} ({work_mode})\n"
        f"📋 <b>Contrato:</b> {emp_type} | <b>Área:</b> {area}\n"
        f"📅 <b>Publicação:</b> {pub_str} | <b>Fonte:</b> {source}\n"
    )
    if bullets:
        msg += f"\n💡 <b>Motivos do Match:</b>\n{bullets}\n"
    if url:
        msg += f"\n🔗 <a href='{url}'>Clique aqui para ver a vaga completa</a>\n"

    return msg[:4000]


def build_job_inline_keyboard(job: dict) -> dict:
    """Cria os botões inline para interação rápida no Telegram."""
    job_id = job.get("id") or 0
    url = job.get("url") or "https://hermes.local"
    return {
        "inline_keyboard": [
            [{"text": "🔗 Abrir Vaga no Navegador", "url": url}],
            [
                {"text": "⭐ Favoritar", "callback_data": f"fav:{job_id}"},
                {"text": "🚫 Ignorar", "callback_data": f"ignore:{job_id}"}
            ],
            [
                {"text": "👍 Relevante", "callback_data": f"fb_pos:{job_id}"},
                {"text": "👎 Não Relevante", "callback_data": f"fb_neg:{job_id}"}
            ]
        ]
    }


class TelegramProvider:
    """Provedor de notificações via Telegram Bot API."""

    def __init__(self, token: str = "", timeout: int = 15, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.timeout = timeout
        self.transport = transport
        self.last_payload: Optional[dict] = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def send_job_notification(
        self,
        chat_id: str,
        job: dict,
        score: int,
        reasoning: list[str]
    ) -> dict:
        if not self.enabled:
            raise RuntimeError("Telegram não configurado (TELEGRAM_BOT_TOKEN vazio)")
        if not chat_id:
            raise RuntimeError("telegram_chat_id do usuário não configurado")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": format_job_message(job, score, reasoning),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": build_job_inline_keyboard(job)
        }
        self.last_payload = payload

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
