from app.services.filters import apply_hard_filters

JOB = {"title": "Backend Developer Python", "company": "Acme", "description": "Python FastAPI",
       "seniority": "mid", "work_mode": "remote", "employment_type": "full_time",
       "salary_min": 8000, "salary_max": 12000}
PREFS = {"excluded_keywords": [], "excluded_companies": [], "seniority_levels": ["mid", "senior"],
         "work_modes": ["remote"], "employment_types": [], "minimum_salary": 5000, "maximum_salary": None}


def test_passes():
    ok, reason = apply_hard_filters(JOB, PREFS)
    assert ok and reason == "ok"


def test_excluded_keyword():
    ok, reason = apply_hard_filters(JOB, {**PREFS, "excluded_keywords": ["python"]})
    assert not ok and reason == "excluded_keyword"


def test_seniority_block():
    ok, reason = apply_hard_filters(JOB, {**PREFS, "seniority_levels": ["senior"]})
    assert not ok and reason == "seniority"


def test_work_mode_block():
    ok, reason = apply_hard_filters(JOB, {**PREFS, "work_modes": ["onsite"]})
    assert not ok


def test_salary_below_minimum():
    ok, reason = apply_hard_filters(JOB, {**PREFS, "minimum_salary": 20000})
    assert not ok and reason == "salary_below_minimum"


def test_excluded_company():
    ok, reason = apply_hard_filters(JOB, {**PREFS, "excluded_companies": ["acme"]})
    assert not ok and reason == "excluded_company"
