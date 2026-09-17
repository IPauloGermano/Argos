from __future__ import annotations
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def analyze_job(self, job: dict, profile: dict, preferences: dict) -> dict:
        """Retorna dict com score, *_score e reasoning (lista de str)."""
        raise NotImplementedError

    @abstractmethod
    async def parse_resume(self, resume_text: str) -> dict:
        """Retorna dict com headline, summary, years_experience, seniority, skills, roles, languages."""
        raise NotImplementedError
