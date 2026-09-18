from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings
from .base import JobSource, NormalizedJob


class VagasComJobSource(JobSource):
    name = "vagas"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.base_url = settings.VAGAS_BASE_URL

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["desenvolvedor"]
        keyword = roles[0] if roles else "tecnologia"
        slug = urllib.parse.quote(keyword.lower().replace(" ", "-"))

        raw_locations = query.get("locations") or []
        foreign_keywords = (
            "brasil", "brazil", "remoto", "remote", "chile", "paraguai", "paraguay",
            "portugal", "ireland", "united kingdom", "dublin", "london", "santiago",
            "united states", "usa", "eua"
        )
        urls_to_crawl = [f"{self.base_url}/vagas-de-{slug}?pagina=1"]
        for loc in raw_locations:
            clean_loc = loc.strip()
            lower = clean_loc.lower()
            if not clean_loc or any(k in lower for k in foreign_keywords):
                continue
            city_slug = urllib.parse.quote(clean_loc.split(",")[0].split("-")[0].strip().lower().replace(" ", "-"))
            if len(city_slug) >= 3:
                urls_to_crawl.append(f"{self.base_url}/vagas-em-{city_slug}/{slug}")
                break
        urls_to_crawl = urls_to_crawl[:2]

        jobs: list[NormalizedJob] = []
        known_urls = query.get("known_urls") or set()
        known_ids = query.get("known_ids") or set()
        seen_urls: set[str] = set()
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=min(self.timeout, 6.0)) as client:
            headers = self.get_default_headers()

            for url in urls_to_crawl:
                try:
                    resp = await client.get(url, headers=headers)
                    self.pages_crawled += 1

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("Vagas.com 429 Rate Limit")
                        break

                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        break

                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")
                    cards = soup.find_all("li", class_=lambda c: c and "vaga" in c)
                    if not cards:
                        break

                    page_count = 0
                    for card in cards:
                        link_tag = card.find("a", class_=lambda c: c and "link-detalhes-vaga" in c)
                        if not link_tag or not link_tag.get("href"):
                            continue

                        rel_url = link_tag["href"]
                        full_url = f"{self.base_url}{rel_url}" if rel_url.startswith("/") else rel_url

                        # Extrai código da vaga da URL (ex: /vagas/v12345/...)
                        ext_id = ""
                        match = re.search(r"/v(\d+)/", full_url)
                        if match:
                            ext_id = match.group(1)
                        else:
                            ext_id = full_url

                        if full_url in seen_urls or full_url in known_urls or ext_id in known_ids:
                            continue
                        seen_urls.add(full_url)

                        title = link_tag.get_text(strip=True)

                        company_tag = card.find("span", class_=lambda c: c and ("empr" in c or "cargo" in c))
                        company = company_tag.get_text(strip=True) if company_tag else "Confidencial"

                        loc_tag = card.find("span", class_=lambda c: c and "vaga-local" in c)
                        location = loc_tag.get_text(strip=True) if loc_tag else "Brasil"

                        desc_tag = card.find("div", class_=lambda c: c and "detalhes" in c)
                        desc = desc_tag.get_text(strip=True) if desc_tag else title

                        work_mode = "remote" if "remoto" in location.lower() or "100% remoto" in desc.lower() else "onsite"

                        nj = NormalizedJob(
                            external_id=ext_id,
                            source=self.name,
                            url=full_url,
                            title=title,
                            company=company,
                            location=location,
                            work_mode=work_mode,
                            seniority="",
                            employment_type="clt",
                            area="Tecnologia",
                            description=desc,
                            salary_min=None,
                            salary_max=None,
                            currency="BRL",
                            published_at=None,
                            date_status="unknown_date",
                            raw_data={"url": full_url}
                        )
                        jobs.append(nj)
                        page_count += 1

                    if page_count == 0:
                        break

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
