from app.services.validation import validate_job, is_spam_or_scam


def test_validation_rejects_spam():
    is_spam, reason = is_spam_or_scam(
        "Ganhe dinheiro sem sair de casa",
        "Trabalhe 2 horas por dia e ganhe R$ 5000 imediatamente!"
    )
    assert is_spam is True
    assert "spam_pattern_detected" in reason


def test_validation_rejects_missing_company():
    job = {"title": "Desenvolvedor Python", "company": "", "url": "https://empresa.com/vaga/1"}
    is_valid, reason = validate_job(job, {})
    assert is_valid is False
    assert reason == "missing_company_name"


def test_validation_rejects_invalid_url():
    job = {"title": "Desenvolvedor Python", "company": "Acme", "url": "ftp://empresa.com/vaga/1"}
    is_valid, reason = validate_job(job, {})
    assert is_valid is False
    assert reason == "invalid_url"


def test_validation_enforces_mandatory_keywords():
    job = {
        "title": "Desenvolvedor Frontend",
        "company": "Acme",
        "url": "https://empresa.com/vaga/1",
        "description": "Trabalhar com Vue.js e CSS"
    }
    prefs = {"mandatory_keywords": ["python"]}
    is_valid, reason = validate_job(job, prefs)
    assert is_valid is False
    assert "missing_mandatory_keyword" in reason

    # Com a palavra obrigatória presente
    job["description"] = "Trabalhar com Python e FastAPI"
    is_valid, reason = validate_job(job, prefs)
    assert is_valid is True


def test_validation_rejects_excluded_keywords():
    job = {
        "title": "Engenheiro de Software PHP",
        "company": "Acme",
        "url": "https://empresa.com/vaga/1",
        "description": "Legado em PHP"
    }
    prefs = {"excluded_keywords": ["php"]}
    is_valid, reason = validate_job(job, prefs)
    assert is_valid is False
    assert "excluded_keyword" in reason
