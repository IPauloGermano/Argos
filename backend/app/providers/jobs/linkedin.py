from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings
from .base import JobSource, NormalizedJob


class LinkedInJobSource(JobSource):
    name = "linkedin"

    def __init__(self, timeout: float = 25.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.base_url = settings.LINKEDIN_GUEST_API_URL
        self.rate_limit_delay_seconds = 0.3

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Desenvolvedor"]
        keywords_list = roles[:2] if len(roles) >= 2 else roles
        if not keywords_list:
            keywords_list = ["Desenvolvedor"]

        # Extrai localizações prioritárias configuradas pelo candidato
        raw_locations = query.get("locations") or []
        regional_targets: list[str] = []
        for loc in raw_locations:
            clean = loc.strip()
            if not clean:
                continue
            lower = clean.lower()
            if lower in ("remoto", "remote"):
                continue
            known_foreign = (
                "chile", "paraguai", "paraguay", "estados unidos", "united states",
                "usa", "us", "argentina", "uruguay", "uruguai", "mexico", "méxico",
                "colombia", "colômbia", "peru", "portugal", "canada", "canadá",
                "reino unido", "uk", "alemanha", "germany", "espanha", "spain"
            )
            is_foreign = any(c in lower for c in known_foreign)
            target = clean if (is_foreign or lower.endswith("brasil") or lower.endswith("brazil")) else f"{clean}, Brasil"
            if target not in regional_targets:
                regional_targets.append(target)
        if not regional_targets:
            regional_targets = ["Brasil"]

        # Monta buscas direcionadas focadas no perfil sem redundâncias lentas
        search_targets: list[dict] = []
        user_roles = [r.strip() for r in (query.get("desired_roles") or []) if r.strip()]
        tech_terms = list(user_roles[:3]) if user_roles else ["Desenvolvedor"]

        for reg in regional_targets:
            for kw in tech_terms:
                geo_id = "106057199" if reg.lower() in ("brasil", "brasil, brasil") else None
                search_targets.append({"keywords": kw, "location": reg, "geoId": geo_id})

        # Adiciona no máximo 1 busca nacional com geoId se não coberto
        if "Brasil" not in regional_targets and not any(t.get("geoId") for t in search_targets):
            search_targets.append({"keywords": tech_terms[0], "location": "Brasil", "geoId": "106057199"})

        # Limita para máxima velocidade e proteção contra rate limit do LinkedIn
        search_targets = search_targets[:6]

        jobs: list[NormalizedJob] = []
        seen_urls: set[str] = set()
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()
            headers["Sec-Fetch-Site"] = "same-origin"
            headers["Sec-Fetch-Mode"] = "cors"

            for target in search_targets:
                params: dict = {
                    "keywords": target["keywords"],
                    "location": target["location"],
                    "start": 0,
                }
                if target.get("geoId"):
                    params["geoId"] = target["geoId"]

                try:
                    resp = await client.get(self.base_url, params=params, headers=headers)
                    self.pages_crawled += 1

                    if resp.status_code in (429, 999):
                        self.circuit_breaker.record_failure(f"LinkedIn Rate Limit / Bot Block (HTTP {resp.status_code})")
                        break

                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        continue

                    html = resp.text
                    if not html.strip():
                        continue

                    soup = BeautifulSoup(html, "html.parser")
                    cards = soup.find_all("li")
                    if not cards:
                        cards = soup.find_all("div", class_=lambda c: c and "base-card" in c)

                    for card in cards:
                        link_tag = card.find("a", class_=lambda c: c and ("base-card__full-link" in c or "job-card-list__title" in c))
                        if not link_tag or not link_tag.get("href"):
                            link_tag = card.find("a", href=True)
                            if not link_tag:
                                continue

                        job_url = link_tag.get("href", "").split("?")[0]
                        if not ("/jobs/view/" in job_url or "/jobs/" in job_url):
                            continue

                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        title_tag = card.find("h3", class_=lambda c: c and "base-search-card__title" in c)
                        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                        if not title:
                            continue

                        company_tag = card.find("h4", class_=lambda c: c and "base-search-card__subtitle" in c)
                        company = company_tag.get_text(strip=True) if company_tag else "Empresa Confidencial"

                        loc_tag = card.find("span", class_=lambda c: c and "job-search-card__location" in c)
                        location = loc_tag.get_text(strip=True) if loc_tag else target["location"]

                        time_tag = card.find("time")
                        pub_dt = None
                        date_status = "unknown_date"
                        if time_tag and time_tag.get("datetime"):
                            try:
                                raw_date = time_tag["datetime"]
                                pub_dt = datetime.fromisoformat(raw_date)
                                if pub_dt.tzinfo is None:
                                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                                else:
                                    pub_dt = pub_dt.astimezone(timezone.utc)
                                date_status = "verified"
                            except Exception:
                                pass

                        title_lower = title.lower()
                        loc_lower = location.lower()
                        is_remote = "remoto" in loc_lower or "remote" in loc_lower or "remoto" in title_lower or "remote" in title_lower
                        is_hybrid = "híbrido" in loc_lower or "hybrid" in loc_lower or "híbrido" in title_lower or "hybrid" in title_lower
                        work_mode = "remote" if is_remote else ("hybrid" if is_hybrid else "onsite")

                        # Extrai ID do LinkedIn da URL se presente
                        ext_id = ""
                        try:
                            parts = job_url.rstrip("/").split("-")
                            ext_id = parts[-1] if parts[-1].isdigit() else job_url.split("/")[-1]
                        except Exception:
                            ext_id = job_url

                        nj = NormalizedJob(
                            external_id=ext_id,
                            source=self.name,
                            url=job_url,
                            title=title,
                            company=company,
                            location=location,
                            work_mode=work_mode,
                            seniority="",
                            employment_type="clt",
                            area="Tecnologia",
                            description=f"{title} na {company} - {location}",
                            salary_min=None,
                            salary_max=None,
                            currency="BRL",
                            published_at=pub_dt,
                            date_status=date_status,
                            raw_data={"scraped_url": job_url}
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
