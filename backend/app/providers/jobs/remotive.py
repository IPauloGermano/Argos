from __future__ import annotations
from datetime import datetime, timezone
import re
import httpx
from .base import JobSource, NormalizedJob

API_URL = "https://remotive.com/api/remote-jobs"


def _infer_seniority(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("principal", "staff", "lead")):
        return "senior"
    if "senior" in t or "sr " in t or "sênior" in t:
        return "senior"
    if "junior" in t or "jr " in t or "júnior" in t or "entry" in t:
        return "junior"
    return "mid"


class RemotiveJobSource(JobSource):
    """API pública, sem autenticação, uso permitido. https://remotive.com/api/remote-jobs"""
    name = "remotive"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles: list[str] = query.get("desired_roles") or ["python"]
        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.get_default_headers()) as client:
            for role in roles[:3]:
                try:
                    r = await client.get(API_URL, params={"search": role, "limit": 20})
                    self.pages_crawled += 1
                    r.raise_for_status()

                    for item in r.json().get("jobs", [])[:20]:
                        desc = re.sub(r"<[^>]+>", " ", item.get("description") or "")
                        pub_dt = None
                        date_status = "unknown_date"
                        raw_pub = item.get("publication_date")
                        if raw_pub:
                            try:
                                pub_dt = datetime.fromisoformat(raw_pub.replace("Z", "+00:00"))
                                date_status = "verified"
                            except Exception:
                                pass

                        jobs.append(NormalizedJob(
                            external_id=f"remotive-{item.get('id')}",
                            source="remotive",
                            url=item.get("url") or "",
                            title=item.get("title") or "",
                            company=item.get("company_name") or "",
                            location=item.get("candidate_required_location") or "Remote",
                            work_mode="remote",
                            seniority=_infer_seniority(f"{item.get('title','')} {desc}"),
                            employment_type=item.get("job_type") or "clt",
                            area="Tecnologia",
                            description=desc[:8000],
                            salary_min=None,
                            salary_max=None,
                            currency="USD",
                            requirements=[],
                            nice_to_have=item.get("tags") or [],
                            published_at=pub_dt,
                            date_status=date_status,
                            raw_data=item
                        ))
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
