from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as dbmod
from app.core.database import Base
from app.models.entities import (
    Job,
    JobMatch,
    JobChangelog,
    Notification,
    JobFeedback,
    UserFavorite,
    SearchPreferences,
    User,
    CandidateProfile,
)
import app.main as mainmod
from app.services.cleanup import purge_expired_jobs, purge_example_jobs

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


def test_purge_expired_jobs_removes_old_jobs():
    now = datetime.now(timezone.utc)
    old_70d = now - timedelta(days=70)
    recent_10d = now - timedelta(days=10)

    with TestingSession() as s:
        # 1. Vaga antiga com published_at > 60 dias (deve ser deletada)
        j1 = Job(
            title="Old Published Job",
            company="Company A",
            status="active",
            content_hash="hash-1",
            published_at=old_70d,
            discovered_at=old_70d,
        )
        # 2. Vaga recente com published_at recente (deve ser mantida)
        j2 = Job(
            title="Recent Published Job",
            company="Company B",
            status="active",
            content_hash="hash-2",
            published_at=recent_10d,
            discovered_at=recent_10d,
        )
        # 3. Vaga antiga sem published_at, mas com discovered_at > 60 dias (deve ser deletada)
        j3 = Job(
            title="Old Unknown Date Job",
            company="Company C",
            status="active",
            content_hash="hash-3",
            published_at=None,
            discovered_at=old_70d,
        )
        # 4. Vaga recente sem published_at, com discovered_at recente (deve ser mantida)
        j4 = Job(
            title="Recent Unknown Date Job",
            company="Company D",
            status="active",
            content_hash="hash-4",
            published_at=None,
            discovered_at=recent_10d,
        )
        s.add_all([j1, j2, j3, j4])
        s.commit()
        j1_id, j2_id, j3_id, j4_id = j1.id, j2.id, j3.id, j4.id

        # Adiciona match para j1
        u = User(name="User Test", email="test@local")
        s.add(u)
        s.commit()
        prof = CandidateProfile(user_id=u.id)
        s.add(prof)
        s.commit()
        s.add(JobMatch(job_id=j1_id, profile_id=prof.id, score=80))
        s.commit()

        # Executa purga com limite de 60 dias
        purged = purge_expired_jobs(s, max_age_days=60)
        assert purged == 2

        remaining_ids = set(s.scalars(select(Job.id)).all())
        assert j2_id in remaining_ids
        assert j4_id in remaining_ids
        assert j1_id not in remaining_ids
        assert j3_id not in remaining_ids

        # Verifica que o JobMatch de j1 foi apagado junto
        assert s.scalar(select(JobMatch).where(JobMatch.job_id == j1_id)) is None


def test_purge_expired_jobs_preserves_favorited_jobs():
    now = datetime.now(timezone.utc)
    old_80d = now - timedelta(days=80)

    with TestingSession() as s:
        u = User(name="User Fav", email="fav@local")
        s.add(u)
        s.commit()

        j_old_fav = Job(
            title="Very Old But Favorited",
            company="Company Fav",
            status="active",
            content_hash="hash-fav-1",
            published_at=old_80d,
            discovered_at=old_80d,
        )
        j_old_unfav = Job(
            title="Very Old Unfavorited",
            company="Company Unfav",
            status="active",
            content_hash="hash-unfav-2",
            published_at=old_80d,
            discovered_at=old_80d,
        )
        s.add_all([j_old_fav, j_old_unfav])
        s.commit()
        fav_id = j_old_fav.id
        unfav_id = j_old_unfav.id

        # Usuário favoritou a j_old_fav
        s.add(UserFavorite(user_id=u.id, job_id=fav_id))
        s.commit()

        # Executa limpeza
        purged = purge_expired_jobs(s, max_age_days=60)
        assert purged == 1

        remaining = set(s.scalars(select(Job.id)).all())
        assert fav_id in remaining
        assert unfav_id not in remaining


