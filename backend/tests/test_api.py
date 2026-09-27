"""API integration com SQLite em memória (sobrescreve get_db)."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

import app.core.database as dbmod
from app.core.database import Base
import app.main as mainmod

import pytest


def _override():
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def setup_api_db():
    Base.metadata.create_all(bind=engine)
    mainmod.app.dependency_overrides[dbmod.get_db] = _override
    yield
    mainmod.app.dependency_overrides.pop(dbmod.get_db, None)


client = TestClient(mainmod.app, raise_server_exceptions=False)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["database"] == "ok"


def test_health_liveness():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_readiness_failure(monkeypatch):
    from unittest.mock import MagicMock
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("DB Connection Lost")
    monkeypatch.setattr(mainmod, "engine", mock_engine)

    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == "error"


def test_profile_crud():
    assert client.get("/api/profile").status_code == 200
    r = client.put("/api/profile", json={"headline": "Backend Dev", "skills": ["Python"]})
    assert r.status_code == 200 and r.json()["headline"] == "Backend Dev"


def test_preferences_update_and_validation():
    assert client.get("/api/preferences").status_code == 200
    r = client.put("/api/preferences", json={"minimum_match_score": 80, "search_frequency_minutes": 30})
    assert r.status_code == 200 and r.json()["minimum_match_score"] == 80
    assert client.put("/api/preferences", json={"email_digest_mode": "nope"}).status_code == 400


def test_jobs_list_empty_ok():
    r = client.get("/api/jobs")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_agent_status_and_dashboard():
    assert client.get("/api/agent/status").status_code == 200
    assert client.get("/api/agent/dashboard").status_code == 200


def test_notifications_list():
    assert client.get("/api/notifications").status_code == 200
