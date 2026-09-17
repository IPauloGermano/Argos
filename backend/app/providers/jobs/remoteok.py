from __future__ import annotations
import asyncio
import html
import re
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from .base import JobSource, NormalizedJob


def _clean_html(raw: str, limit: int = 2000) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    if "<" in text:
        try:
            text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
        except Exception:
            text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _to_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_datetime(value) -> tuple[datetime | None, str]:
    if not value:
        return None, "unknown_date"
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc), "verified"
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt, "verified"
    except Exception:
        return None, "unknown_date"


class RemoteOKJobSource(JobSource):
    """Conector RemoteOK — API publica gratuita de vagas tech remotas.

    Sem chave, sem login, sem scraping de HTML: GET unico que retorna ~100
    vagas. O filtro por cargo e feito localmente (titulo + tags).
    """

    name = "remoteok"

    def __init__(self, timeout: float = 20.0, max_pages: int = 1):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.api_url = "https://remoteok.com/api"

    def _matches(self, job: dict, terms: list[str]) -> bool:
        haystack = f"{job.get('position') or ''} {' '.join(job.get('tags') or [])}".lower()
        for term in terms:
            if term and term.lower() in haystack:
                return True
        if any(tech in haystack for tech in ["python", "django", "backend"]):
            return True
        return False

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Developer"]
        known_urls = query.get("known_urls") or set()
        known_ids = query.get("known_ids") or set()
        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()
            headers["Accept"] = "application/json"

            try:
                resp = await client.get(self.api_url, headers=headers)
                self.pages_crawled += 1

                if resp.status_code == 429:
                    self.circuit_breaker.record_failure("Rate limit 429")
                    return jobs

                if resp.status_code != 200:
                    self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                    return jobs

                payload = resp.json()
                items = payload if isinstance(payload, list) else payload.get("jobs", [])

                for item in items:
                    if not isinstance(item, dict) or not item.get("position"):
                        continue  # pula aviso legal / entradas invalidas

                    ext_id = f"remoteok-{item.get('id') or item.get('slug')}"
                    job_url = str(item.get("url") or "")
                    if ext_id in known_ids or job_url in known_urls:
                        continue

                    if not self._matches(item, roles):
                        continue

                    pub_dt, date_status = _to_datetime(item.get("epoch") or item.get("date"))
                    location = str(item.get("location") or "").strip() or "Remoto"

                    jobs.append(NormalizedJob(
                        external_id=ext_id,
                        source=self.name,
                        url=job_url,
                        title=str(item.get("position") or "").strip(),
                        company=str(item.get("company") or "").strip(),
                        location=location,
                        work_mode="remote",
                        seniority="",
                        # Tipo de contrato desconhecido na API: vazio passa
                        # pelo filtro sem rotular errado (validacao ignora "").
                        employment_type="",
                        area="Tecnologia",
                        description=_clean_html(str(item.get("description") or "")),
                        salary_min=_to_float(item.get("salary_min")),
                        salary_max=_to_float(item.get("salary_max")),
                        currency="USD",
                        published_at=pub_dt,
                        date_status=date_status,
                        raw_data={"tags": item.get("tags") or []},
                    ))

                await asyncio.sleep(self.rate_limit_delay_seconds)

            except Exception as e:
                self.circuit_breaker.record_failure(str(e))
                return jobs

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
