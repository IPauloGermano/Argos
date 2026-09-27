from app.services.dedup import content_hash, normalize_url, dedup_key


def test_normalize_url_removes_query_and_fragment():
    assert normalize_url("https://Example.com/jobs/1/?utm=x#top") == "https://example.com/jobs/1"
    # Tracking params removidos, funcionais preservados
    assert normalize_url("https://x.com/j/1?utm_source=google&fbclid=abc") == "https://x.com/j/1"
    assert "id=123" in normalize_url("https://x.com/j?id=123&utm_source=google")
    assert normalize_url("https://x.com/j?id=123") != normalize_url("https://x.com/j?id=456")


def test_content_hash_stable_and_differs():
    h1 = content_hash("Backend Dev", "Acme", "Remoto")
    h2 = content_hash("Backend Dev", "Acme", "Remoto")
    h3 = content_hash("Backend Dev", "Other", "Remoto")
    assert h1 == h2 and h1 != h3


def test_content_hash_prefers_external_id_and_url():
    assert content_hash("A", "B", "C", external_id="ext-1") == content_hash("X", "Y", "Z", external_id="ext-1")
    # Query funcional distinta => hash distinto (anúncios distintos)
    assert content_hash("A", "B", "C", url="https://x.com/j/1?id=2") != content_hash("A", "B", "C", url="https://x.com/j/1?id=3")
    # Tracking removido => mesmo hash
    assert content_hash("A", "B", "C", url="https://x.com/j/1?utm_source=g") == content_hash("A", "B", "C", url="https://x.com/j/1")


def test_dedup_key_case_insensitive():
    assert dedup_key("Backend Dev", "Acme", "SP") == dedup_key("backend dev ", " ACME", "sp")


def test_fuzzy_dedup_variations():
    from app.services.dedup import are_jobs_duplicate

    job1 = {"title": "Estágio em Desenvolvimento", "company": "Empresa XYZ", "location": "Remoto"}
    job2 = {"title": "Estagiário de Desenvolvimento", "company": "Empresa XYZ LTDA", "location": "Remoto"}
    job3 = {"title": "Estágio Desenvolvedor", "company": "Empresa XYZ", "location": "Remoto"}
    job4 = {"title": "Engenheiro de Software Sênior", "company": "Empresa XYZ", "location": "Remoto"}

    dup1, _ = are_jobs_duplicate(job1, job2)
    dup2, _ = are_jobs_duplicate(job1, job3)
    dup3, _ = are_jobs_duplicate(job1, job4)

    assert dup1 is True
    assert dup2 is True
    assert dup3 is False

