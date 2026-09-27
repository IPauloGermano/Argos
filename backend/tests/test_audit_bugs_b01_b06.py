import threading
import time
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as dbmod
from app.core.database import Base
from app.models.entities import User, CandidateProfile, SearchPreferences, Job, JobChangelog, Notification, SearchRun
from app.services.pipeline import run_search_sync
from app.services.notifications import notify_job

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def setup_b_suite_db(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    monkeypatch.setattr(dbmod, "engine", test_engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSession)
    monkeypatch.setattr("app.services.pipeline.SessionLocal", TestingSession)

    # Seed usuário, perfil e preferências padrão
    s = TestingSession()
    u = User(id=1, email="test@hermes.local", name="Test User")
    s.add(u)
    p = CandidateProfile(
        id=1,
        user_id=1,
        headline="Python Developer",
        roles=["Backend Developer", "Desenvolvedor Python"],
        skills=["Python", "FastAPI", "SQL"],
        seniority="junior"
    )
    s.add(p)
    pref = SearchPreferences(
        id=1,
        user_id=1,
        desired_roles=["Backend Developer"],
        locations=["Brasil", "Remoto"],
        work_modes=["remote"],
        telegram_enabled=True,
        telegram_chat_id="123456",
        telegram_bot_token="fake_token",
        minimum_match_score=60
    )
    s.add(pref)
    s.commit()
    s.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


class DummyJob:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_b01_no_duplicate_changelogs_multiple_cycles():
    """
    B-01: Verifica que alterações em uma vaga existente atualizam a entidade Job no banco
    e não geram registros de changelog duplicados ao longo de múltiplos ciclos.
    """
    db = TestingSession()
    # Cria uma vaga existente no banco com salário 1000
    initial_job = Job(
        uuid=str(uuid4()),
        external_id="job-100",
        source="gupy",
        url="https://portal.gupy.io/job/100",
        title="Desenvolvedor Python Júnior",
        company="Tech Corp",
        location="Remoto",
        work_mode="remote",
        seniority="junior",
        salary_min=1000.0,
        salary_max=1500.0,
        status="active",
        content_hash="hash-100"
    )
    db.add(initial_job)
    db.commit()
    job_id = initial_job.id
    db.close()

    # Vaga coletada traz novo salário: 2000
    mocked_job_update = DummyJob(
        external_id="job-100",
        source="gupy",
        url="https://portal.gupy.io/job/100",
        title="Desenvolvedor Python Júnior",
        company="Tech Corp",
        location="Remoto",
        work_mode="remote",
        seniority="junior",
        employment_type="CLT",
        area="Tecnologia",
        description="Desenvolvimento em Python e FastAPI",
        salary_min=2000.0,
        salary_max=2500.0,
        currency="BRL",
        requirements=["Python"],
        nice_to_have=[],
        published_at=datetime.now(timezone.utc),
        raw_data={}
    )

    with patch("app.services.pipeline._collect_from_sources", return_value=([mocked_job_update], [], {}, 1)), \
         patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock):

        # Ciclo 1: detecta alteração de 1000 -> 2000
        res1 = run_search_sync()
        assert res1["updated"] >= 1

        db = TestingSession()
        chgs_c1 = db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all()
        assert len(chgs_c1) == 2  # salary_min e salary_max
        updated_job = db.get(Job, job_id)
        assert updated_job.salary_min == 2000.0  # Job foi atualizado no banco!
        db.close()

        # Ciclo 2: mesma vaga coletada com 2000. NÃO pode gerar changelogs repetidos!
        res2 = run_search_sync()
        assert res2["updated"] == 0

        db = TestingSession()
        chgs_c2 = db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all()
        assert len(chgs_c2) == 2  # Permaneceu 2! Nenhuma duplicação!
        db.close()

        # Ciclo 3: novamente mesma vaga com 2000.
        res3 = run_search_sync()
        assert res3["updated"] == 0

        db = TestingSession()
        chgs_c3 = db.scalars(select(JobChangelog).where(JobChangelog.job_id == job_id)).all()
        assert len(chgs_c3) == 2
        db.close()


