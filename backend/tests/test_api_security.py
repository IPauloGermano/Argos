import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
import app.main as mainmod
from app.core.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_db():
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def setup_sec_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    s = TestingSession()
    from app.models.entities import User, SearchPreferences
    u = User(id=1, email="test@hermes.local", name="Test User")
    s.add(u)
    p = SearchPreferences(id=1, user_id=1, telegram_chat_id="12345", telegram_bot_token="test_token")
    s.add(p)
    s.commit()
    s.close()
    mainmod.app.dependency_overrides[get_db] = _override_db
    yield
    mainmod.app.dependency_overrides.pop(get_db, None)


def test_cors_authorized_and_unauthorized():
    client = TestClient(mainmod.app, raise_server_exceptions=False)
    
    # Origem autorizada (default localhost:3000)
    res_allowed = client.options(
        "/api/jobs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Origem não autorizada (malicious site)
    res_blocked = client.options(
        "/api/jobs",
        headers={
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    # Não deve ter o header permitindo a origem maliciosa
    assert res_blocked.headers.get("access-control-allow-origin") is None


from unittest.mock import AsyncMock, patch

def test_auth_token_enforcement(monkeypatch):
    client = TestClient(mainmod.app, raise_server_exceptions=False)
    secret = "test-super-secret-token"
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", secret)

    with patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock), \
         patch("app.services.scheduler.trigger_run_now", new_callable=AsyncMock, return_value={"status": "ok"}), \
         patch("app.api.routes.agent.trigger_run_now", new_callable=AsyncMock, return_value={"status": "ok"}), \
         patch("app.services.pipeline.run_search_sync", return_value={"status": "completed"}):
        protected_endpoints = [
            ("POST", "/api/agent/run"),
            ("POST", "/api/agent/start"),
            ("POST", "/api/agent/pause"),
            ("POST", "/api/jobs/cleanup-expired"),
            ("POST", "/api/notifications/test", {"channel": "telegram"}),
            ("POST", "/api/telegram/simulate", None, {"chat_id": "12345", "text": "/start"}),
        ]

        for item in protected_endpoints:
            method = item[0]
            url = item[1]
            json_body = item[2] if len(item) > 2 else None
            params = item[3] if len(item) > 3 else None

            # 1. Sem token -> 401
            r_no_token = client.request(method, url, json=json_body, params=params)
            assert r_no_token.status_code == 401, f"Expected 401 for {url}, got {r_no_token.status_code}"

            # 2. Token inválido -> 403
            r_bad_token = client.request(
                method, url, json=json_body, params=params,
                headers={"Authorization": "Bearer wrong-token"}
            )
            assert r_bad_token.status_code == 403, f"Expected 403 for {url}, got {r_bad_token.status_code}"

            # 3. Token válido via Bearer -> deve prosseguir (não ser 401 ou 403)
            r_good_bearer = client.request(
                method, url, json=json_body, params=params,
                headers={"Authorization": f"Bearer {secret}"}
            )
            assert r_good_bearer.status_code not in (401, 403), f"Bearer failed for {url}: {r_good_bearer.status_code}"

            # 4. Token válido via X-API-Key -> deve prosseguir (não ser 401 ou 403)
            r_good_header = client.request(
                method, url, json=json_body, params=params,
                headers={"X-API-Key": secret}
            )
            assert r_good_header.status_code not in (401, 403), f"X-API-Key failed for {url}: {r_good_header.status_code}"


def test_telegram_simulate_invalid_chat_id(monkeypatch):
    client = TestClient(mainmod.app, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "AGENT_API_TOKEN", "")
    r = client.post("/api/telegram/simulate", params={"chat_id": "not-a-number"})
    assert r.status_code == 400
