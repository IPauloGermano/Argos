from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import re
import unicodedata
from typing import Optional
from app.services.circuit_breaker import CircuitBreaker


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    return "".join(c for c in text if not unicodedata.combining(c))


SENIORITY_RULES: tuple[tuple[str, str], ...] = (
    ("estagio", r"estag|intern|aprendiz|apprentice"),
    ("trainee", r"trainee"),
    ("junior", r"junior|\bjr\b|entry[\s-]?level"),
    ("senior", r"senior|\bsr\b|staff|principal|\blead\b|especialista"),
    ("mid", r"\bpleno\b|\bmid\b|mid[\s-]?level"),
)


def infer_seniority(title: str, description: str = "") -> str:
    """Infere senioridade (estagio/trainee/junior/mid/senior) do titulo.

    Usa o MAIOR nivel mencionado ("Pleno/Senior" -> senior). Retorna ""
    quando indeterminado (filtros ignoram vazio em vez de descartar).
    """
    text = f"{_norm(title)} {_norm(description[:500])}"
    for level, pattern in SENIORITY_RULES:
        if re.search(pattern, text):
            return level
    return ""


@dataclass
class NormalizedJob:
    external_id: str = ""
    source: str = "mock"
    url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: str = ""
    seniority: str = ""
    employment_type: str = ""
    area: str = "Tecnologia"
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = "BRL"
    requirements: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    date_status: str = "verified"
    raw_data: dict = field(default_factory=dict)


class JobSource(ABC):
    name: str = "base"
    max_pages: int = 3
    rate_limit_delay_seconds: float = 1.0
    timeout: float = 30.0

    def __init__(self, timeout: Optional[float] = None, max_pages: Optional[int] = None):
        if timeout is not None:
            self.timeout = timeout
        if max_pages is not None:
            self.max_pages = max_pages
        self.circuit_breaker = CircuitBreaker(self.name)
        self.pages_crawled = 0
        self.last_status = "idle"

    def get_default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 HermesJobHunter/2.0",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "application/json, text/html, */*",
        }

    @abstractmethod
    async def search(self, query: dict) -> list[NormalizedJob]:
        """
        Executa a busca para a fonte considerando paginação e filtros da query.
        Deve respeitar rate limits e atualizar self.pages_crawled.
        """
        raise NotImplementedError
