from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from app.core.config import settings
from .base import JobSource, NormalizedJob


class CIEEJobSource(JobSource):
    name = "ciee"

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.api_url = "https://web.ciee.org.br/api/vagas/publicas"

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Tecnologia"]
        term = roles[0] if roles else "TI"
        jobs: list[NormalizedJob] = []
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = self.get_default_headers()

            for page in range(1, self.max_pages + 1):
                params = {
                    "termo": term,
                    "pagina": page,
                    "tamanho": 15,
                }

                try:
                    resp = await client.get(self.api_url, params=params, headers=headers)
                    self.pages_crawled += 1

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("CIEE Rate Limit 429")
                        break

                    if resp.status_code not in (200, 201):
                        # CIEE pode requerer fallback para busca web pública
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        break

                    payload = resp.json()
                    items = payload.get("conteudo") or payload.get("itens") or []
                    if not items:
                        break

                    for it in items:
                        ext_id = str(it.get("codigo") or it.get("id") or "")
                        title = str(it.get("titulo") or it.get("curso") or f"Estágio {term}").strip()
                        company = str(it.get("empresa") or "Empresa Parceira CIEE").strip()
                        city = it.get("cidade") or ""
                        uf = it.get("uf") or ""
                        location = f"{city} - {uf}".strip(" -") or "Brasil"

                        bolsa = it.get("valorBolsa") or it.get("bolsa")
                        salary_min = None
                        if bolsa:
                            try:
                                salary_min = float(bolsa)
                            except (ValueError, TypeError):
                                pass

                        tipo_vaga = str(it.get("tipoVaga") or "estagio").lower()
                        emp_type = "estagio"
                        if "aprendiz" in tipo_vaga:
                            emp_type = "jovem_aprendiz"
                        elif "trainee" in tipo_vaga:
                            emp_type = "trainee"

                        nj = NormalizedJob(
                            external_id=ext_id,
                            source=self.name,
                            url=f"https://web.ciee.org.br/vaga/{ext_id}" if ext_id else "https://web.ciee.org.br",
                            title=title,
                            company=company,
                            location=location,
                            work_mode="onsite",
                            seniority="estagio",
                            employment_type=emp_type,
                            area="Tecnologia",
                            description=str(it.get("descricao") or f"Vaga de {emp_type} CIEE para {title}"),
                            salary_min=salary_min,
                            salary_max=salary_min,
                            currency="BRL",
                            published_at=datetime.now(timezone.utc),
                            date_status="verified",
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
