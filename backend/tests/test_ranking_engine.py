from datetime import datetime, timezone, timedelta
from app.services.ranking import rank_job_relevance


def test_ranking_high_match():
    job = {
        "title": "Backend Developer Python",
        "description": "Desenvolvimento com Python, FastAPI, PostgreSQL e Docker",
        "seniority": "mid",
        "work_mode": "remote",
        "location": "Brasil",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=12),
        "requirements": ["Python", "FastAPI", "Docker"]
    }
    profile = {
        "roles": ["Backend Developer"],
        "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
        "seniority": "mid"
    }
    prefs = {
        "desired_roles": ["Backend Developer"],
        "locations": ["Brasil", "Remoto"],
        "seniority_levels": ["mid"],
        "preferred_keywords": ["Python", "Docker"]
    }

    result = rank_job_relevance(job, profile, prefs)
    assert result["score"] >= 80
    assert result["role_score"] >= 90
    assert result["skills_score"] == 100
    assert result["location_score"] == 100
    assert len(result["reasoning"]) > 0


def test_ranking_low_match():
    job = {
        "title": "Designer Gráfico",
        "description": "Figma, Photoshop e Ilustração",
        "seniority": "junior",
        "work_mode": "onsite",
        "location": "Manaus, AM",
        "published_at": datetime.now(timezone.utc) - timedelta(days=25)
    }
    profile = {
        "roles": ["Backend Developer"],
        "skills": ["Python", "Docker"],
        "seniority": "senior"
    }
    prefs = {
        "desired_roles": ["Backend Developer"],
        "locations": ["Remoto"],
        "seniority_levels": ["senior"],
        "preferred_keywords": ["Python"]
    }

    result = rank_job_relevance(job, profile, prefs)
    assert result["score"] < 50
