from app.services.matching import deterministic_scores

PROFILE = {"headline": "Backend Developer", "skills": ["Python", "FastAPI", "PostgreSQL"],
           "roles": ["Backend Developer"], "seniority": "mid"}
PREFS = {"desired_roles": ["Backend Developer"], "locations": ["Remoto", "Brasil"],
         "minimum_salary": 5000}
JOB = {"title": "Backend Developer Python", "description": "Procuramos Python FastAPI PostgreSQL",
       "requirements": ["Python", "FastAPI"], "seniority": "mid", "work_mode": "remote",
       "location": "Brasil (Remoto)", "salary_min": 8000, "salary_max": 12000}


def test_scores_range_and_keys():
    s = deterministic_scores(JOB, PROFILE, PREFS)
    assert set(s) >= {"score", "role_score", "skills_score", "seniority_score",
                      "location_score", "salary_score"}
    assert all(0 <= s[k] <= 100 for k in ("score", "role_score", "skills_score",
                                          "seniority_score", "location_score", "salary_score"))


def test_good_match_scores_high():
    assert deterministic_scores(JOB, PROFILE, PREFS)["score"] >= 70


def test_bad_match_scores_low():
    bad = dict(JOB, title="Designer Gráfico", description="Photoshop Illustrator",
               requirements=["Photoshop"])
    assert deterministic_scores(bad, PROFILE, PREFS)["score"] < 70


def test_mock_llm_returns_valid_shape():
    import asyncio
    from app.providers.llm.mock import MockLLMProvider

    out = asyncio.run(MockLLMProvider().analyze_job(JOB, PROFILE, PREFS))
    assert 0 <= out["score"] <= 100 and isinstance(out["reasoning"], list) and out["reasoning"]
