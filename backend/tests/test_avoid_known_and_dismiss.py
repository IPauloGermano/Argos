from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import httpx

import app.core.database as dbmod
from app.core.database import Base
from app.models.entities import Job, SearchPreferences, User
import app.main as mainmod
from app.services.validation import validate_job
from app.providers.jobs.gupy import GupyJobSource
from app.providers.jobs.remotive import RemotiveJobSource
from app.providers.jobs.weworkremotely import WeWorkRemotelyJobSource
from app.providers.jobs.linkedin import LinkedInJobSource

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override():
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    mainmod.app.dependency_overrides[dbmod.get_db] = _override
    yield
    mainmod.app.dependency_overrides.pop(dbmod.get_db, None)
    Base.metadata.drop_all(bind=engine)


client = TestClient(mainmod.app, raise_server_exceptions=False)


def test_validation_discards_user_excluded_job():
    job = {
        "id": 42,
        "url": "https://example.com/jobs/42",
        "title": "Senior Python Dev",
        "company": "Acme",
        "work_mode": "remote",
        "status": "active"
    }
    prefs = {"excluded_jobs": [42]}
    ok, reason = validate_job(job, prefs)
    assert not ok
    assert reason == "user_excluded_job"

    prefs_clean = {"excluded_jobs": [999]}
    ok, reason = validate_job(job, prefs_clean)
    assert ok


def test_api_dismiss_and_undismiss_job():
    # Cria uma vaga no banco
    with TestingSession() as s:
        j = Job(
            title="Backend Python Developer",
            company="Tech Corp",
            location="Remoto",
            work_mode="remote",
            status="active",
            content_hash="hash-12345",
            discovered_at=datetime.now(timezone.utc),
        )
        s.add(j)
        s.commit()
        s.refresh(j)
        job_id = j.id

    # 1. Lista deve conter a vaga inicialmente
    res = client.get("/api/jobs")
    assert res.status_code == 200
    job_ids = [item["id"] for item in res.json()]
    assert job_id in job_ids

    # 2. Usuário descarta a vaga via POST /api/jobs/{id}/dismiss
    r_dismiss = client.post(f"/api/jobs/{job_id}/dismiss")
    assert r_dismiss.status_code == 200
    assert r_dismiss.json()["dismissed"] is True

    # 3. GET /api/jobs padrão (exclude_dismissed=True) agora NÃO deve retornar a vaga
    res2 = client.get("/api/jobs")
    assert res2.status_code == 200
    job_ids2 = [item["id"] for item in res2.json()]
    assert job_id not in job_ids2

    # 4. GET /api/jobs com exclude_dismissed=false deve retornar a vaga marcada como is_dismissed=True
    res_all = client.get("/api/jobs?exclude_dismissed=false")
    assert res_all.status_code == 200
    found = next((item for item in res_all.json() if item["id"] == job_id), None)
    assert found is not None
    assert found["is_dismissed"] is True

    # 5. Restaura a vaga via POST /api/jobs/{id}/undismiss
    r_undismiss = client.post(f"/api/jobs/{job_id}/undismiss")
    assert r_undismiss.status_code == 200
    assert r_undismiss.json()["dismissed"] is False

    # 6. GET /api/jobs volta a listar a vaga
    res3 = client.get("/api/jobs")
    assert res3.status_code == 200
    job_ids3 = [item["id"] for item in res3.json()]
    assert job_id in job_ids3


def test_api_only_new_filter():
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=5)

    with TestingSession() as s:
        old_job = Job(
            title="Old Job",
            company="Old Corp",
            status="active",
            content_hash="hash-old-1",
            discovered_at=old_time,
            published_at=old_time,
        )
        new_job = Job(
            title="Fresh Job",
            company="New Corp",
            status="active",
            content_hash="hash-new-2",
            discovered_at=now,
            published_at=now,
        )
        s.add_all([old_job, new_job])
        s.commit()
        s.refresh(old_job)
        s.refresh(new_job)
        old_id = old_job.id
        new_id = new_job.id

    # Busca apenas novas
    res = client.get("/api/jobs?only_new=true")
    assert res.status_code == 200
    items = res.json()
    ids = [item["id"] for item in items]
    assert new_id in ids
    assert old_id not in ids


@pytest.mark.asyncio
async def test_remotive_skips_known_urls_and_ids(monkeypatch):
    source = RemotiveJobSource()
    fake_items = [
        {"id": 1, "title": "Dev Python", "company_name": "Co A", "url": "https://remotive.com/job/1"},
        {"id": 2, "title": "Dev Django", "company_name": "Co B", "url": "https://remotive.com/job/2"},
    ]

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"jobs": fake_items}

    async def fake_get(self, url, params=None, headers=None):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    # Com known_urls incluindo a vaga 1
    query = {
        "desired_roles": ["python"],
        "known_urls": {"https://remotive.com/job/1"},
        "known_ids": set(),
    }
    jobs = await source.search(query)
    assert len(jobs) == 1
    assert jobs[0].url == "https://remotive.com/job/2"


@pytest.mark.asyncio
async def test_gupy_skips_known_urls_and_ids(monkeypatch):
    source = GupyJobSource()
    fake_items = [
        {"id": 100, "name": "Engenheiro Python", "jobUrl": "https://gupy.io/job/100"},
        {"id": 200, "name": "Engenheiro Backend", "jobUrl": "https://gupy.io/job/200"},
    ]

    class FakeResponse:
        status_code = 200
        text = "<html></html>"
        def raise_for_status(self): pass

    async def fake_get(self, url, params=None, headers=None):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(source, "_parse_page", lambda html: (fake_items, len(fake_items)))

    # Informa que id '100' já é conhecido
    query = {
        "desired_roles": ["python"],
        "known_urls": set(),
        "known_ids": {"100"},
    }
    jobs = await source.search(query)
    assert len(jobs) == 1
    assert jobs[0].external_id == "200"

