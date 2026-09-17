from datetime import datetime, timezone, timedelta
from app.services.ghost_detector import check_publication_age, check_closure_signals, evaluate_job_freshness


def test_ghost_detector_discards_over_60_days():
    old_date = datetime.now(timezone.utc) - timedelta(days=61)
    is_old, reason, status = check_publication_age(old_date, max_age_days=60)
    assert is_old is True
    assert status == "expired"
    assert "published_61_days_ago" in reason


def test_ghost_detector_accepts_recent_date():
    recent_date = datetime.now(timezone.utc) - timedelta(days=5)
    is_old, reason, status = check_publication_age(recent_date, max_age_days=60)
    assert is_old is False
    assert status == "verified"


def test_ghost_detector_never_invents_date():
    is_old, reason, status = check_publication_age(None, max_age_days=60)
    assert is_old is False
    assert status == "unknown_date"


def test_ghost_detector_detects_closure_signals():
    closed_text = "Esta oportunidade está com inscrições encerradas para novos candidatos."
    is_closed, reason = check_closure_signals(closed_text)
    assert is_closed is True
    assert "closure_signal" in reason

    open_text = "Venha fazer parte do nosso time de tecnologia! Vaga aberta para início imediato."
    is_closed, reason = check_closure_signals(open_text)
    assert is_closed is False


def test_evaluate_job_freshness_full():
    job = {
        "title": "Desenvolvedor Python",
        "description": "Venha trabalhar conosco",
        "published_at": datetime.now(timezone.utc) - timedelta(days=10)
    }
    eval_res = evaluate_job_freshness(job, max_age_days=60)
    assert eval_res["is_ghost"] is False
    assert eval_res["status"] == "active"
    assert eval_res["date_status"] == "verified"
