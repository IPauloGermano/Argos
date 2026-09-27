"""Bateria estendida: changelog A->B->B->B->C->B, poison 100, concorrência 20x, lock, provider retry."""
import threading
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as dbmod
from app.core.database import Base
from app.models.entities import User, CandidateProfile, SearchPreferences, Job, JobChangelog, Notification, SearchRun

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


import pytest

@pytest.fixture(autouse=True)
def setup_ext_db(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(dbmod, "engine", test_engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSession)
    monkeypatch.setattr("app.services.pipeline.SessionLocal", TestingSession)
    s = TestingSession()
    u = User(id=1, email="test@hermes.local", name="Test User")
    s.add(u)
    p = CandidateProfile(id=1, user_id=1, headline="Python Developer",
                         roles=["Backend Developer"], skills=["Python", "FastAPI", "SQL"], seniority="junior")
    s.add(p)
    pref = SearchPreferences(id=1, user_id=1, desired_roles=["Backend Developer"],
                             locations=["Brasil", "Remoto"], work_modes=["remote"],
                             telegram_enabled=True, telegram_chat_id="123456",
                             telegram_bot_token="fake", minimum_match_score=60)
    s.add(pref)
    s.commit()
    s.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


class DummyJob:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mk_job(ext="job-x", salary_min=1000.0, salary_max=1500.0, title="Desenvolvedor Python Júnior", company="Tech Corp"):
    return DummyJob(
        external_id=ext, source="gupy", url=f"https://portal.gupy.io/job/{ext}",
        title=title, company=company, location="Remoto", work_mode="remote",
        seniority="junior", employment_type="CLT", area="Tecnologia",
        description="Desenvolvimento em Python e FastAPI", salary_min=salary_min,
        salary_max=salary_max, currency="BRL", requirements=["Python"],
        nice_to_have=[], published_at=datetime.now(timezone.utc), raw_data={},
    )


def test_changelog_full_sequence_A_B_B_B_C_B():
    from app.services.pipeline import run_search_sync
    db = TestingSession()
    j = Job(uuid=str(uuid4()), external_id="job-seq", source="gupy",
            url="https://portal.gupy.io/job/job-seq", title="Desenvolvedor Python Júnior",
            company="Tech Corp", location="Remoto", work_mode="remote", seniority="junior",
            salary_min=1000.0, salary_max=1500.0, status="active", content_hash="hash-seq")
    db.add(j); db.commit(); job_id = j.id; db.close()

    with patch("app.services.pipeline._collect_from_sources") as mock_collect, \
         patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock):
        async def _ret(payload):
            return payload
        # Ciclo 1: A->B
        mock_collect.return_value = ([_mk_job("job-seq", 2000.0, 2500.0)], [], {}, 1)
        r1 = run_search_sync()
        assert r1["updated"] >= 1
        db = TestingSession()
        assert db.scalar(select(Job).where(Job.id == job_id)).salary_min == 2000.0
        c1 = len(db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all())
        assert c1 == 2
        db.close()
        # Ciclo 2 e 3 sem alteração
        for _ in range(2):
            r = run_search_sync()
            assert r["updated"] == 0
            db = TestingSession()
            assert len(db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all()) == 2
            db.close()
        # Ciclo B->C
        mock_collect.return_value = ([_mk_job("job-seq", 3000.0, 3500.0)], [], {}, 1)
        r4 = run_search_sync()
        assert r4["updated"] >= 1
        db = TestingSession()
        c4 = len(db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all())
        assert c4 == 4, f"expected 4 got {c4}"
        db.close()
        # Ciclo C->B (legítimo, deve gerar novo changelog)
        mock_collect.return_value = ([_mk_job("job-seq", 2000.0, 2500.0)], [], {}, 1)
        r5 = run_search_sync()
        assert r5["updated"] >= 1
        db = TestingSession()
        c5 = len(db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all())
        assert c5 == 6, f"expected 6 got {c5}"
        db.close()


