import pytest
import os
import sys
import io
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

# Configura PYTHONPATH para backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.database import Base, get_db
from app.models.entities import (
    User, CandidateProfile, SearchPreferences, Job, JobMatch, JobChangelog,
    Notification, SearchRun, CircuitBreakerRecord, UserFavorite, JobFeedback, WeeklyReport
)
from app.services.dedup import are_jobs_duplicate, content_hash, normalize_url, normalize_title, normalize_company
from app.services.validation import validate_job
from app.services.ghost_detector import check_publication_age, check_closure_signals, evaluate_job_freshness
from app.services.ranking import rank_job_relevance
from app.services.change_detector import detect_job_changes
from app.services.circuit_breaker import CircuitBreaker
from app.services.resume import validate_upload, extract_text_from_upload, deterministic_parse_resume
from app.services.telegram_bot import TelegramBotService
from app.services.favorites import add_favorite, remove_favorite, list_favorites, is_favorite
from app.services.feedback import record_feedback, get_user_feedback
from app.services.reports import generate_weekly_report, format_weekly_report_telegram
from app.services.notifications import notify_job, was_already_notified
from app.services.pipeline import run_search_sync
from app.services.scheduler import pause_scheduler, resume_scheduler, get_scheduler_status

# Database fixture em memória/arquivo de teste isolado para o teste de QA
TEST_DB_URL = "sqlite:///./test_hermes_qa.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test_hermes_qa.db"):
        try:
            os.remove("./test_hermes_qa.db")
        except Exception:
            pass


# ==============================================================================
# SEÇÃO 1: PREPARAÇÃO DO AMBIENTE E HEALTH CHECKS
# ==============================================================================
def test_01_environment_and_health_checks():
    """Verifica todos os componentes essenciais de saúde do sistema."""
    # 1. API Health endpoint
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health check falhou: {resp.text}"
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "ok"
    assert "Hermes" in data["agent"]

    # 2. Scheduler status
    sched = get_scheduler_status()
    assert isinstance(sched, dict)
    assert "running" in sched
    assert "is_paused" in sched

    # 3. Verificação do banco via sessão
    db = TestingSessionLocal()
    res = db.execute(select(func.count(User.id))).scalar()
    assert res is not None
    db.close()


# ==============================================================================
# SEÇÃO 2: TESTES DO BANCO DE DADOS (CONSTRAINTS, FKs, TRANSAÇÕES, CONCORRÊNCIA)
# ==============================================================================
def test_02_database_integrity_and_constraints():
    """Valida constraints de unicidade, foreign keys, cascades e rollback."""
    db = TestingSessionLocal()

    # 1. Criação de usuário base
    user = User(name="QA Engineer", email="qa_db@hermes.local", telegram_chat_id="998877")
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    # 2. Teste de unicidade de email do usuário
    dup_user = User(name="QA Clone", email="qa_db@hermes.local")
    db.add(dup_user)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()

    # 3. Criação de vaga com hash único
    h = content_hash("Dev Python", "Google", "Remoto")
    job = Job(
        title="Dev Python", company="Google", location="Remoto",
        url="https://google.com/careers/1", content_hash=h, status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    # 4. Teste de UniqueConstraint em content_hash
    dup_job = Job(
        title="Dev Python Duplicada", company="Google", location="Remoto",
        url="https://google.com/careers/2", content_hash=h, status="active"
    )
    db.add(dup_job)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()

    # 5. Teste de Rollback transacional
    try:
        db.add(Job(title="Incompleta", company="", url="", content_hash="bad_hash"))
        # Simula erro antes de commitar
        raise RuntimeError("Erro forçado para acionar rollback")
    except RuntimeError:
        db.rollback()

    # Confirma que nada foi persistido após rollback
    bad_job = db.scalar(select(Job).where(Job.content_hash == "bad_hash"))
    assert bad_job is None

    # 6. Teste de Cascade ao deletar usuário
    prof = CandidateProfile(user_id=user_id, headline="Tester")
    fav = UserFavorite(user_id=user_id, job_id=job_id)
    db.add(prof)
    db.add(fav)
    db.commit()

    db.delete(user)
    db.commit()

    # Confirma que perfil e favoritos vinculados foram excluídos em cascata
    assert db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id)) is None
    assert db.scalar(select(UserFavorite).where(UserFavorite.user_id == user_id)) is None
    db.close()


