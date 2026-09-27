from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
import re
import httpx

CLOSED_INDICATORS = [
    r"\bvaga\s+encerrada\b",
    r"\bvagas?\s+esgotadas?\b",
    r"\bcandidaturas?\s+encerradas?\b",
    r"\binscri[cç][oõ]es?\s+encerradas?\b",
    r"\bprocesso\s+seletivo\s+(encerrado|finalizado)\b",
    r"\bposi[cç][aã]o\s+preenchida\b",
    r"\bjob\s+(is\s+)?(expired|closed)\b",
    r"\bno\s+longer\s+accepting\s+applications\b",
    r"\bthis\s+position\s+has\s+been\s+closed\b",
    r"\bapplications?\s+(have\s+)?closed\b",
    r"\bvaga\s+pausada\b",
]


def check_publication_age(
    published_at: Optional[datetime],
    max_age_days: int = 60
) -> tuple[bool, str, str]:
    """
    Verifica a idade da vaga contra o limite configurado (default 60 dias).
    Retorna (is_ghost, reason, date_status).
    NUNCA inventa datas: se published_at for None, marca como 'unknown_date'.
    """
    if not published_at:
        return False, "unknown_date", "unknown_date"

    # Converte para UTC timezone-aware para cálculo preciso
    if published_at.tzinfo is None:
        pub_utc = published_at.replace(tzinfo=timezone.utc)
    else:
        pub_utc = published_at.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)
    age = now - pub_utc

    if age > timedelta(days=max_age_days):
        days = age.days
        return True, f"published_{days}_days_ago (limit: {max_age_days})", "expired"

    return False, "recent", "verified"


def check_closure_signals(text: str) -> tuple[bool, str]:
    """Analisa conteúdo da vaga buscando sinais evidentes de vaga encerrada."""
    if not text:
        return False, "no_text"
    lower = text.lower()
    for pattern in CLOSED_INDICATORS:
        if re.search(pattern, lower):
            return True, f"closure_signal: {pattern}"
    return False, "open"


async def check_url_liveness(url: str, timeout: float = 5.0) -> tuple[bool, int, str]:
    """
    Verifica se a página da vaga ainda existe (HTTP 200/300) ou se retornou 404/410/erro.
    Com proteção SSRF: bloqueia hosts privados/loopback/.local antes de qualquer fetch.
    Fail-open em erro de rede para evitar falsos positivos.
    """
    if not url:
        return False, 0, "empty_url"
    try:
        from app.providers.jobs.http_client import is_private_url
        if is_private_url(url):
            return True, 0, "ssrf_blocked_private_host"
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.head(url, headers=headers)
            if resp.status_code in (404, 410):
                return False, resp.status_code, "not_found"
            if resp.status_code >= 400:
                # Tenta GET rápido caso HEAD seja bloqueado pelo servidor
                resp = await client.get(url, headers=headers)
                if resp.status_code in (404, 410):
                    return False, resp.status_code, "not_found"
            return True, resp.status_code, "active"
    except Exception as e:
        # Se for timeout ou erro de rede, não descarta imediatamente para evitar falsos positivos
        return True, 0, f"network_warning: {type(e).__name__}"


def evaluate_job_freshness(
    job: dict,
    max_age_days: int = 60,
    check_signals: bool = True
) -> dict:
    """
    Avaliação completa de frescor e status fantasma da vaga.
    Adiciona chaves 'date_status', 'is_ghost', 'ghost_reason', 'status'.
    """
    published_at = job.get("published_at")
    is_old, age_reason, date_status = check_publication_age(published_at, max_age_days)

    if is_old:
        return {
            "is_ghost": True,
            "status": "potential_ghost",
            "ghost_reason": age_reason,
            "date_status": date_status
        }

    if check_signals:
        blob = f"{job.get('title', '')} {job.get('description', '')}"
        is_closed, close_reason = check_closure_signals(blob)
        if is_closed:
            return {
                "is_ghost": True,
                "status": "closed",
                "ghost_reason": close_reason,
                "date_status": date_status
            }

    return {
        "is_ghost": False,
        "status": "active",
        "ghost_reason": "",
        "date_status": date_status
    }
