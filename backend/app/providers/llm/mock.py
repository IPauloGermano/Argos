from __future__ import annotations
import re
from .base import LLMProvider

SENIORITY_YEARS = {"intern": 0, "junior": 1, "mid": 3, "pleno": 3, "senior": 5, "staff": 8, "principal": 10}


class MockLLMProvider(LLMProvider):
    """Heurístico/determinístico. Permite rodar todo o sistema sem API externa."""

    async def analyze_job(self, job: dict, profile: dict, preferences: dict) -> dict:
        from app.services.matching import deterministic_scores

        scores = deterministic_scores(job, profile, preferences)
        reasons: list[str] = []
        pskills = {s.lower() for s in (profile.get("skills") or [])}
        desc = f"{job.get('title','')} {job.get('description','')} {' '.join(job.get('requirements') or [])}".lower()
        hits = sorted({s for s in pskills if s and s in desc})
        for h in hits[:4]:
            reasons.append(f"{h} é um match forte")
        if not reasons:
            reasons.append("Perfil geral compatível com a descrição")
        if (job.get("work_mode") or "").lower() in {"remote", "remoto", "remot"}:
            reasons.append("Trabalho remoto compatível com preferência")
        if scores["seniority_score"] >= 80:
            reasons.append("Senioridade compatível")
        else:
            reasons.append("Gap de senioridade: verificar requisitos")
        return {**scores, "reasoning": reasons[:6]}

    async def parse_resume(self, resume_text: str) -> dict:
        from app.services.resume import deterministic_parse_resume
        return deterministic_parse_resume(resume_text or "")
