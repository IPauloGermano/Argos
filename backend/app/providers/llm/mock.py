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
        text = resume_text or ""
        skills_pool = ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "Celery",
                       "TypeScript", "Next.js", "React", "AWS", "Kubernetes", "SQL"]
        found = [s for s in skills_pool if re.search(r"\b" + re.escape(s) + r"\b", text, re.I)]
        years = 0
        m = re.search(r"(\d+)\s*(anos|years|yrs)", text, re.I)
        if m:
            years = int(m.group(1))
        seniority = "junior" if years < 2 else ("mid" if years < 5 else "senior")
        headline = "Software Engineer"
        m2 = re.search(r"(Backend|Frontend|Full.?stack|Data|DevOps)[^\n]{0,40}", text, re.I)
        if m2:
            headline = m2.group(0).strip()[:80]
        return {
            "headline": headline,
            "summary": text[:500],
            "years_experience": years,
            "seniority": seniority,
            "skills": found or ["Python", "SQL"],
            "roles": [headline, "Software Engineer"],
            "languages": ["Portuguese", "English"] if re.search(r"english", text, re.I) else ["Portuguese"],
        }
