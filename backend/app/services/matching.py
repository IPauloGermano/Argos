from __future__ import annotations
from app.services.ranking import (
    calculate_role_score,
    calculate_skills_score,
    calculate_seniority_score,
    calculate_location_score,
    rank_job_relevance,
)


def role_score(job: dict, profile: dict, prefs: dict) -> int:
    score, _ = calculate_role_score(job, profile, prefs)
    return score


def skills_score(job: dict, profile: dict) -> int:
    score, _ = calculate_skills_score(job, profile, {})
    return score


def seniority_score(job: dict, profile: dict) -> int:
    score, _ = calculate_seniority_score(job, profile, {})
    return score


def location_score(job: dict, prefs: dict) -> int:
    score, _ = calculate_location_score(job, prefs)
    return score


def deterministic_scores(job: dict, profile: dict, prefs: dict) -> dict:
    return rank_job_relevance(job, profile, prefs)

