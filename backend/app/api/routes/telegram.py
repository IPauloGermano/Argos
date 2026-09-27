from __future__ import annotations
from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_admin_token
from app.services.telegram_bot import TelegramBotService

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(update: dict = Body(...), db: Session = Depends(get_db)):
    """Recebe atualizações do webhook oficial do Telegram."""
    try:
        result = TelegramBotService.handle_update(update, db)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/simulate", dependencies=[Depends(require_admin_token)])
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
