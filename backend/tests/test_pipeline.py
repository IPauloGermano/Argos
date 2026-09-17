"""Pipeline end-to-end com MockJobSource + MockLLM + SQLite (sem rede, sem Postgres)."""
import asyncio
from app.providers.jobs.mock import MockJobSource
from app.providers.llm.mock import MockLLMProvider
from app.services.dedup import content_hash, dedup_key
from app.services.filters import apply_hard_filters
from app.services.matching import deterministic_scores


def test_mock_source_returns_jobs():
    jobs = asyncio.run(MockJobSource(count=10).search({"desired_roles": ["Backend Developer"]}))
    assert len(jobs) == 10
    assert all(j.title and j.url for j in jobs)


def test_full_flow_dedup_filter_match():
    jobs = asyncio.run(MockJobSource(count=10).search({"desired_roles": ["Backend Developer"]}))
    # simula duplicata: dobra a lista
    jobs = jobs + jobs
    profile = {"skills": ["Python", "FastAPI"], "roles": ["Backend Developer"], "seniority": "mid"}
    prefs = {"desired_roles": ["Backend Developer"], "seniority_levels": ["junior", "mid", "senior"],
             "locations": ["Brasil", "Remoto"], "work_modes": ["remote", "hybrid", "onsite"],
             "employment_types": [], "excluded_keywords": [], "excluded_companies": [],
             "minimum_salary": None, "maximum_salary": None, "minimum_match_score": 0}
    seen, unique = set(), []
    for j in jobs:
        ch = content_hash(j.title, j.company, j.location, j.url, j.external_id)
        key = dedup_key(j.title, j.company, j.location)
        if ch in seen or key in seen:
            continue
        seen.update((ch, key))
        unique.append(j)
    assert len(unique) == 10  # duplicadas removidas
    llm = MockLLMProvider()
    scored = []
    for j in unique:
        jd = {"title": j.title, "company": j.company, "location": j.location, "work_mode": j.work_mode,
              "seniority": j.seniority, "employment_type": j.employment_type, "description": j.description,
              "salary_min": j.salary_min, "salary_max": j.salary_max, "requirements": j.requirements,
              "nice_to_have": j.nice_to_have}
        ok, _ = apply_hard_filters(jd, prefs)
        if ok:
            scored.append(asyncio.run(llm.analyze_job(jd, profile, prefs)))
    assert scored and all(0 <= s["score"] <= 100 for s in scored)
