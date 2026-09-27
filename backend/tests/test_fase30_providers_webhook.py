"""FASE 30+: regressão para webhook secret, Vagas fallback, Lever parcial, fuzzy narrowing."""
import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as dbmod
from app.core.database import Base, get_db
from app.core.config import settings
import app.main as mainmod


@pytest.fixture()
def client():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    def _override():
        s = S()
        try:
            yield s
        finally:
            s.close()

    mainmod.app.dependency_overrides[get_db] = _override
    yield TestClient(mainmod.app, raise_server_exceptions=False)
    mainmod.app.dependency_overrides.pop(get_db, None)


def _update(chat_id="1", text="/teste"):
    return {"update_id": 1, "message": {"message_id": 1, "chat": {"id": int(chat_id)},
            "from": {"id": int(chat_id), "first_name": "T"}, "text": text}}


def test_webhook_without_secret_allows_local(client, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
    r = client.post("/api/telegram/webhook", json=_update())
    assert r.status_code == 200 and r.json()["ok"] is True


def test_webhook_with_secret_enforces_header(client, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "s3cr3t")
    r = client.post("/api/telegram/webhook", json=_update())
    assert r.status_code == 401
    r2 = client.post("/api/telegram/webhook", json=_update(),
                     headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert r2.status_code == 401
    r3 = client.post("/api/telegram/webhook", json=_update(),
                     headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"})
    assert r3.status_code == 200 and r3.json()["ok"] is True


def test_webhook_forged_pause_does_not_pause_scheduler(client, monkeypatch):
    """Sem secret, atacante ainda só afeta o próprio usuário; com secret, 401."""
    from app.services import scheduler as sched
    sched.resume_scheduler()
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "s3cr3t")
    r = client.post("/api/telegram/webhook", json=_update(chat_id="999", text="/pausar"))
    assert r.status_code == 401
    assert sched.get_scheduler_status()["is_paused"] is False
    # Com secret válido, o comando é processado (Cenário A legítimo)
    r2 = client.post("/api/telegram/webhook", json=_update(chat_id="999", text="/pausar"),
                     headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"})
    assert r2.status_code == 200
    assert sched.get_scheduler_status()["is_paused"] is True
    sched.resume_scheduler()
    assert sched.get_scheduler_status()["is_paused"] is False


def test_vagas_english_slug_falls_back_to_pt():
    from app.providers.jobs.vagas import VagasComJobSource

    pt_html = """
    <html><body><ul>
    <li class="vaga"><a class="link-detalhes-vaga" href="/vagas/v123/dev">Dev Python</a>
    <span class="empresa">Acme</span><span class="vaga-local">Remoto</span></li>
    </ul></body></html>
    """
    empty_html = "<html><body><ul></ul></body></html>"

    def handler(request):
        if "backend-developer" in str(request.url):
            return httpx.Response(200, text=empty_html)
        return httpx.Response(200, text=pt_html)

    src = VagasComJobSource(timeout=10, max_pages=1)
    src.rate_limit_delay_seconds = 0

    async def _go():
        import app.providers.jobs.vagas as vm
        orig = httpx.AsyncClient
        vm.httpx.AsyncClient = lambda **k: orig(transport=httpx.MockTransport(handler))
        try:
            return await src.search({"desired_roles": ["Backend Developer"], "locations": ["Brasil"]})
        finally:
            vm.httpx.AsyncClient = orig

    jobs = asyncio.run(_go())
    assert len(jobs) == 1 and jobs[0].title == "Dev Python"
    assert src.last_status == "success"


def test_lever_404_board_is_skipped_not_failure():
    from app.providers.jobs import greenhouse_lever as gl

    assert "spotify" in gl.DEFAULT_LEVER_BOARDS
    assert "nubank" not in gl.DEFAULT_LEVER_BOARDS

    def handler(request):
        url = str(request.url)
        if "lever.co" in url:
            return httpx.Response(404, text='{"ok":false}')
        return httpx.Response(200, json={"jobs": []})

    from app.providers.jobs.greenhouse_lever import CorporateATSJobSource
    src = CorporateATSJobSource(timeout=10, max_pages=1)
    src.rate_limit_delay_seconds = 0
    assert src.lever_partial is True

    async def _go():
        import app.providers.jobs.greenhouse_lever as glm
        orig = httpx.AsyncClient
        real = httpx.AsyncClient
        glm.httpx.AsyncClient = lambda **k: real(transport=httpx.MockTransport(handler))
        try:
            return await src.search({"desired_roles": ["ZZZ-NoMatch"], "locations": []})
        finally:
            glm.httpx.AsyncClient = orig

    jobs = asyncio.run(_go())
    assert jobs == []
    # 404s não contaram como failure: breaker continua CLOSED
    assert src.circuit_breaker.state == "CLOSED"


def test_fuzzy_narrowing_recall_and_reduction():
    from app.services.dedup import company_blocking_tokens, are_jobs_duplicate

    # Recall: duplicata real compartilha token de empresa -> candidata
    toks = company_blocking_tokens("Tech Solutions Ltda")
    assert "tech" in toks and "solutions" in toks
    ok, _ = are_jobs_duplicate(
        {"title": "Desenvolvedor Python", "company": "Tech Solutions", "location": "Remoto", "url": "https://a/1"},
        {"title": "Dev Python", "company": "Tech Solutions LTDA", "location": "Remoto", "url": "https://b/2"},
    )
    assert ok is True
    # Distinct: sem token em comum
    assert company_blocking_tokens("Companhia Novaomega Inexistente").isdisjoint(
        company_blocking_tokens("Tech Solutions"))