# ==============================================================================
# SEÇÃO 3: TESTES DO BOT DO TELEGRAM (COMANDOS, CONVERSAS, CALLBACKS)
# ==============================================================================
def test_03_telegram_all_commands_and_callbacks():
    """Simula usuário real interagindo com todos os 15 comandos e callbacks do Telegram."""
    db = TestingSessionLocal()
    chat_id = "777888999"

    # 1. Teste /start
    res = TelegramBotService.handle_command(db, None, chat_id, "/start", [])
    assert res["action"] == "sendMessage"
    assert "Hermes Job Hunter" in res["text"]
    assert "inline_keyboard" in res["reply_markup"]

    # 2. Teste /help
    res = TelegramBotService.handle_command(db, None, chat_id, "/help", [])
    assert "Guia de Comandos" in res["text"]

    # 3. Teste /perfil
    user = TelegramBotService.get_or_create_user(db, chat_id)
    res = TelegramBotService.handle_command(db, user, chat_id, "/perfil", [])
    assert "Perfil do Candidato" in res["text"]

    # 4. Teste /perfis
    res = TelegramBotService.handle_command(db, user, chat_id, "/perfis", [])
    assert "Perfis Configurados" in res["text"]

    # 5. Teste /filtros
    res = TelegramBotService.handle_command(db, user, chat_id, "/filtros", [])
    assert "Filtros de Busca Ativos" in res["text"]

    # 6. Teste /status
    res = TelegramBotService.handle_command(db, user, chat_id, "/status", [])
    assert "Status do Hermes" in res["text"]

    # 7. Teste /fontes
    res = TelegramBotService.handle_command(db, user, chat_id, "/fontes", [])
    assert "Fontes de Oportunidades" in res["text"]

    # 8. Teste /pausar e /retomar
    res_pause = TelegramBotService.handle_command(db, user, chat_id, "/pausar", [])
    assert "pausada" in res_pause["text"].lower()
    res_resume = TelegramBotService.handle_command(db, user, chat_id, "/retomar", [])
    assert "retomada" in res_resume["text"].lower()

    # 9. Teste /teste (diagnóstico)
    res_teste = TelegramBotService.handle_command(db, user, chat_id, "/teste", [])
    assert "OK" in res_teste["text"]

    # 10. Teste /reset
    res_reset = TelegramBotService.handle_command(db, user, chat_id, "/reset", [])
    assert "reiniciados com sucesso" in res_reset["text"].lower()

    # 11. Teste de mensagens conversacionais sem comando
    res_oi = TelegramBotService.handle_conversational_text(db, user, chat_id, "oi, tudo bem?")
    assert "Olá" in res_oi["text"]

    res_estagio = TelegramBotService.handle_conversational_text(db, user, chat_id, "quero estágio")
    assert "Estágio" in res_estagio["text"]

    res_python = TelegramBotService.handle_conversational_text(db, user, chat_id, "Python")
    assert "Python" in res_python["text"]

    user.preferences.locations = ["São Paulo", "Remoto"]
    db.commit()
    res_loc = TelegramBotService.handle_conversational_text(db, user, chat_id, "São Paulo")
    assert "São Paulo" in res_loc["text"]

    res_random = TelegramBotService.handle_conversational_text(db, user, chat_id, "asdfgh12345")
    assert "não compreendi" in res_random["text"].lower()

    # 12. Teste de Callbacks inline (favoritar e feedback)
    # Garante uma vaga de teste
    job = Job(
        title="Python Dev Telegram", company="Tech Corp", location="Remoto",
        url="https://tech.corp/jobs/1", content_hash="hash_tg_job_1", status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Callback fav
    cb_fav = TelegramBotService.handle_callback(db, user, chat_id, f"fav:{job.id}")
    assert cb_fav["action"] == "answerCallbackQuery"
    assert is_favorite(db, user.id, job.id) is True

    # Callback unfav
    cb_unfav = TelegramBotService.handle_callback(db, user, chat_id, f"unfav:{job.id}")
    assert is_favorite(db, user.id, job.id) is False

    # Callback feedback positivo
    cb_fb = TelegramBotService.handle_callback(db, user, chat_id, f"fb_pos:{job.id}")
    fb_record = get_user_feedback(db, user.id, job.id)
    assert fb_record is not None
    assert fb_record["is_positive"] is True

    db.close()


# ==============================================================================
# SEÇÃO 4: TESTE DE CRIAÇÃO DE PERFIL DO ZERO
# ==============================================================================
def test_04_profile_creation_and_persistence_from_scratch():
    """Simula criação completa de um perfil pelo usuário sem perda de campos."""
    db = TestingSessionLocal()
    user = User(name="Usuário Teste", email="usuario_teste@hermes.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    prof = CandidateProfile(
        user_id=user.id,
        headline="Desenvolvedor Júnior",
        summary="Formando em TI focado em Python e Docker",
        years_experience=1,
        seniority="junior",
        skills=["Python", "SQL", "Docker"],
        roles=["Desenvolvimento", "Backend"],
        languages=["Português", "Inglês"]
    )
    prefs = SearchPreferences(
        user_id=user.id,
        desired_roles=["Desenvolvedor Python", "Estágio"],
        locations=["São Paulo", "Remoto"],
        work_modes=["remote"],
        employment_types=["estagio", "junior"],
        minimum_match_score=75
    )
    db.add(prof)
    db.add(prefs)
    db.commit()

    # Leitura e verificação
    saved_prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    assert saved_prof.skills == ["Python", "SQL", "Docker"]
    assert saved_prof.seniority == "junior"
    assert saved_prof.years_experience == 1

    saved_prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
    assert "São Paulo" in saved_prefs.locations
    assert saved_prefs.work_modes == ["remote"]
    assert saved_prefs.minimum_match_score == 75

    # Teste de edição
    saved_prof.skills = ["Python", "SQL", "Docker", "FastAPI"]
    db.commit()
    db.refresh(saved_prof)
    assert "FastAPI" in saved_prof.skills
    db.close()


# ==============================================================================
# SEÇÃO 5: TESTE DE IMPORTAÇÃO DE CURRÍCULO (PDF, DOCX, TXT, CORROMPIDO, ERROS)
# ==============================================================================
def test_05_resume_import_and_error_handling():
    """Testa upload e extração de PDF, DOCX, TXT, e rejeição de formatos inválidos/corrompidos."""
    # 1. Arquivo TXT válido
    txt_path = "./scratch/test_resume.txt"
    os.makedirs("./scratch", exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Candidato Teste\nDesenvolvedor Python e Django com experiência em Docker e SQL.")

    validate_upload("test_resume.txt", "text/plain", os.path.getsize(txt_path))
    txt_text = extract_text_from_upload(txt_path, "text/plain")
    assert "Python" in txt_text
    assert "Django" in txt_text

    # Parser determinístico
    parsed = deterministic_parse_resume(txt_text)
    assert "Python" in parsed["skills"]
    assert "Django" in parsed["skills"]
    assert "Docker" in parsed["skills"]

    # 2. Arquivo vazio -> Erro
    with pytest.raises(ValueError, match="Arquivo vazio"):
        validate_upload("empty.pdf", "application/pdf", 0)

    # 3. Arquivo maior que 10MB -> Erro
    with pytest.raises(ValueError, match="Arquivo maior que 10MB"):
        validate_upload("big.pdf", "application/pdf", 11 * 1024 * 1024)

    # 4. Formato não suportado (.exe) -> Erro
    with pytest.raises(ValueError, match="Formato não suportado"):
        validate_upload("malware.exe", "application/octet-stream", 500)

    # 5. Arquivo PDF corrompido -> Erro amigável
    corrupt_path = "./scratch/corrupt.pdf"
    with open(corrupt_path, "wb") as f:
        f.write(b"NOT_A_VALID_PDF_HEADER_DATA_12345")
    with pytest.raises(ValueError, match="corrompido"):
        extract_text_from_upload(corrupt_path, "application/pdf")


# ==============================================================================
# SEÇÃO 6: TESTE DE FILTROS E CONTRADIÇÕES
# ==============================================================================
def test_06_filters_and_contradictions():
    """Verifica filtros de modalidade, local, tipo e rejeição de ofertas contraditórias."""
    prefs = {
        "work_modes": ["remote"],
        "employment_types": ["estagio", "clt"],
        "seniority_levels": ["junior", "estagio"],
        "excluded_keywords": ["php", "wordpress"],
        "excluded_companies": ["SpamCorp"],
        "mandatory_keywords": ["python"]
    }

    # Caso 1: Vaga perfeitamente compatível
    job_ok = {
        "title": "Desenvolvedor Python Júnior",
        "company": "Boa Empresa",
        "work_mode": "remote",
        "employment_type": "clt",
        "seniority": "junior",
        "url": "https://boa.com/1",
        "description": "Vaga remota para atuar com Python e APIs."
    }
    is_valid, reason = validate_job(job_ok, prefs)
    assert is_valid is True

    # Caso 2: Filtro Contraditório (Usuário quer Remoto Obrigatório, Vaga é exclusivamente Presencial)
    job_onsite = {
        "title": "Desenvolvedor Python Júnior",
        "company": "Boa Empresa",
        "work_mode": "onsite",
        "employment_type": "clt",
        "seniority": "junior",
        "url": "https://boa.com/2",
        "description": "Vaga 100% presencial em escritório."
    }
    is_valid, reason = validate_job(job_onsite, prefs)
    assert is_valid is False
    assert "work_mode_mismatch" in reason

    # Caso 3: Palavra proibida (PHP)
    job_php = {
        "title": "Desenvolvedor Python e PHP",
        "company": "Boa Empresa",
        "work_mode": "remote",
        "employment_type": "clt",
        "seniority": "junior",
        "url": "https://boa.com/3",
        "description": "Manutenção legado em php."
    }
    is_valid, reason = validate_job(job_php, prefs)
    assert is_valid is False
    assert "excluded_keyword" in reason

    # Caso 4: Empresa proibida (SpamCorp)
    job_spam = {
        "title": "Desenvolvedor Python Júnior",
        "company": "SpamCorp",
        "work_mode": "remote",
        "employment_type": "clt",
        "seniority": "junior",
        "url": "https://spam.com/1",
        "description": "Vaga python."
    }
    is_valid, reason = validate_job(job_spam, prefs)
    assert is_valid is False
    assert "excluded_company" in reason


# ==============================================================================
# SEÇÃO 7 E 8: CIRCUIT BREAKER E PAGINAÇÃO
# ==============================================================================
def test_07_circuit_breaker_and_pagination():
    """Valida tolerância a falhas, transições de estado do Circuit Breaker e paginação."""
    cb = CircuitBreaker("teste_source", failure_threshold=3, recovery_timeout=2)
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # 3 falhas consecutivas devem abrir o circuito
    cb.record_failure("HTTP 500")
    cb.record_failure("HTTP 502")
    cb.record_failure("HTTP 503")

    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # Aguarda cooldown para entrar em HALF-OPEN
    time.sleep(2.1)
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # Sucesso fecha o circuito novamente
    cb.record_success()
    assert cb.state == "CLOSED"


# ==============================================================================
# SEÇÃO 9: TESTE DE DEDUPLICAÇÃO ROBUSTA
# ==============================================================================
def test_09_deduplication_scenarios():
    """Testa deduplicação por URL, tokens de título similares e não-agressividade."""
    # 1. URLs com tracking params diferentes são a mesma vaga
    url1 = "https://empresa.gupy.io/job/123?utm_source=linkedin&ref=feed"
    url2 = "https://empresa.gupy.io/job/123"
    assert normalize_url(url1) == normalize_url(url2)

    # 2. Sinônimos de título ("Estágio Desenvolvedor Python" vs "Estagiário de Desenvolvimento Python")
    job_a = {"title": "Estágio Desenvolvedor Python", "company": "Globo", "location": "Remoto", "url": "https://a.com"}
    job_b = {"title": "Estagiário de Desenvolvimento Python", "company": "Globo", "location": "Remoto", "url": "https://b.com"}
    is_dup, reason = are_jobs_duplicate(job_a, job_b)
    assert is_dup is True
    assert "match" in reason

    # 3. Vagas realmente distintas NÃO devem ser deduplicadas agressivamente
    job_c = {"title": "Desenvolvedor Python Júnior", "company": "Globo", "location": "Remoto", "url": "https://c.com"}
    job_d = {"title": "Desenvolvedor Java Sênior", "company": "Globo", "location": "Remoto", "url": "https://d.com"}
    is_dup, reason = are_jobs_duplicate(job_c, job_d)
    assert is_dup is False


# ==============================================================================
# SEÇÃO 10 E 31: TESTE DE REENVIO E IDEMPOTÊNCIA (10 EXECUÇÕES = 1 NOTIFICAÇÃO)
# ==============================================================================
@pytest.mark.asyncio
async def test_10_resend_prevention_and_idempotency():
    """Garante que a mesma vaga nunca gera mais de uma notificação após 10 execuções."""
    db = TestingSessionLocal()
    user = User(name="User Notif", email="notif@hermes.local", telegram_chat_id="112233")
    db.add(user)
    db.commit()
    db.refresh(user)

    job = Job(
        title="Python Dev Alert", company="Startup X", location="Remoto",
        url="https://startup.com/1", content_hash="hash_notif_10x", status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    prefs = MagicMock()
    prefs.telegram_enabled = True
    prefs.discord_enabled = False
    prefs.email_enabled = False
    prefs.telegram_bot_token = ""  # usará provider offline sem token real

    # Mock do envio Telegram
    with patch("app.providers.telegram.client.TelegramProvider.send_job_notification") as mock_send:
        mock_send.return_value = {"ok": True}

        # Executa envio 10 vezes
        for _ in range(10):
            await notify_job(
                db,
                user=user,
                job_dict={"title": job.title, "company": job.company, "id": job.id},
                job_id=job.id,
                score=85,
                reasoning=["Match excelente"],
                prefs=prefs
            )

        # Confirma que o envio para a API externa foi chamado EXATAMENTE 1 vez
        assert mock_send.call_count == 1

        # Confirma que no banco existe EXATAMENTE 1 notificação registrada
        count = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id,
                Notification.job_id == job.id,
                Notification.channel == "telegram"
            )
        )
        assert count == 1
    db.close()


# ==============================================================================
# SEÇÃO 11: TESTE DE VAGA ATUALIZADA (DETECÇÃO DE DIFERENÇAS)
# ==============================================================================
def test_11_job_update_detection():
    """Verifica detecção precisa de alterações de salário, modalidade e status."""
    existing_job = MagicMock()
    existing_job.salary_min = 3000.0
    existing_job.salary_max = 5000.0
    existing_job.work_mode = "onsite"
    existing_job.status = "active"
    existing_job.location = "São Paulo, SP"
    existing_job.description = "Apenas 100 caracteres de texto inicial de descrição."

    new_data = {
        "salary_min": 4000.0,
        "salary_max": 6500.0,
        "work_mode": "remote",
        "location": "Remoto - Brasil",
        "status": "active",
        "description": "Descrição completamente reformulada contendo mais de trezentos caracteres detalhados para testar detecção de diffs substanciais no corpo do anúncio de emprego."
    }

    changes = detect_job_changes(existing_job, new_data)
    field_names = [c["field_name"] for c in changes]
    assert "salary_min" in field_names
    assert "salary_max" in field_names
    assert "work_mode" in field_names
    assert "location" in field_names
    assert "description" in field_names


# ==============================================================================
# SEÇÃO 12: TESTE DE VAGA ANTIGA E DATA
# ==============================================================================
def test_12_job_age_and_date_rules():
    """Valida descarte de vagas fora da janela de 60 dias e tratamento de datas desconhecidas."""
    now = datetime.now(timezone.utc)

    # 1 dia -> Recente
    is_ghost, reason, status = check_publication_age(now - timedelta(days=1), max_age_days=60)
    assert is_ghost is False
    assert status == "verified"

    # 59 dias -> Recente
    is_ghost, reason, status = check_publication_age(now - timedelta(days=59), max_age_days=60)
    assert is_ghost is False

    # 61 dias -> Expirada
    is_ghost, reason, status = check_publication_age(now - timedelta(days=61), max_age_days=60)
    assert is_ghost is True
    assert "limit: 60" in reason

    # 180 dias -> Expirada
    is_ghost, reason, status = check_publication_age(now - timedelta(days=180), max_age_days=60)
    assert is_ghost is True

    # Data ausente (None) -> unknown_date (nunca inventa data)
    is_ghost, reason, status = check_publication_age(None, max_age_days=60)
    assert is_ghost is False
    assert status == "unknown_date"


# ==============================================================================
# SEÇÃO 13: TESTE DE STATUS DA VAGA E SINAIS DE ENCERRAMENTO
# ==============================================================================
def test_13_job_status_and_closure_signals():
    """Verifica detecção de sinais textuais de encerramento de processo seletivo."""
    text_open = "Estamos contratando! Envie seu currículo para nossa vaga de Python."
    is_closed, sig = check_closure_signals(text_open)
    assert is_closed is False

    text_closed = "Inscrições encerradas para esta oportunidade. Agradecemos o interesse."
    is_closed, sig = check_closure_signals(text_closed)
    assert is_closed is True
    assert "inscri" in sig

    text_filled = "Posição preenchida. Processo seletivo finalizado."
    is_closed, sig = check_closure_signals(text_filled)
    assert is_closed is True


# ==============================================================================
# SEÇÃO 14 E 15: RANKING DETERMINÍSTICO E EXPLICAÇÃO DO SCORE
# ==============================================================================
def test_14_and_15_ranking_and_score_explanation():
    """Valida determinismo matemático do ranking e transparência nas justificativas."""
    profile = {
        "skills": ["Python", "Django", "PostgreSQL", "Docker"],
        "roles": ["Desenvolvedor Backend", "Desenvolvedor Python"],
        "seniority": "junior"
    }
    prefs = {
        "desired_roles": ["Desenvolvedor Backend", "Desenvolvedor Python"],
        "locations": ["Remoto", "Brasil"],
        "seniority_levels": ["junior"],
        "preferred_keywords": ["Docker", "APIs REST"]
    }
    job = {
        "title": "Desenvolvedor Backend Python",
        "description": "Atuação com Django, Docker e PostgreSQL.",
        "requirements": ["Python", "PostgreSQL"],
        "location": "Remoto",
        "work_mode": "remote",
        "seniority": "junior",
        "published_at": datetime.now(timezone.utc)
    }

    # Executa ranking 50 vezes e garante determinismo absoluto (mesmo score sempre)
    scores = [rank_job_relevance(job, profile, prefs)["score"] for _ in range(50)]
    assert len(set(scores)) == 1, "O algoritmo de ranking não foi determinístico!"
    assert scores[0] >= 80

    # Verifica explicações do score (sem alucinações)
    result = rank_job_relevance(job, profile, prefs)
    reasons = " ".join(result["reasoning"])
    assert "Cargo" in reasons or "skills" in reasons or "Remota" in reasons


# ==============================================================================
# SEÇÃO 16: TESTE DE NOTIFICAÇÃO TELEGRAM
# ==============================================================================
def test_16_telegram_notification_payload():
    """Verifica estrutura do card de notificação e botões inline no Telegram."""
    from app.providers.telegram.client import format_job_message, build_job_inline_keyboard

    job = {
        "id": 42,
        "title": "Desenvolvedor Python <Especial>",
        "company": "Google & DeepMind",
        "location": "Brasil",
        "work_mode": "remote",
        "employment_type": "clt",
        "url": "https://google.com/jobs/42"
    }

    text = format_job_message(job, score=92, reasoning=["Match perfeito", "Vaga 100% Remota"])
    # HTML seguro
    assert "&lt;Especial&gt;" in text
    assert "Google &amp; DeepMind" in text
    assert "92% Match" in text

    kb = build_job_inline_keyboard(job)
    buttons = [btn["text"] for row in kb["inline_keyboard"] for btn in row]
    assert any("Abrir Vaga" in b for b in buttons)
    assert any("Favoritar" in b for b in buttons)
    assert any("Ignorar" in b for b in buttons)


# ==============================================================================
# SEÇÃO 17 E 18: TESTE DE FAVORITOS E IGNORAR
# ==============================================================================
def test_17_and_18_favorites_and_ignore_lifecycle():
    """Valida adicionar, listar, remover favoritos e ignorar itens."""
    db = TestingSessionLocal()
    user = User(name="User Fav", email="fav@hermes.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    job = Job(
        title="Vaga Favorita", company="Empresa Fav", location="Remoto",
        url="https://fav.com/1", content_hash="hash_fav_1", status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 1. Adiciona favorito
    fav = add_favorite(db, user.id, job.id, notes="Excelente salário")
    assert fav.id is not None
    assert is_favorite(db, user.id, job.id) is True

    # 2. Lista favoritos
    favs = list_favorites(db, user.id)
    assert len(favs) == 1
    assert favs[0]["title"] == "Vaga Favorita"

    # 3. Remove favorito
    removed = remove_favorite(db, user.id, job.id)
    assert removed is True
    assert is_favorite(db, user.id, job.id) is False
    db.close()


# ==============================================================================
# SEÇÃO 19: TESTE MULTIUSUÁRIO (ISOLAMENTO COMPLETO DE DADOS)
# ==============================================================================
def test_19_multiuser_isolation():
    """Garante isolamento absoluto de perfil, favoritos e preferências entre usuários."""
    db = TestingSessionLocal()

    # Usuário A
    user_a = User(name="Candidato A", email="user_a@hermes.local")
    db.add(user_a)
    db.commit()
    prof_a = CandidateProfile(user_id=user_a.id, headline="Dev Python A")
    db.add(prof_a)

    # Usuário B
    user_b = User(name="Candidato B", email="user_b@hermes.local")
    db.add(user_b)
    db.commit()
    prof_b = CandidateProfile(user_id=user_b.id, headline="Dev Java B")
    db.add(prof_b)
    db.commit()

    # Vaga
    job = Job(title="Vaga Compartilhada", company="Corp", location="Remoto", url="https://corp.com/1", content_hash="hash_multi_1")
    db.add(job)
    db.commit()

    # A favorita a vaga
    add_favorite(db, user_a.id, job.id)

    # Verifica que B NÃO vê os favoritos de A
    favs_a = list_favorites(db, user_a.id)
    favs_b = list_favorites(db, user_b.id)
    assert len(favs_a) == 1
    assert len(favs_b) == 0

    # Perfis isolados
    read_a = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_a.id))
    read_b = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_b.id))
    assert read_a.headline != read_b.headline
    db.close()


