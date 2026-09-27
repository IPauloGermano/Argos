from __future__ import annotations
import hmac
from fastapi import APIRouter, Depends, Body, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_admin_token
from app.core.rate_limit import limit_notify_test
from app.services.telegram_bot import TelegramBotService

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


def _check_telegram_webhook_secret(request: Request) -> None:
    """Valida X-Telegram-Bot-Api-Secret-Token quando TELEGRAM_WEBHOOK_SECRET configurado.

    Compatível com o Telegram real (que reenvia o secret). Sem secret
    configurado (dev/teste), permite para não quebrar fluxos locais.
    """
    expected = (settings.TELEGRAM_WEBHOOK_SECRET or "").strip()
    if not expected:
        return
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "WEBHOOK_UNAUTHORIZED", "message": "Invalid webhook secret."}},
        )


@router.post("/webhook")
async def telegram_webhook(request: Request, update: dict = Body(...), db: Session = Depends(get_db)):
    """Recebe atualizações do webhook oficial do Telegram (com secret-token)."""
    _check_telegram_webhook_secret(request)
    try:
        result = TelegramBotService.handle_update(update, db)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/simulate", dependencies=[Depends(require_admin_token), Depends(limit_notify_test)])
async def telegram_simulate(
    chat_id: str = "123456",
    text: str = "/start",
    callback_data: str = "",
    db: Session = Depends(get_db)
):
    """
    Endpoint de teste e simulação de usuário do Telegram para QA,
    permitindo testar comandos e botões sem precisar de conexão externa com a internet.
    """
    try:
        numeric_chat_id = int(chat_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="chat_id must be a numeric integer string.")

    if callback_data:
        update = {
            "update_id": 999,
            "callback_query": {
                "id": "cb_test_123",
                "from": {"id": numeric_chat_id, "first_name": "QA Tester"},
                "message": {"chat": {"id": numeric_chat_id}},
                "data": callback_data
            }
        }
    else:
        update = {
            "update_id": 999,
            "message": {
                "message_id": 1001,
                "chat": {"id": numeric_chat_id},
                "from": {"id": numeric_chat_id, "first_name": "QA Tester"},
                "text": text
            }
        }

    res = TelegramBotService.handle_update(update, db)
    return {"status": "ok", "response": res}
