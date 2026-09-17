from app.services.dedup import content_hash, normalize_url, dedup_key


def test_normalize_url_removes_query_and_fragment():
    assert normalize_url("https://Example.com/jobs/1/?utm=x#top") == "https://example.com/jobs/1"


def test_content_hash_stable_and_differs():
    h1 = content_hash("Backend Dev", "Acme", "Remoto")
    h2 = content_hash("Backend Dev", "Acme", "Remoto")
    h3 = content_hash("Backend Dev", "Other", "Remoto")
    assert h1 == h2 and h1 != h3


def test_content_hash_prefers_external_id_and_url():
    assert content_hash("A", "B", "C", external_id="ext-1") == content_hash("X", "Y", "Z", external_id="ext-1")
    assert content_hash("A", "B", "C", url="https://x.com/j/1?a=2") == content_hash("A", "B", "C", url="https://x.com/j/1")


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