def test_purge_expired_jobs_cleans_dependent_tables():
    now = datetime.now(timezone.utc)
    old_50d = now - timedelta(days=50)

    with TestingSession() as s:
        u = User(name="User Dept", email="dept@local")
        s.add(u)
        s.commit()
        prof = CandidateProfile(user_id=u.id)
        s.add(prof)
        s.commit()

        job = Job(
            title="Job With Many Dependents",
            company="Corp",
            status="active",
            content_hash="hash-dept",
            published_at=old_50d,
            discovered_at=old_50d,
        )
        s.add(job)
        s.commit()
        jid = job.id

        # Adiciona dependências em todas as tabelas filhas
        s.add(JobMatch(job_id=jid, profile_id=prof.id, score=90))
        s.add(JobChangelog(job_id=jid, field_name="salary", change_type="salary"))
        s.add(Notification(user_id=u.id, job_id=jid, channel="telegram"))
        s.add(JobFeedback(user_id=u.id, job_id=jid, is_positive=True))
        s.commit()

        # Purga com limite de 30 dias
        purged = purge_expired_jobs(s, max_age_days=30)
        assert purged == 1

        # Todas as tabelas filhas devem estar limpas sem erro de integridade
        assert s.scalar(select(Job).where(Job.id == jid)) is None
        assert s.scalar(select(JobMatch).where(JobMatch.job_id == jid)) is None
        assert s.scalar(select(JobChangelog).where(JobChangelog.job_id == jid)) is None
        assert s.scalar(select(Notification).where(Notification.job_id == jid)) is None
        assert s.scalar(select(JobFeedback).where(JobFeedback.job_id == jid)) is None


def test_purge_cleans_excluded_jobs_list():
    now = datetime.now(timezone.utc)
    old_90d = now - timedelta(days=90)

    with TestingSession() as s:
        u = User(name="User Pref", email="pref@local")
        s.add(u)
        s.commit()

        j = Job(
            title="Old Excluded Job",
            company="Company Ex",
            status="active",
            content_hash="hash-ex",
            published_at=old_90d,
            discovered_at=old_90d,
        )
        s.add(j)
        s.commit()
        jid = j.id

        prefs = SearchPreferences(user_id=u.id, excluded_jobs=[jid, 9999])
        s.add(prefs)
        s.commit()

        purge_expired_jobs(s, max_age_days=60)

        s.refresh(prefs)
        # O ID da vaga deletada deve ter sido removido, e o ID 9999 preservado
        assert jid not in prefs.excluded_jobs
        assert 9999 in prefs.excluded_jobs


def test_purge_safety_guards():
    with TestingSession() as s:
        # max_age_days inválido ou zero não deve deletar nada
        assert purge_expired_jobs(s, max_age_days=0) == 0
        assert purge_expired_jobs(s, max_age_days=-10) == 0
        assert purge_expired_jobs(s, max_age_days=None) == 0


def test_cleanup_expired_jobs_api_endpoint():
    now = datetime.now(timezone.utc)
    old_70d = now - timedelta(days=70)

    with TestingSession() as s:
        j = Job(
            title="Old Job For API Cleanup",
            company="API Corp",
            status="active",
            content_hash="hash-api-cleanup",
            published_at=old_70d,
            discovered_at=old_70d,
        )
        s.add(j)
        s.commit()
        jid = j.id

    r = client.post("/api/jobs/cleanup-expired")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["purged_count"] >= 1

    with TestingSession() as s:
        assert s.scalar(select(Job).where(Job.id == jid)) is None


def test_purge_example_jobs_removes_mock_and_demo():
    with TestingSession() as s:
        # Vaga mock
        j1 = Job(
            title="Backend Developer",
            company="Empresa Alpha 1",
            source="mock",
            url="https://example.com/jobs/mock-1",
            content_hash="mock-hash-1",
            status="active"
        )
        # Vaga de teste com [TESTE] no título
        j2 = Job(
            title="[TESTE] Desenvolvedor Python",
            company="Vagas Testes",
            source="gupy",
            url="https://bondy-demo.gupy.io/job/123",
            content_hash="demo-hash-2",
            status="active"
        )
        # Vaga real válida que NÃO deve ser apagada
        j3 = Job(
            title="Desenvolvedor Python Júnior",
            company="Empresa Real Tech",
            source="linkedin",
            url="https://linkedin.com/jobs/view/999",
            content_hash="real-hash-3",
            status="active"
        )
        s.add_all([j1, j2, j3])
        s.commit()
        j1_id, j2_id, j3_id = j1.id, j2.id, j3.id

    with TestingSession() as s:
        purged = purge_example_jobs(s)
        assert purged == 2
        assert s.scalar(select(Job).where(Job.id == j1_id)) is None
        assert s.scalar(select(Job).where(Job.id == j2_id)) is None
        assert s.scalar(select(Job).where(Job.id == j3_id)) is not None

