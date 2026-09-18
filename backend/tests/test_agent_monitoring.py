from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import get_db, Base
from app.models.entities import SearchRun, SearchPreferences

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_agent_status_resolves_last_search_from_redis(monkeypatch):
    test_iso = "2026-09-18T00:30:00+00:00"
    monkeypatch.setattr("app.api.routes.agent._redis_get", lambda k: test_iso if "last_run" in k else None)

    r = client.get("/api/agent/status")
    assert r.status_code == 200
    data = r.json()
    assert data["last_search"] == test_iso


def test_agent_status_resolves_last_search_from_search_run(monkeypatch):
    monkeypatch.setattr("app.api.routes.agent._redis_get", lambda k: None)
    now = datetime.now(timezone.utc)
    started = now - timedelta(minutes=25)
    finished = now - timedelta(minutes=24)

    with TestingSession() as s:
        # Cria preferência com frequência de 60 minutos
        s.query(SearchPreferences).delete()
        s.query(SearchRun).delete()
        s.add(SearchPreferences(user_id=1, search_frequency_minutes=60))
        
        run = SearchRun(
            run_id="test-run-123",
            started_at=started,
            finished_at=finished,
            status="completed",
            jobs_found=10,
            valid_count=5,
            new_count=3,
        )
        s.add(run)
        s.commit()

    r = client.get("/api/agent/status")
    assert r.status_code == 200
    data = r.json()
    assert data["last_search"] is not None
    # Deve refletir o término da última verificação
    assert data["last_search"] == finished.isoformat()
    # Próxima busca deve ser aproximadamente finished + 60 min
    assert data["next_search"] is not None
    next_dt = datetime.fromisoformat(data["next_search"])
    expected_next = finished + timedelta(minutes=60)
    assert abs((next_dt - expected_next).total_seconds()) < 5

    # Dashboard também deve conter as mesmas informações
    rd = client.get("/api/agent/dashboard")
    assert rd.status_code == 200
    dash_data = rd.json()
    assert dash_data["last_search"] == finished.isoformat()
    assert dash_data["next_search"] == data["next_search"]


def test_agent_status_paused_clears_next_search(monkeypatch):
    now = datetime.now(timezone.utc)
    with TestingSession() as s:
        s.query(SearchPreferences).delete()
        s.query(SearchRun).delete()
        s.add(SearchPreferences(user_id=1, search_frequency_minutes=30))
        run = SearchRun(
            run_id="test-run-paused",
            started_at=now,
            finished_at=now,
            status="completed",
        )
        s.add(run)
        s.commit()

    # Simula agente pausado
    from app.services import scheduler
    monkeypatch.setattr(scheduler, "_is_paused", True)

    r = client.get("/api/agent/status")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] is False
    assert data["is_paused"] is True
    assert data["next_search"] is None
