from __future__ import annotations
import asyncio
from datetime import datetime
import html
import json
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from .base import JobSource, NormalizedJob

# O portal Gupy (Next.js SSR) embute a lista de vagas no __NEXT_DATA__ da
# pagina /job-search/term=<termo>. A antiga API publica /api/v1/jobs foi
# descontinuada e hoje retorna o HTML da homepage.
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
PAGE_SIZE = 12


def _clean_html(raw: str, limit: int = 2000) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    if "<" in text:
        try:
            text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
        except Exception:
            text = re.sub(r"<[^>]+>", " ", text)
    # Entidades coladas (&nbsp; decodificado vira \xa0): normaliza tudo.
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _map_employment_type(raw_type: str) -> str:
    t = (raw_type or "").lower()
    if "estag" in t or "intern" in t:
        return "estagio"
    if "trainee" in t:
        return "trainee"
    if "aprendiz" in t or "apprentice" in t:
        return "jovem_aprendiz"
    if "pj" in t or "contract" in t:
        return "pj_contrato"
    return "clt"


def _map_work_mode(item: dict) -> str:
    wt = str(item.get("workplaceType") or "").lower()
    if item.get("isRemoteWork") or "remot" in wt:
        return "remote"
    if "hibrid" in wt or "hybrid" in wt:
        return "hybrid"
    return "onsite"


class GupyJobSource(JobSource):
    name = "gupy"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.search_base = "https://portal.gupy.io/job-search"

    def _parse_page(self, html: str) -> tuple[list[dict], int]:
        m = NEXT_DATA_RE.search(html)
        if not m:
            return [], 0
        try:
            data = json.loads(m.group(1))
        except Exception:
            return [], 0
        initial = data.get("props", {}).get("pageProps", {}).get("initialJobList", {})
        items = initial.get("data") or []
        total = (initial.get("pagination") or {}).get("total", 0)
        return items, total

    def _normalize(self, item: dict) -> NormalizedJob:
        ext_id = str(item.get("id") or "")
        title = str(item.get("name") or "").strip()
        company = str(item.get("careerPageName") or "").strip()
        job_url = str(item.get("jobUrl") or f"https://portal.gupy.io/job/{ext_id}")

        work_mode = _map_work_mode(item)
        city = item.get("city") or ""
        state = item.get("state") or ""
        location = f"{city} - {state}".strip(" -") if (city or state) else ("Remoto" if work_mode == "remote" else "Brasil")

        pub_dt = None
        date_status = "unknown_date"
        raw_date = item.get("publishedDate")
        if raw_date:
            try:
                pub_dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                date_status = "verified"
            except Exception:
                pass

        return NormalizedJob(
            external_id=ext_id,
            source=self.name,
            url=job_url,
            title=title,
            company=company,
            location=location,
            work_mode=work_mode,
            seniority="",
            employment_type=_map_employment_type(str(item.get("type") or "")),
            area="Tecnologia",
            description=_clean_html(str(item.get("description") or title)),
            salary_min=None,
            salary_max=None,
            currency="BRL",
            published_at=pub_dt,
            date_status=date_status,
            raw_data={"gupy_id": ext_id},
        )

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Desenvolvedor Python"]
        terms_to_search = []
        for r in roles[:2]:
            if r and r not in terms_to_search:
                terms_to_search.append(r)

        # Garante busca por Python e Backend
        for tech_term in ["Python", "Desenvolvedor Backend"]:
            if tech_term not in terms_to_search and len(terms_to_search) < 3:
                terms_to_search.append(tech_term)

        # Adiciona no máximo 1 busca regional brasileira relevante (ignora países e cidades do exterior)
        raw_locations = query.get("locations") or []
        foreign_keywords = (
            "brasil", "brazil", "remoto", "remote", "chile", "paraguai", "paraguay",
            "portugal", "ireland", "united kingdom", "dublin", "london", "santiago",
            "united states", "usa", "eua"
        )
        for loc in raw_locations:
            clean_loc = loc.strip()
            lower = clean_loc.lower()
            if not clean_loc or any(k in lower for k in foreign_keywords):
                continue
            city_name = clean_loc.split(",")[0].split("-")[0].strip()
            if len(city_name) >= 3:
                terms_to_search.append(f"Desenvolvedor {city_name}")
                break

        unique_terms = []
        for t in terms_to_search:
            if t not in unique_terms:
                unique_terms.append(t)
        unique_terms = unique_terms[:4]

        known_urls = query.get("known_urls") or set()
        known_ids = query.get("known_ids") or set()

        jobs: list[NormalizedJob] = []
        seen_ids: set[str] = set()
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=min(self.timeout, 8.0), follow_redirects=True) as client:
            headers = self.get_default_headers()
            headers["Referer"] = "https://portal.gupy.io/"

            async def _fetch_term(term: str) -> list[NormalizedJob]:
                slug = urllib.parse.quote(term.strip(), safe="")
                url = f"{self.search_base}/term={slug}"
                term_jobs: list[NormalizedJob] = []
                try:
                    resp = await client.get(url, headers=headers)
                    self.pages_crawled += 1
                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("Rate limit 429")
                        return []
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        return []

                    items, total = self._parse_page(resp.text)
                    if not items:
                        return []

                    for item in items:
                        ext_id = str(item.get("id") or "")
                        job_url = str(item.get("jobUrl") or f"https://portal.gupy.io/job/{ext_id}")
                        if ext_id in known_ids or job_url in known_urls:
                            continue

                        try:
                            nj = self._normalize(item)
                            term_jobs.append(nj)
                        except Exception:
                            continue
                except Exception as e:
                    self.circuit_breaker.record_failure(str(e))
                return term_jobs

            results = await asyncio.gather(*[_fetch_term(t) for t in unique_terms], return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    for nj in res:
                        if nj.external_id not in seen_ids:
                            seen_ids.add(nj.external_id)
                            jobs.append(nj)

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