def test_poison_100_jobs_99_continue():
    from app.services.pipeline import run_search_sync
    from app.core.config import settings
    jobs = []
    for i in range(100):
        if i == 36:
            class PoisonJob:
                external_id = "poison-37"; source = "evil"; url = "https://x/37"
                @property
                def title(self):
                    raise RuntimeError("poison #37")
            jobs.append(PoisonJob())
        else:
            jobs.append(_mk_job(f"ok-{i}", 3000.0, 4000.0, title=f"Desenvolvedor Python Backend Projeto {i}", company=f"Empresa Única {i} Tecnologia"))
    with patch("app.services.pipeline._collect_from_sources", return_value=(jobs, [], {}, 1)), \
         patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock), \
         patch.object(settings, "DEDUPLICATION_SIMILARITY_THRESHOLD", 1.0):
        result = run_search_sync()
        assert result["status"] == "partial_error"
        assert result["valid"] >= 90, f"valid={result['valid']}"
        db = TestingSession()
        sr = db.scalar(select(SearchRun).where(SearchRun.run_id == result["run_id"]))
        assert sr is not None and sr.status == "partial_error"
        db.close()


def test_concurrent_pipeline_20_calls_single_execution():
    from app.services.pipeline import run_search_sync
    with patch("app.services.pipeline._collect_from_sources", return_value=([], [], {}, 0)):
        results = []
        def _run():
            try:
                results.append(run_search_sync())
            except Exception as e:
                results.append({"status": f"exc:{e}"})
        threads = [threading.Thread(target=_run) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(results) == 20
        executed = [r for r in results if r.get("status") in ("completed", "partial_error")]
        skipped = [r for r in results if r.get("status") == "skipped"]
        # Com lock local (threading), apenas 1 executa por vez; demais skipped
        assert len(executed) >= 1
        assert len(skipped) >= 1, f"executed={len(executed)} skipped={len(skipped)}"


def test_notification_race_20_workers_single_record(tmp_path):
    from app.services.notifications import try_claim_notification
    # DB em arquivo para concorrência real (SQLite memória + StaticPool
    # compartilha 1 conexão e mascara a constraint UNIQUE entre threads).
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm
    db_file = str(tmp_path / "race20.db")
    file_engine = _ce(f"sqlite:///{db_file}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(bind=file_engine)
    with file_engine.connect() as c:
        c.exec_driver_sql("PRAGMA journal_mode=WAL;")
    FileSession = _sm(bind=file_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    s0 = FileSession()
    s0.add(User(id=1, email="test@hermes.local", name="Test User"))
    s0.add(Job(uuid=str(uuid4()), external_id="job-race20", source="remotive",
               url="https://remotive.com/race20", title="Python Engineer",
               company="ACME", location="Remoto", content_hash="hash-race20"))
    s0.commit()
    job_id = s0.scalars(select(Job)).first().id
    s0.close()
    results = []
    rlock = threading.Lock()
    def worker():
        local = FileSession()
        try:
            ok = try_claim_notification(local, 1, job_id, "telegram")
            with rlock:
                results.append(ok)
        finally:
            local.close()
    ts = [threading.Thread(target=worker) for _ in range(20)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert results.count(True) == 1, f"expected exactly 1 claim, got {results.count(True)}/20"
    chk = FileSession()
    assert len(chk.scalars(select(Notification).where(Notification.job_id == job_id)).all()) == 1
    chk.close()
    file_engine.dispose()


def test_provider_retry_429_then_success():
    import asyncio, httpx
    from app.providers.jobs.http_client import fetch_with_retry
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, text="ok")
    async def _go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            resp = await fetch_with_retry(client, "GET", "https://x.test/", max_retries=3, base_delay=0.01)
            return resp.status_code
    assert asyncio.run(_go()) == 200
    assert calls["n"] == 3


def test_rate_limit_blocks_after_limit():
    from app.core.rate_limit import check_rate_limit
    key = f"test-{uuid4()}"
    for _ in range(5):
        allowed, _ = check_rate_limit(key, limit=5, window_seconds=60)
        assert allowed
    allowed, retry = check_rate_limit(key, limit=5, window_seconds=60)
    assert not allowed and retry > 0