def test_b02_poison_job_does_not_abort_cycle():
    """
    B-02: Uma vaga corrompida/envenenada no meio do lote não pode abortar o ciclo inteiro
    nem apagar a telemetria do SearchRun.
    """
    vaga_ok_1 = DummyJob(
        external_id="ok-1",
        source="remotive",
        url="https://remotive.com/job/1",
        title="Desenvolvedor Python Backend Júnior",
        company="Startup Boa",
        location="Remoto",
        work_mode="remote",
        seniority="junior",
        employment_type="CLT",
        area="Tecnologia",
        description="Vaga excelente de Python",
        salary_min=3000.0,
        salary_max=4000.0,
        currency="BRL",
        requirements=["Python"],
        nice_to_have=[],
        published_at=datetime.now(timezone.utc),
        raw_data={}
    )

    # Vaga envenenada: objeto que lança erro durante conversão ou avaliação
    class PoisonJob:
        external_id = "poison-666"
        source = "evil_source"
        url = "https://malformed.invalid/job/666"
        @property
        def title(self):
            raise RuntimeError("Fatal explosion parsing malformed job payload")

    vaga_ok_2 = DummyJob(
        external_id="ok-2",
        source="remotive",
        url="https://remotive.com/job/2",
        title="Desenvolvedor Python FastAPI Pleno",
        company="Tech Inc",
        location="Remoto",
        work_mode="remote",
        seniority="mid",
        employment_type="CLT",
        area="Tecnologia",
        description="Vaga com Python e Docker",
        salary_min=5000.0,
        salary_max=6000.0,
        currency="BRL",
        requirements=["Python"],
        nice_to_have=[],
        published_at=datetime.now(timezone.utc),
        raw_data={}
    )

    collected_batch = [vaga_ok_1, PoisonJob(), vaga_ok_2]

    with patch("app.services.pipeline._collect_from_sources", return_value=(collected_batch, [], {}, 1)), \
         patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock):

        # Executa ciclo com vaga envenenada
        result = run_search_sync()

        # O ciclo NÃO explodiu
        assert result["status"] == "partial_error"
        assert len(result["errors"]) >= 1

        # O erro contém metadados claros da vaga com problema
        err_entry = [e for e in result["errors"] if isinstance(e, dict) and e.get("external_id") == "poison-666"]
        assert len(err_entry) == 1
        assert "Fatal explosion" in err_entry[0]["error"]
        assert err_entry[0]["source"] == "evil_source"

        # E o SearchRun foi persistido no banco com telemetria preservada
        db = TestingSession()
        sr = db.scalar(select(SearchRun).where(SearchRun.run_id == result["run_id"]))
        assert sr is not None
        assert sr.status == "partial_error"
        assert sr.jobs_found == 3
        assert sr.valid_count >= 1
        db.close()


