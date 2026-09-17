from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import httpx
from .base import JobSource, NormalizedJob

_COMPANY_CACHE: dict[int, str] = {}


def _infer_seniority(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("principal", "staff", "lead", "arquitecto", "architect")):
        return "senior"
    if any(k in t for k in ("senior", "sr", "sênior", "sr.", "avanzado")):
        return "senior"
    if any(k in t for k in ("junior", "jr", "júnior", "jr.", "trainee", "entry", "inicial")):
        return "junior"
    return "mid"


class GetOnBoardJobSource(JobSource):
    """
    Conector para Get on Board (https://www.getonbrd.com).
    Principal plataforma de vagas de tecnologia para o Chile, Paraguai e América Latina.
    API pública e oficial, só leitura, sem necessidade de autenticação.
    """
    name = "getonbrd"

    def __init__(self, timeout: float = 20.0, max_pages: int = 2):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.api_url = "https://www.getonbrd.com/api/v0/search/jobs"
        self.company_url = "https://www.getonbrd.com/api/v0/companies"

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles: list[str] = query.get("desired_roles") or ["python"]
        locations: list[str] = query.get("locations") or []

        # Constrói termos de busca combinando tecnologia e locais desejados (Chile, Paraguai, etc.)
        search_terms = []
        for r in roles[:2]:
            clean_r = r.strip()
            if clean_r:
                search_terms.append(clean_r)

        # Adiciona buscas direcionadas se o usuário solicitou Chile, Paraguai ou LatAm
        for loc in locations:
            clean_l = loc.strip().lower()
            if any(k in clean_l for k in ("chile", "santiago", "paraguai", "paraguay", "asuncion", "latam")):
                search_terms.append(f"{roles[0] if roles else 'software'} {loc.strip()}")

        if not search_terms:
            search_terms = ["software"]

        jobs: list[NormalizedJob] = []
        seen_ids: set[str] = set()
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.get_default_headers()) as client:
            for term in search_terms[:3]:
                for page in range(1, min(self.max_pages, 2) + 1):
                    params = {
                        "query": term,
                        "per_page": 20,
                        "page": page,
                    }
                    try:
                        resp = await client.get(self.api_url, params=params)
                        self.pages_crawled += 1

                        if resp.status_code == 429:
                            self.circuit_breaker.record_failure("Get on Board Rate Limit 429")
                            break
                        if resp.status_code != 200:
                            self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                            break

                        payload = resp.json()
                        data = payload.get("data", [])
                        if not data:
                            break

                        for it in data:
                            job_id = it.get("id") or ""
                            if not job_id or job_id in seen_ids:
                                continue
                            seen_ids.add(job_id)

                            attr = it.get("attributes", {})
                            title = (attr.get("title") or "").strip()
                            if not title:
                                continue

                            # Resolução de empresa via cache ou endpoint público
                            comp_id = attr.get("company", {}).get("data", {}).get("id")
                            company_name = "Empresa Confidencial (Get on Board)"
                            if comp_id:
                                if comp_id in _COMPANY_CACHE:
                                    company_name = _COMPANY_CACHE[comp_id]
                                else:
                                    try:
                                        c_resp = await client.get(f"{self.company_url}/{comp_id}")
                                        if c_resp.status_code == 200:
                                            c_data = c_resp.json().get("data", {}).get("attributes", {})
                                            company_name = c_data.get("name") or company_name
                                            _COMPANY_CACHE[comp_id] = company_name
                                    except Exception:
                                        pass

                            # Localização e países
                            countries = attr.get("countries") or []
                            cities_data = attr.get("location_cities", {}).get("data") or []
                            cities = [c.get("name") for c in cities_data if isinstance(c, dict) and c.get("name")]
                            if cities:
                                location_str = f"{', '.join(cities[:2])} - {', '.join(countries[:1])}"
                            elif countries:
                                location_str = ", ".join(countries[:2])
                            else:
                                location_str = "Chile / América Latina"

                            # Modalidade
                            is_remote = bool(attr.get("remote"))
                            modality = (attr.get("remote_modality") or "").lower()
                            if is_remote and "hybrid" in modality:
                                work_mode = "hybrid"
                            elif is_remote or "remote" in modality:
                                work_mode = "remote"
                            else:
                                work_mode = "onsite"

                            # Descrição limpa
                            raw_desc = f"{attr.get('description', '')} {attr.get('functions', '')} {attr.get('benefits', '')}"
                            desc_clean = re.sub(r"<[^>]+>", " ", raw_desc).strip()

                            # URL
                            links = it.get("links", {})
                            url = links.get("public_url") or f"https://www.getonbrd.com/jobs/{job_id}"

                            # Salário
                            sal_min = attr.get("min_salary")
                            sal_max = attr.get("max_salary")
                            salary_min = float(sal_min) if sal_min else None
                            salary_max = float(sal_max) if sal_max else None

                            # Data de publicação
                            pub_ts = attr.get("published_at")
                            pub_dt = None
                            date_status = "unknown_date"
                            if pub_ts:
                                try:
                                    pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                                    date_status = "verified"
                                except Exception:
                                    pass

                            # Senioridade
                            sen = attr.get("seniority") or _infer_seniority(f"{title} {desc_clean}")

                            nj = NormalizedJob(
                                external_id=f"getonbrd-{job_id}",
                                source=self.name,
                                url=url,
                                title=title,
                                company=company_name,
                                location=location_str,
                                work_mode=work_mode,
                                seniority=sen,
                                employment_type="clt",
                                area="Tecnologia",
                                description=desc_clean[:6000],
                                salary_min=salary_min,
                                salary_max=salary_max,
                                currency="USD",
                                requirements=[],
                                nice_to_have=attr.get("tags") or [],
                                published_at=pub_dt,
                                date_status=date_status,
                                raw_data=it
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
