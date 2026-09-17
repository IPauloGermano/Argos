from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from .base import JobSource, NormalizedJob


class GlassdoorJobSource(JobSource):
    name = "glassdoor"

    def __init__(self, timeout: float = 25.0, max_pages: int = 2):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.base_url = "https://www.glassdoor.com.br/Vaga/brasil"

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Desenvolvedor"]
        term = roles[0] if roles else "tecnologia"
        slug = urllib.parse.quote(term.lower().replace(" ", "-"))
        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"

            url = f"{self.base_url}-{slug}-vagas-SRCH_KO0,{len(slug)}.htm"
            try:
                resp = await client.get(url, headers=headers)
                self.pages_crawled += 1

                if resp.status_code in (403, 429):
                    self.circuit_breaker.record_failure(f"Glassdoor Cloudflare/Bot Protection ({resp.status_code})")
                    return []

                if resp.status_code != 200:
                    self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                    return []

                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.find_all("li", class_=lambda c: c and ("JobCard" in c or "react-job-listing" in c))

                for card in cards:
                    link_tag = card.find("a", href=True)
                    if not link_tag:
                        continue

                    title = link_tag.get_text(strip=True)
                    job_url = link_tag["href"]
                    if not job_url.startswith("http"):
                        job_url = f"https://www.glassdoor.com.br{job_url}"

                    company_tag = card.find("span", class_=lambda c: c and "Employer" in c)
                    company = company_tag.get_text(strip=True) if company_tag else "Empresa Confidencial"

                    loc_tag = card.find("div", class_=lambda c: c and "location" in c.lower())
                    location = loc_tag.get_text(strip=True) if loc_tag else "Brasil"

                    nj = NormalizedJob(
                        external_id=job_url,
                        source=self.name,
                        url=job_url,
                        title=title,
                        company=company,
                        location=location,
                        work_mode="remote" if "remoto" in location.lower() else "onsite",
                        seniority="",
                        employment_type="clt",
                        area="Tecnologia",
                        description=f"{title} na {company}",
                        salary_min=None,
                        salary_max=None,
                        currency="BRL",
                        published_at=None,
                        date_status="unknown_date",
                        raw_data={"url": job_url}
                    )
                    jobs.append(nj)

            except Exception as e:
                self.circuit_breaker.record_failure(str(e))

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