def test_b03_concurrent_notifications_prevent_duplicate_sends():
    """
    B-03: Corrida concorrente de notificações na mesma vaga e mesmo canal
    não deve enviar duplicatas (apenas 1 envio efetivo).
    """
    db = TestingSession()
    u = db.scalar(select(User).where(User.id == 1))
    pref = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == 1))

    # Cria vaga salva no banco
    j = Job(
        uuid=str(uuid4()),
        external_id="job-notif-1",
        source="remotive",
        url="https://remotive.com/notif-1",
        title="Python Engineer",
        company="ACME",
        location="Remoto",
        content_hash="hash-notif-1"
    )
    db.add(j)
    db.commit()
    job_id = j.id
    db.close()

    send_call_count = 0
    lock = threading.Lock()

    async def mock_send(*args, **kwargs):
        nonlocal send_call_count
        with lock:
            send_call_count += 1
        time.sleep(0.05)  # Simula latência de rede

    with patch("app.providers.telegram.client.TelegramProvider.send_job_notification", side_effect=mock_send):
        import asyncio

        def worker_notify():
            local_db = TestingSession()
            user_inst = local_db.get(User, 1)
            pref_inst = local_db.get(SearchPreferences, 1)
            job_dict = {"title": "Python Engineer", "company": "ACME", "url": "https://remotive.com/notif-1"}

            asyncio.run(notify_job(
                local_db,
                user=user_inst,
                job_dict=job_dict,
                job_id=job_id,
                score=90,
                reasoning=["Excelente fit"],
                prefs=pref_inst
            ))
            local_db.close()

        # Dispara 2 threads concorrentes ao mesmo tempo
        t1 = threading.Thread(target=worker_notify)
        t2 = threading.Thread(target=worker_notify)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    # Verifica que o TelegramProvider foi chamado EXATAMENTE 1 vez
    assert send_call_count == 1, f"Expected 1 notification send, but got {send_call_count}"

    # E na tabela notifications há exatamente 1 registro
    db = TestingSession()
    notifs = db.scalars(select(Notification).where(Notification.job_id == job_id, Notification.channel == "telegram")).all()
    assert len(notifs) == 1
    assert notifs[0].status == "sent"
    db.close()


def test_b04_pipeline_distributed_lock_mutual_exclusion():
    """
    B-04: Dois ciclos disparados simultaneamente não devem colidir:
    o segundo ciclo detecta que já há execução e recebe 'already_running'.
    """
    from app.core.distributed_lock import acquire_pipeline_lock, release_pipeline_lock

    run1_id = str(uuid4())
    run2_id = str(uuid4())

    acquired1, info1 = acquire_pipeline_lock(run1_id, initiator="test_runner_1")
    assert acquired1 is True

    # Tentativa simultânea do run 2
    acquired2, info2 = acquire_pipeline_lock(run2_id, initiator="test_runner_2")
    assert acquired2 is False
    assert info2.get("run_id") == run1_id

    # Libera run 1
    release_pipeline_lock(run1_id)

    # Agora run 2 consegue adquirir
    acquired3, info3 = acquire_pipeline_lock(run2_id, initiator="test_runner_2")
    assert acquired3 is True
    release_pipeline_lock(run2_id)


def test_b06_batch_commit_failure_is_observable():
    """
    B-06: Falha no commit final em lote é registrada em stats['errors'],
    logada de forma estruturada e reflete status 'partial_error' no SearchRun.
    """
    mock_job = DummyJob(
        external_id="job-b06",
        source="remoteok",
        url="https://remoteok.com/job/b06",
        title="Python Dev",
        company="Remote Co",
        location="Remoto",
        work_mode="remote",
        seniority="junior",
        employment_type="CLT",
        area="Tecnologia",
        description="Python e Django",
        salary_min=4000.0,
        salary_max=5000.0,
        currency="BRL",
        requirements=["Python"],
        nice_to_have=[],
        published_at=datetime.now(timezone.utc),
        raw_data={}
    )

    with patch("app.services.pipeline._collect_from_sources", return_value=([mock_job], [], {}, 1)), \
         patch("app.providers.telegram.client.TelegramProvider.send_job_notification", new_callable=AsyncMock):

        from sqlalchemy.orm import Session
        import inspect
        original_commit = Session.commit

        def flaky_commit(self):
            frame = inspect.currentframe().f_back
            # Falha especificamente no commit do lote final (após o loop de vagas)
            if frame and frame.f_code.co_name == "run_search_sync" and frame.f_lineno >= 610:
                raise RuntimeError("Simulated Database Disk I/O Failure on Batch Commit")
            return original_commit(self)

        with patch.object(Session, "commit", flaky_commit):
            result = run_search_sync()

        # O erro não desapareceu silenciosamente
        assert any("batch_commit_error" in str(e) for e in result["errors"])
        assert result["status"] == "partial_error"
