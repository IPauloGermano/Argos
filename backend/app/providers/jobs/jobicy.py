from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
import httpx
from .base import JobSource, NormalizedJob


def _infer_seniority(text: str, declared_level: str = "") -> str:
    dl = (declared_level or "").lower()
    if any(k in dl for k in ("senior", "lead", "staff", "principal")):
        return "senior"
    if any(k in dl for k in ("junior", "entry", "intern")):
        return "junior"
    t = text.lower()
    if any(k in t for k in ("principal", "staff", "lead", "architect", "head of")):
        return "senior"
    if any(k in t for k in ("senior", "sr", "sênior", "sr.")):
        return "senior"
    if any(k in t for k in ("junior", "jr", "júnior", "jr.", "trainee", "entry", "intern")):
        return "junior"
    return "mid"


class JobicyJobSource(JobSource):
    """
    Conector para Jobicy (https://jobicy.com).
    Plataforma de vagas remotas nos EUA, América Latina e Globais.
    API pública e oficial, só leitura, sem necessidade de autenticação.
    """
    name = "jobicy"

    def __init__(self, timeout: float = 20.0, max_pages: int = 2):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.api_url = "https://jobicy.com/api/v2/remote-jobs"

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles: list[str] = query.get("desired_roles") or ["python"]
        jobs: list[NormalizedJob] = []
        seen_ids: set[str] = set()
        self.pages_crawled = 0

        # Tags de busca
        tags = []
        for r in roles[:2]:
            clean_r = r.strip().lower()
            if "python" in clean_r:
                tags.append("python")
            elif "backend" in clean_r:
                tags.append("backend")
            elif "devops" in clean_r:
                tags.append("devops")
            else:
                tags.append("software")
        if not tags:
            tags = ["python"]

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.get_default_headers()) as client:
            for tag in tags[:2]:
                try:
                    params = {"count": 25, "tag": tag}
                    resp = await client.get(self.api_url, params=params)
                    self.pages_crawled += 1

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("Jobicy Rate Limit 429")
                        break
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        break

                    try:
                        payload = resp.json()
                    except Exception:
                        self.circuit_breaker.record_failure("Invalid JSON from Jobicy")
                        break

                    items = payload.get("jobs", [])
                    if not items:
                        continue

                    for item in items:
                        job_id = str(item.get("id") or "")
                        title = (item.get("jobTitle") or "").strip()
                        url = (item.get("url") or "").strip()
                        company = (item.get("companyName") or "").strip()
                        geo = (item.get("jobGeo") or "USA / Worldwide").strip()

                        if not job_id or not title or not url or job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        raw_desc = item.get("jobDescription") or item.get("jobExcerpt") or ""
                        desc_clean = re.sub(r"<[^>]+>", " ", raw_desc).strip()

                        # Salário
                        s_min = item.get("salaryMin")
                        s_max = item.get("salaryMax")
                        salary_min = float(s_min) if s_min else None
                        salary_max = float(s_max) if s_max else None
                        currency = item.get("salaryCurrency") or "USD"

                        # Data de publicação
                        raw_pub = item.get("pubDate")
                        pub_dt = None
                        date_status = "unknown_date"
                        if raw_pub:
                            try:
                                dt = datetime.fromisoformat(str(raw_pub).replace("Z", "+00:00"))
                                if dt.tzinfo is None:
                                    pub_dt = dt.replace(tzinfo=timezone.utc)
                                else:
                                    pub_dt = dt.astimezone(timezone.utc)
                                date_status = "verified"
                            except Exception:
                                pass

                        seniority = _infer_seniority(f"{title} {desc_clean}", item.get("jobLevel") or "")

                        nj = NormalizedJob(
                            external_id=f"jobicy-{job_id}",
                            source=self.name,
                            url=url,
                            title=title,
                            company=company or "Empresa Remota (Jobicy)",
                            location=f"{geo} (Remoto)",
                            work_mode="remote",
                            seniority=seniority,
                            employment_type="clt",
                            area="Tecnologia",
                            description=desc_clean[:6000],
                            salary_min=salary_min,
                            salary_max=salary_max,
                            currency=currency,
                            requirements=[],
                            nice_to_have=item.get("jobIndustry") or [],
                            published_at=pub_dt,
                            date_status=date_status,
                            raw_data=item
                        )
                        jobs.append(nj)

                    await asyncio.sleep(self.rate_limit_delay_seconds)

                except Exception as e:
                    self.circuit_breaker.record_failure(str(e))
                    break

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
