from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings
from .base import JobSource, NormalizedJob

SALARY_RE = re.compile(
    r"R\$\s*([\d.]+),(\d{2})(?:\s*[–—-]\s*R\$\s*([\d.]+),(\d{2}))?"
)


def _parse_brl_salary(text: str) -> tuple[float | None, float | None]:
    m = SALARY_RE.search(text or "")
    if not m:
        return None, None

    def num(int_part: str, dec_part: str) -> float | None:
        try:
            return float(int_part.replace(".", "") + "." + dec_part)
        except (ValueError, TypeError):
            return None

    lo = num(m.group(1), m.group(2))
    hi = num(m.group(3), m.group(4)) if m.group(3) else lo
    return lo, hi


class IndeedJobSource(JobSource):
    name = "indeed"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.rss_url = "https://br.indeed.com/rss"

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Desenvolvedor"]
        keywords = roles[0] if roles else "TI"
        raw_locations = query.get("locations") or []
        target_locations = []
        for loc in raw_locations:
            clean_loc = loc.strip()
            if clean_loc and clean_loc.lower() not in ("remoto", "remote"):
                if clean_loc not in target_locations:
                    target_locations.append(clean_loc)
        if not target_locations:
            target_locations = ["Brasil"]

        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()

            for target_loc in target_locations:
                for page in range(min(self.max_pages, 2)):
                    start = page * 10
                    params = {
                        "q": keywords,
                        "l": target_loc,
                        "start": start,
                    }

                    try:
                        resp = await client.get(self.rss_url, params=params, headers=headers)
                        self.pages_crawled += 1

                        if resp.status_code == 429:
                            self.circuit_breaker.record_failure("Indeed Rate Limit 429")
                            break

                        if resp.status_code != 200:
                            self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                            break

                        # Parse XML RSS Feed
                        try:
                            root = ET.fromstring(resp.content)
                            items = root.findall(".//item")
                        except Exception:
                            items = []

                        if not items:
                            break

                        for item in items:
                            title = item.findtext("title") or ""
                            link = item.findtext("link") or ""
                            desc = item.findtext("description") or ""
                            source = item.findtext("source") or "Empresa Não Informada"
                            pub_date_str = item.findtext("pubDate")

                            # Separa empresa e título se vier formato "Título - Empresa"
                            company = source
                            if " - " in title and (source == "Empresa Não Informada" or not source):
                                parts = title.rsplit(" - ", 1)
                                title = parts[0]
                                company = parts[1]

                            pub_dt = None
                            date_status = "unknown_date"
                            if pub_date_str:
                                try:
                                    parsed = email.utils.parsedate_to_datetime(pub_date_str)
                                    pub_dt = parsed.astimezone(timezone.utc)
                                    date_status = "verified"
                                except Exception:
                                    pass

                            work_mode = "remote" if "remoto" in title.lower() or "remoto" in desc.lower() else "onsite"

                            # Extrai ID ou URL limpa
                            clean_url = link.split("&")[0] if "&" in link else link
                            if clean_url in (query.get("known_urls") or set()):
                                continue

                            nj = NormalizedJob(
                                external_id=clean_url,
                                source=self.name,
                                url=clean_url,
                                title=title.strip(),
                                company=company.strip(),
                                location="Brasil",
                                work_mode=work_mode,
                                seniority="",
                                employment_type="clt",
                                area="Tecnologia",
                                description=desc.strip(),
                                salary_min=None,
                                salary_max=None,
                                currency="BRL",
                                published_at=pub_dt,
                                date_status=date_status,
                                raw_data={"rss_pubdate": pub_date_str}
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
            # RSS morto (404) ou vazio: tenta fallback via browser renderizado.
            jobs = await self._search_browser(keywords)
            if jobs:
                self.circuit_breaker.record_success()
                self.last_status = "success-browser"
            else:
                self.circuit_breaker.record_success()
                self.last_status = "empty"

        return jobs

    async def _search_browser(self, keywords: str) -> list[NormalizedJob]:
        from app.providers.browser.cloak import cloak_available, fetch_rendered_html

        if not cloak_available():
            return []

        jobs: list[NormalizedJob] = []
        for page in range(min(self.max_pages, 1)):
            start = page * 10
            params = {"q": keywords, "l": "Brasil", "start": start}
            url = f"https://br.indeed.com/jobs?{urllib.parse.urlencode(params)}"
            try:
                html = await fetch_rendered_html(url, wait_ms=1500)
                self.pages_crawled += 1
                cards = self._parse_browser_cards(html)
                if not cards:
                    break
                jobs.extend(cards)
            except Exception as e:
                self.circuit_breaker.record_failure(f"browser: {type(e).__name__}")
                break
        return jobs

    def _parse_browser_cards(self, html: str) -> list[NormalizedJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[NormalizedJob] = []
        for card in soup.select("td.resultContent"):
            link = card.select_one("a.jcs-JobTitle")
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            href = link.get("href") or ""
            url = href if href.startswith("http") else f"https://br.indeed.com{href}"

            comp_el = card.select_one('[data-testid="company-name"]') or card.select_one("span.companyName")
            company = comp_el.get_text(" ", strip=True) if comp_el else "Empresa Não Informada"
            loc_el = card.select_one('[data-testid="text-location"]') or card.select_one("div.companyLocation")
            location = loc_el.get_text(" ", strip=True) if loc_el else "Brasil"

            text = card.get_text(" ", strip=True)
            salary_min, salary_max = _parse_brl_salary(text)
            low = text.lower()
            if "remoto" in low or "home office" in low:
                work_mode = "remote"
            elif "híbrido" in low or "hibrido" in low:
                work_mode = "hybrid"
            else:
                work_mode = "onsite"

            jobs.append(NormalizedJob(
                external_id=url,
                source=self.name,
                url=url,
                title=title,
                company=company,
                location=location,
                work_mode=work_mode,
                seniority="",
                # Tipo de contrato nao informado no card: vazio passa
                # pelo filtro sem rotular errado (validacao ignora "").
                employment_type="",
                area="Tecnologia",
                description=text[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                currency="BRL",
                published_at=None,
                date_status="unknown_date",
                raw_data={"via": "browser"},
            ))
        return jobs
