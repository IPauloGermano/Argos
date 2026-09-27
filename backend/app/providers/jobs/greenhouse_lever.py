from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from .base import JobSource, NormalizedJob

# Boards verificados via rede real em 2026-09-27:
# - Greenhouse: vtex/gitlab/cloudflare retornam 200 com jobs; nubank 200 vazio; loft 404.
# - Lever: apenas 'spotify' confirmado (200 com lista); nubank/quintoandar/loft/vtex/
#   netflix/duolingo/airbnb/stripe/cloudflare retornam 404 (boards inexistentes).
# Suporte Lever = parcial e explícito (1 board verificado).
DEFAULT_GREENHOUSE_BOARDS = ["vtex", "gitlab", "cloudflare", "stripe"]
DEFAULT_LEVER_BOARDS = ["spotify"]


class CorporateATSJobSource(JobSource):
    """Agregador Greenhouse + Lever parcial (nome legado 'greenhouse' por compat).

    - Greenhouse: boards-api.greenhouse.io (suporte completo: paginação da API,
      múltiplos boards, falhas 429/5xx registradas, 404 de board conta como
      `disabled` sem poluir o circuit breaker).
    - Lever: api.lever.co (suporte PARCIAL e explícito: apenas boards verificados
      em DEFAULT_LEVER_BOARDS; endpoint sem paginação — retorna a lista do board).
    Ambos só leitura, sem auth.
    """
    name = "greenhouse"
    lever_partial: bool = True

    def __init__(self, timeout: float = 20.0, max_pages: int = 3):
        super().__init__(timeout=timeout, max_pages=max_pages)

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = query.get("desired_roles") or ["Developer", "Engineer"]
        preferred_companies = query.get("preferred_companies") or []
        boards = [c.lower().replace(" ", "") for c in preferred_companies] if preferred_companies else DEFAULT_GREENHOUSE_BOARDS[:2]
        known_urls = query.get("known_urls") or set()
        known_ids = query.get("known_ids") or set()

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
                    if resp.status_code in (404, 410):
                        # Board inexistente/removido: distinto de falha transitória.
                        # Não polui o circuit breaker; só marca para telemetria.
                        self.last_status = "disabled"
                        continue
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"Greenhouse HTTP {resp.status_code} board={board}")
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
                        if job_id in known_ids or job_url in known_urls:
                            continue
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

            # Lever: api.lever.co/v0/postings/{board} (best-effort, não bloqueia Greenhouse)
            for board in (DEFAULT_LEVER_BOARDS[:1] if not preferred_companies else []):
                url = f"https://api.lever.co/v0/postings/{board}"
                try:
                    resp = await client.get(url, headers=headers)
                    self.pages_crawled += 1
                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("Lever 429")
                        break
                    if resp.status_code in (404, 410):
                        # Board Lever inexistente: suporte parcial — ignora sem
                        # contar como falha do provider.
                        continue
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"Lever HTTP {resp.status_code} board={board}")
                        continue
                    raw_jobs = resp.json() or []
                    for it in raw_jobs if isinstance(raw_jobs, list) else []:
                        title = str(it.get("text") or "").strip()
                        if roles and not any(r.lower() in title.lower() for r in roles):
                            continue
                        job_id = str(it.get("id") or "")
                        job_url = str(it.get("hostedUrl") or f"https://jobs.lever.co/{board}/{job_id}")
                        if job_id in known_ids or job_url in known_urls:
                            continue
                        loc = str((it.get("categories") or {}).get("location") or "Remoto")
                        work_mode = "remote" if "remote" in loc.lower() else "onsite"
                        nj = NormalizedJob(
                            external_id=f"lever-{board}-{job_id}",
                            source=self.name,
                            url=job_url,
                            title=title,
                            company=board.capitalize(),
                            location=loc,
                            work_mode=work_mode,
                            seniority="",
                            employment_type="clt",
                            area="Tecnologia",
                            description=f"{title} na {board.capitalize()} - {loc}",
                            published_at=None,
                            date_status="unknown_date",
                            raw_data=it,
                        )
                        jobs.append(nj)
                except Exception as e:
                    self.circuit_breaker.record_failure(f"Lever {type(e).__name__}")
                    continue

        if jobs:
            self.circuit_breaker.record_success()
            self.last_status = "success"
        elif self.pages_crawled > 0:
            self.circuit_breaker.record_success()
            self.last_status = "empty"

        return jobs