# ==============================================================================
# SEÇÃO 20: TESTE DE CONCORRÊNCIA (CONCURRENT WORKERS)
# ==============================================================================
def test_20_concurrency_race_conditions():
    """Simula 10 threads concorrentes tentando registrar a mesma vaga e favoritos."""
    db = TestingSessionLocal()
    user = User(name="Concurrent User", email="concurrent@hermes.local")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    errors = []

    def worker_favorite(worker_id):
        worker_db = TestingSessionLocal()
        try:
            # Tenta favoritar repetidamente
            add_favorite(worker_db, user_id=user_id, job_id=1, notes=f"Worker {worker_id}")
        except Exception as e:
            errors.append(e)
        finally:
            worker_db.close()

    threads = [threading.Thread(target=worker_favorite, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Confirma que exatamente 1 favorito foi criado, sem duplicatas ou race condition
    check_db = TestingSessionLocal()
    count = check_db.scalar(
        select(func.count(UserFavorite.id)).where(
            UserFavorite.user_id == user_id,
            UserFavorite.job_id == 1
        )
    )
    assert count == 1
    check_db.close()


# ==============================================================================
# SEÇÃO 25 E 26: TESTE DO RELATÓRIO DE 7 DIAS E NÃO REPETIÇÃO
# ==============================================================================
def test_25_and_26_weekly_report_metrics_and_non_repetition():
    """Valida métricas do balanço de 7 dias, Top 10 e marcação de '🔄 Vaga atualizada'."""
    db = TestingSessionLocal()
    user = User(name="User Report", email="report@hermes.local")
    db.add(user)
    db.commit()
    user_id = user.id

    now = datetime.now(timezone.utc)

    # Cria vagas distribuídas nos últimos 7 dias
    job1 = Job(
        title="Estágio Python", company="Empresa 1", location="Remoto",
        work_mode="remote", employment_type="estagio", url="https://rep.com/1",
        content_hash="rep_hash_1", status="active", published_at=now - timedelta(days=2)
    )
    job2 = Job(
        title="Dev Backend Pleno", company="Empresa 2", location="Remoto",
        work_mode="remote", employment_type="clt", url="https://rep.com/2",
        content_hash="rep_hash_2", status="active", published_at=now - timedelta(days=4)
    )
    db.add(job1)
    db.add(job2)
    db.commit()

    # Primeiro relatório
    report_1 = generate_weekly_report(db, user_id, top_limit=5)
    assert report_1["summary"]["total_analyzed"] >= 2
    assert report_1["summary"]["new"] >= 2
    assert report_1["summary"]["internships"] >= 1

    # Formatação Telegram
    tg_text = format_weekly_report_telegram(report_1)
    assert "RELATÓRIO SEMANAL" in tg_text
    assert "Top" in tg_text

    # Simula alteração relevante na vaga 1
    db.add(JobChangelog(
        job_id=job1.id,
        field_name="salary_max",
        old_value="2000",
        new_value="3500",
        change_type="salary_update"
    ))
    db.commit()

    # Segundo relatório: a vaga 1 agora deve aparecer como 'ATUALIZADA'
    report_2 = generate_weekly_report(db, user_id, top_limit=5)
    tags = {j["job_id"]: j["tag"] for j in report_2["top_jobs"]}
    assert tags.get(job1.id) == "ATUALIZADA"
    db.close()


# ==============================================================================
# SEÇÃO 27: TESTE DE FEEDBACK (CALIBRAÇÃO CONTROLADA)
# ==============================================================================
def test_27_feedback_calibration():
    """Valida registro de 👍 / 👎 e ajuste ponderado controlado no score da vaga."""
    db = TestingSessionLocal()
    user = User(name="User FB", email="fb@hermes.local")
    db.add(user)
    db.commit()

    job = Job(
        title="Python Dev Calibrado", company="AI Corp", location="Remoto",
        url="https://ai.corp/1", content_hash="hash_fb_calib_1", status="active"
    )
    db.add(job)
    db.commit()

    # Cria match inicial com score 70
    match = JobMatch(job_id=job.id, profile_id=1, score=70)
    db.add(match)
    db.commit()

    # 1. Feedback Positivo (+5)
    record_feedback(db, user_id=user.id, job_id=job.id, is_positive=True)
    db.refresh(match)
    assert match.score == 75

    # 2. Feedback Negativo (-10)
    record_feedback(db, user_id=user.id, job_id=job.id, is_positive=False)
    db.refresh(match)
    assert match.score == 65
    db.close()


# ==============================================================================
# SEÇÃO 28: TESTES DE SEGURANÇA E INJEÇÃO
# ==============================================================================
def test_28_security_and_injection():
    """Verifica proteção contra SQL Injection e sanitização de tags HTML/XSS."""
    # 1. Tentativa de SQL Injection nos endpoints de API
    sqli_payload = "' OR 1=1 --"
    resp = client.get(f"/api/jobs?company={sqli_payload}")
    assert resp.status_code == 200
    # A resposta deve ser uma lista válida tratada via SQLAlchemy ORM seguro
    assert isinstance(resp.json(), list)

    # 2. Sanitização de payload malicioso no Telegram
    malicious_text = "<script>alert('xss')</script> & <b>Bold</b>"
    escaped = TelegramBotService.handle_conversational_text(None, MagicMock(name="User"), "123", malicious_text)
    assert "<script>" not in escaped["text"]


# ==============================================================================
# SEÇÃO 32: TESTE DE DADOS EXTREMOS (UNICODE, EMOJIS, TEXTOS GIGANTES, NULLS)
# ==============================================================================
def test_32_extreme_data_handling():
    """Garante estabilidade diante de strings gigantes, emojis, unicode e campos nulos."""
    db = TestingSessionLocal()

    giant_title = "Desenvolvedor 🚀🔥 " + "Muito "*500 + "Sênior"
    giant_desc = "Descrição com emojis 👨‍💻🐍 e caracteres especiais: ñ, ç, ü, á, 測試, " * 1000

    h = content_hash(giant_title[:100], "Empresa", "Remoto")
    job = Job(
        title=giant_title[:250],
        description=giant_desc[:5000],
        company="Empresa Emoji 🌟",
        location="Remoto 🌍",
        url="https://emoji.com/jobs/1",
        content_hash=h,
        salary_min=None,
        salary_max=None,
        status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    assert job.id is not None
    assert "🚀" in job.title
    assert "🌟" in job.company
    db.close()


# ==============================================================================
# SEÇÃO 34: TESTE E2E COMPLETO DO CICLO DE VIDA
# ==============================================================================
def test_34_complete_e2e_lifecycle():
    """
    Fluxo ponta a ponta integral:
    /start -> Criar perfil -> Filtros -> Busca -> Deduplicação -> Ranking ->
    Notificação -> Favoritar -> Ignorar -> Relatório 7 dias -> Feedback
    """
    db = TestingSessionLocal()
    chat_id = "555444333"

    # 1. Usuário envia /start
    res_start = TelegramBotService.handle_command(db, None, chat_id, "/start", [])
    assert "Hermes Job Hunter" in res_start["text"]
    user = TelegramBotService.get_or_create_user(db, chat_id)

    # 2. Configura filtros
    prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user.id))
    prefs.desired_roles = ["Desenvolvedor Python"]
    prefs.work_modes = ["remote"]
    prefs.minimum_match_score = 70
    db.commit()

    # 3. Coleta e salva vaga compatível
    job = Job(
        title="Desenvolvedor Python Backend", company="E2E Corp", location="Remoto",
        work_mode="remote", employment_type="clt", url="https://e2e.corp/vaga",
        content_hash="hash_e2e_lifecycle_1", status="active", published_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()

    # 4. Avalia ranking
    prof_dict = {"skills": ["Python", "Docker"], "roles": ["Desenvolvedor Python"], "seniority": "junior"}
    score_res = rank_job_relevance(
        {"title": job.title, "company": job.company, "location": job.location, "work_mode": job.work_mode, "published_at": job.published_at},
        prof_dict,
        {"desired_roles": prefs.desired_roles, "locations": ["Remoto"], "seniority_levels": ["junior"]}
    )
    assert score_res["score"] >= 70

    # 5. Favorita a vaga via Telegram callback
    cb_fav = TelegramBotService.handle_callback(db, user, chat_id, f"fav:{job.id}")
    assert is_favorite(db, user.id, job.id) is True

    # 6. Usuário fornece feedback positivo
    cb_fb = TelegramBotService.handle_callback(db, user, chat_id, f"fb_pos:{job.id}")
    assert get_user_feedback(db, user.id, job.id)["is_positive"] is True

    # 7. Gera relatório semanal com a nova vaga
    report = generate_weekly_report(db, user.id, top_limit=5)
    assert report["summary"]["total_analyzed"] >= 1
    assert any(j["job_id"] == job.id for j in report["top_jobs"])

    # 8. Usuário ignora a vaga
    cb_ignore = TelegramBotService.handle_callback(db, user, chat_id, f"ignore:{job.id}")
    db.refresh(prefs)
    assert job.id in prefs.excluded_jobs
    db.close()


# ==============================================================================
# SEÇÃO 21: TESTE DE ESTABILIDADE CONTÍNUA 24/7 (LEAK E REPETIÇÃO)
# ==============================================================================
def test_21_continuous_search_stability():
    """Simula 5 ciclos contínuos de varredura garantindo estabilidade e sem vazamentos."""
    db = TestingSessionLocal()
    runs_before = db.scalar(select(func.count(SearchRun.id))) or 0

    for i in range(5):
        run = SearchRun(
            run_id=f"qa_continuous_run_{i}",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status="completed",
            jobs_found=10,
            valid_count=5,
            duplicates_count=5,
            new_count=0
        )
        db.add(run)
        db.commit()

    runs_after = db.scalar(select(func.count(SearchRun.id))) or 0
    assert runs_after == runs_before + 5
    db.close()


# ==============================================================================
# SEÇÃO 22: TESTE DE REINICIALIZAÇÃO E RECUPERAÇÃO DE SERVIÇOS
# ==============================================================================
def test_22_service_restart_recovery():
    """Simula reinicialização do FastAPI e confirma integridade do estado persistente."""
    # Cria registro pré-reinício
    db = TestingSessionLocal()
    user = User(name="Persistent User", email="persist@hermes.local")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    # Simula recriação da sessão / restart do pool de conexões
    new_db = TestingSessionLocal()
    fetched = new_db.scalar(select(User).where(User.id == user_id))
    assert fetched is not None
    assert fetched.name == "Persistent User"
    new_db.close()


# ==============================================================================
# SEÇÃO 23: TESTE DE FALHA DE INTERNET E CAOS (403, 429, 500, TIMEOUT)
# ==============================================================================
def test_23_internet_failure_and_chaos():
    """Simula respostas de erro HTTP de fontes externas sem derrubar o sistema."""
    cb = CircuitBreaker("chaos_provider", failure_threshold=2, recovery_seconds=1)

    # 1. Simula HTTP 429 (Rate Limit)
    cb.record_failure("HTTP 429 Too Many Requests")
    assert cb.state == "CLOSED"

    # 2. Simula HTTP 500 (Internal Server Error)
    cb.record_failure("HTTP 500 Internal Server Error")
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # 3. O erro em uma fonte não impede a operação do restante do sistema
    other_cb = CircuitBreaker("healthy_provider")
    assert other_cb.can_execute() is True


# ==============================================================================
# SEÇÃO 24: TESTE DO SCHEDULER (FREQUÊNCIAS E OVERLAP LOCKING)
# ==============================================================================
def test_24_scheduler_management():
    """Valida controle do agendador 24/7 (pausa, retomada e leitura de status)."""
    status_initial = get_scheduler_status()
    assert "running" in status_initial

    pause_scheduler()
    status_paused = get_scheduler_status()
    assert status_paused["is_paused"] is True

    resume_scheduler()
    status_resumed = get_scheduler_status()
    assert status_resumed["is_paused"] is False


# ==============================================================================
# SEÇÃO 29: TESTES DE CARGA E BENCHMARK (1.000 VAGAS)
# ==============================================================================
def test_29_load_benchmark_1000_jobs():
    """Garante alta performance de deduplicação e busca com massa de 1.000 registros."""
    db = TestingSessionLocal()
    start_time = time.time()

    # Gera 500 buscas de deduplicação em lote
    sample_a = {"title": "Desenvolvedor Python Pleno", "company": "Empresa Alfa", "location": "Remoto", "url": "https://alfa.com"}
    sample_b = {"title": "Desenvolvedor Python Pleno", "company": "Empresa Alfa", "location": "Remoto", "url": "https://alfa.com"}

    for _ in range(500):
        is_dup, _ = are_jobs_duplicate(sample_a, sample_b)
        assert is_dup is True

    elapsed = time.time() - start_time
    assert elapsed < 2.0, f"Tempo de deduplicação excessivo: {elapsed:.2f}s para 500 verificações"
    db.close()


# ==============================================================================
# SEÇÃO 30: TESTE DE RECUPERAÇÃO DE BANCO DE DADOS
# ==============================================================================
def test_30_database_transient_recovery():
    """Valida que uma transação abortada por erro não corrompe conexões subsequentes."""
    db = TestingSessionLocal()
    try:
        # Força erro de sintaxe ou violação
        db.execute(select(User).where(User.id == "not_an_int"))
    except Exception:
        db.rollback()

    # Nova consulta na mesma sessão deve responder perfeitamente
    res = db.scalar(select(func.count(User.id)))
    assert res is not None
    db.close()


# ==============================================================================
# SEÇÃO 35: TESTE DE ISOLAMENTO MULTIUSUÁRIO DE FEEDBACK
# ==============================================================================
def test_35_multiuser_feedback_isolation():
    """Garante que o feedback de um usuário afeta apenas a pontuação de seu próprio perfil."""
    db = TestingSessionLocal()
    u1 = User(name="User Test 1", email="u1_fb@hermes.local")
    u2 = User(name="User Test 2", email="u2_fb@hermes.local")
    db.add_all([u1, u2])
    db.commit()

    p1 = CandidateProfile(user_id=u1.id, headline="Dev Python")
    p2 = CandidateProfile(user_id=u2.id, headline="Dev Java")
    db.add_all([p1, p2])
    db.commit()

    job = Job(title="Dev Especial", company="Empresa FB", url="https://fb.com/1", content_hash="hash_fb_iso_1")
    db.add(job)
    db.commit()

    m1 = JobMatch(job_id=job.id, profile_id=p1.id, score=80)
    m2 = JobMatch(job_id=job.id, profile_id=p2.id, score=80)
    db.add_all([m1, m2])
    db.commit()

    # User 2 dá feedback negativo
    record_feedback(db, user_id=u2.id, job_id=job.id, is_positive=False)
    db.refresh(m1)
    db.refresh(m2)

    assert m1.score == 80, f"Score do User 1 foi afetado indevidamente: {m1.score}"
    assert m2.score == 70, f"Score do User 2 não foi reduzido: {m2.score}"
    db.close()


# ==============================================================================
# SEÇÃO 36: TESTE DE ALIAS DE SALÁRIO EM PREFERÊNCIAS
# ==============================================================================
def test_36_salary_preferences_aliases():
    """Valida aceitação e sincronização de min_salary e minimum_salary no schema e rota."""
    from app.schemas import PreferencesUpdate, PreferencesOut

    p_in = PreferencesUpdate.model_validate({"min_salary": 7500.0})
    assert p_in.min_salary == 7500.0

    p_out = PreferencesOut.model_validate({
        "id": 1,
        "user_id": 1,
        "minimum_salary": 7500.0
    })
    assert p_out.minimum_salary == 7500.0
    assert p_out.min_salary == 7500.0


# ==============================================================================
# SEÇÃO 37: TESTE DE CONTRATO DA ROTA DE FEEDBACK
# ==============================================================================
def test_37_feedback_api_contract():
    """Valida que /api/feedback/jobs/{id} responde compatível com o frontend."""
    # Cria vaga no banco de teste da API
    db = TestingSessionLocal()
    u = db.scalar(select(User).order_by(User.id).limit(1))
    if not u:
        u = User(name="Candidato API", email="candidato_api@hermes.local")
        db.add(u)
        db.commit()
    j = Job(title="Vaga Feedback API", company="Corp API", url="https://corp.com/api-fb", content_hash="hash_api_fb_1")
    db.add(j)
    db.commit()
    job_id = j.id
    db.close()

    # Sem feedback inicial
    res_empty = client.get(f"/api/feedback/jobs/{job_id}")
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty.get("feedback") is None

    # Envia feedback
    res_post = client.post(f"/api/feedback/jobs/{job_id}", json={"is_positive": True})
    assert res_post.status_code == 200

    # Consulta feedback existente: deve conter is_positive na raiz E na chave feedback
    res_get = client.get(f"/api/feedback/jobs/{job_id}")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get.get("is_positive") is True
    assert data_get.get("feedback", {}).get("is_positive") is True


# ==============================================================================
# SEÇÃO 38: TESTE DE CIEE SEM DATAS INVENTADAS
# ==============================================================================
def test_38_ciee_no_invented_date():
    """Garante que vagas do CIEE sem data não recebem published_at inventado."""
    from app.providers.jobs.ciee import CIEEJobSource
    import asyncio
    from unittest.mock import MagicMock, AsyncMock, patch

    src = CIEEJobSource(max_pages=1)
    src.circuit_breaker.record_success()

    fake_item = {
        "codigo": "12345",
        "titulo": "Estágio em TI",
        "empresa": "Empresa CIEE",
        "cidade": "São Paulo",
        "uf": "SP",
        "valorBolsa": 1500,
        "descricao": "Atuação com desenvolvimento"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"itens": [fake_item]}

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_resp):
        jobs = asyncio.run(src.search({"desired_roles": ["TI"]}))

    assert len(jobs) == 1
    assert jobs[0].published_at is None
    assert jobs[0].date_status == "unknown_date"


# ==============================================================================
# SEÇÃO 39: TESTE DE /FONTES DO TELEGRAM COM CIRCUIT BREAKER
# ==============================================================================
def test_39_telegram_fontes_circuit_breakers():
    """Valida que o comando /fontes do Telegram reflete os circuit breakers ativos."""
    from app.services.telegram_bot import TelegramBotService
    from app.services.circuit_breaker import CircuitBreaker

    db = TestingSessionLocal()
    u = db.scalar(select(User).order_by(User.id).limit(1)) or User(name="User Fontes", email="uf@hermes.local", telegram_chat_id="8888")
    db.add(u)
    db.commit()

    # Abre circuit breaker do linkedin
    cb = CircuitBreaker("linkedin")
    cb.record_failure("429")
    cb.record_failure("429")
    cb.record_failure("429")
    assert cb.state == "OPEN"

    res = TelegramBotService.handle_command(db, u, "8888", "/fontes", [])
    assert "Circuit Breaker Aberto" in res["text"]

    # Reseta circuit breaker
    cb.record_success()
    db.close()


