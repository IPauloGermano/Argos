from __future__ import annotations
from typing import Optional
from app.core.config import settings
from .base import JobSource
from .mock import MockJobSource
from .remotive import RemotiveJobSource
from .gupy import GupyJobSource
from .linkedin import LinkedInJobSource
from .indeed import IndeedJobSource
from .vagas import VagasComJobSource
from .ciee import CIEEJobSource
from .greenhouse_lever import CorporateATSJobSource
from .glassdoor import GlassdoorJobSource
from .remoteok import RemoteOKJobSource
from .getonbrd import GetOnBoardJobSource
from .weworkremotely import WeWorkRemotelyJobSource
from .jobicy import JobicyJobSource


SOURCE_REGISTRY: dict[str, type[JobSource]] = {
    "mock": MockJobSource,
    "remotive": RemotiveJobSource,
    "remoteok": RemoteOKJobSource,
    "gupy": GupyJobSource,
    "linkedin": LinkedInJobSource,
    "indeed": IndeedJobSource,
    "vagas": VagasComJobSource,
    "ciee": CIEEJobSource,
    "greenhouse": CorporateATSJobSource,
    "glassdoor": GlassdoorJobSource,
    "getonbrd": GetOnBoardJobSource,
    "weworkremotely": WeWorkRemotelyJobSource,
    "jobicy": JobicyJobSource,
}


def get_job_sources(enabled_names: Optional[list[str]] = None) -> list[JobSource]:
    """
    Retorna instâncias dos conectores habilitados.
    Se enabled_names for fornecido (via preferências do usuário), filtra por ele.
    Caso contrário, utiliza settings.JOB_SOURCES.
    """
    if enabled_names:
        names = [n.strip().lower() for n in enabled_names if n.strip()]
    else:
        names = [n.strip().lower() for n in settings.JOB_SOURCES.split(",") if n.strip()]

    sources: list[JobSource] = []
    for n in names:
        if n == "mock" and settings.MOCK_JOBS_COUNT > 0:
            sources.append(MockJobSource(count=settings.MOCK_JOBS_COUNT))
        elif n == "remotive":
            sources.append(RemotiveJobSource(timeout=settings.REMOTIVE_TIMEOUT_SECONDS))
        elif n == "remoteok":
            sources.append(RemoteOKJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS))
        elif n == "gupy":
            sources.append(GupyJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "linkedin":
            sources.append(LinkedInJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "indeed":
            sources.append(IndeedJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "vagas":
            sources.append(VagasComJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "ciee":
            sources.append(CIEEJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "greenhouse":
            sources.append(CorporateATSJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "glassdoor":
            sources.append(GlassdoorJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=2))
        elif n == "getonbrd":
            sources.append(GetOnBoardJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "weworkremotely":
            sources.append(WeWorkRemotelyJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))
        elif n == "jobicy":
            sources.append(JobicyJobSource(timeout=settings.SOURCE_TIMEOUT_SECONDS, max_pages=settings.SOURCE_MAX_PAGES))

    return sources
