from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from .base import JobSource, NormalizedJob

# Exemplos de boards conhecidos com vagas de tecnologia
DEFAULT_GREENHOUSE_BOARDS = ["vtex", "gitlab", "cloudflare", "stripe"]
DEFAULT_LEVER_BOARDS = ["nubank", "quintoandar", "loft"]


class CorporateATSJobSource(JobSource):
    name = "greenhouse"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Developer", "Engineer"]
        preferred_companies = query.get("preferred_companies") or []
        boards = [c.lower().replace(" ", "") for c in preferred_companies] if preferred_companies else DEFAULT_GREENHOUSE_BOARDS[:2]

        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()

            for board in boards:
                url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
                try:
                    resp = await client.get(url, headers=headers)
                    self.pages_crawled += 1

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("Greenhouse 429")
                        break
                    if resp.status_code != 200:
                        continue

                    payload = resp.json()
                    raw_jobs = payload.get("jobs") or []

                    for it in raw_jobs:
                        title = str(it.get("title") or "").strip()
                        # Filtra se título tem correlação com os cargos desejados
                        if roles and not any(r.lower() in title.lower() for r in roles):
                            continue

                        job_id = str(it.get("id") or "")
                        job_url = str(it.get("absolute_url") or f"https://boards.greenhouse.io/{board}/jobs/{job_id}")
                        location = it.get("location", {}).get("name", "Remoto / Global")
                        work_mode = "remote" if "remote" in location.lower() or "remoto" in location.lower() else "onsite"

                        # Data de atualização
                        pub_dt = None
                        date_status = "unknown_date"
                        updated_at = it.get("updated_at")
                        if updated_at:
                            try:
                                pub_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                                date_status = "verified"
                            except Exception:
                                pass

                        nj = NormalizedJob(
                            external_id=job_id,
                            source=self.name,
                            url=job_url,
                            title=title,
                            company=board.capitalize(),
                            location=location,
                            work_mode=work_mode,
                            seniority="",
                            employment_type="clt",
                            area="Tecnologia",
                            description=f"{title} na {board.capitalize()} - {location}",
                            salary_min=None,
                            salary_max=None,
                            currency="USD" if "global" in location.lower() else "BRL",
                            published_at=pub_dt,
                            date_status=date_status,
                            raw_data=it
                        )
                        jobs.append(nj)

                    await asyncio.sleep(self.rate_limit_delay_seconds)

                except Exception as e:
                    self.circuit_breaker.record_failure(str(e))
                    continue

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
