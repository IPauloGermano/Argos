from __future__ import annotations
import asyncio
import email.utils
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx
from .base import JobSource, NormalizedJob


def _infer_seniority(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("principal", "staff", "lead", "architect", "head of")):
        return "senior"
    if any(k in t for k in ("senior", "sr", "sênior", "sr.")):
        return "senior"
    if any(k in t for k in ("junior", "jr", "júnior", "jr.", "trainee", "entry", "intern")):
        return "junior"
    return "mid"


class WeWorkRemotelyJobSource(JobSource):
    """
    Conector para We Work Remotely (https://weworkremotely.com).
    A maior plataforma internacional de vagas remotas para tecnologia (EUA e Global).
    Feed RSS público, somente leitura, sem necessidade de autenticação.
    """
    name = "weworkremotely"

    def __init__(self, timeout: float = 20.0, max_pages: int = 2):
        super().__init__(timeout=timeout, max_pages=max_pages)
        self.feed_urls = [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        ]

    async def search(self, query: dict) -> list[NormalizedJob]:
        if not self.circuit_breaker.can_execute():
            self.last_status = "circuit_open"
            return []

        roles = [r.lower() for r in (query.get("desired_roles") or ["software", "python"])]
        jobs: list[NormalizedJob] = []
        seen_urls: set[str] = set()
        self.pages_crawled = 0

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.get_default_headers()) as client:
            for feed_url in self.feed_urls[:min(self.max_pages, len(self.feed_urls))]:
                try:
                    resp = await client.get(feed_url)
                    self.pages_crawled += 1

                    if resp.status_code == 429:
                        self.circuit_breaker.record_failure("WWR Rate Limit 429")
                        break
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure(f"HTTP {resp.status_code}")
                        break

                    try:
                        root = ET.fromstring(resp.content)
                        items = root.findall(".//item")
                    except Exception:
                        items = []

                    if not items:
                        continue

                    for item in items:
                        title_raw = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        desc_raw = (item.findtext("description") or "").strip()
                        region = (item.findtext("region") or "USA / Worldwide").strip()
                        pub_date_str = item.findtext("pubDate")

                        if not title_raw or not link or link in seen_urls:
                            continue
                        seen_urls.add(link)

                        # Separa formato comum "Empresa: Título da Vaga"
                        if ": " in title_raw:
                            parts = title_raw.split(": ", 1)
                            company = parts[0].strip()
                            title = parts[1].strip()
                        else:
                            company = "Empresa Remota (WWR)"
                            title = title_raw

                        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw).strip()

                        # Data de publicação RFC 2822
                        pub_dt = None
                        date_status = "unknown_date"
                        if pub_date_str:
                            try:
                                parsed = email.utils.parsedate_to_datetime(pub_date_str)
                                pub_dt = parsed.astimezone(timezone.utc)
                                date_status = "verified"
                            except Exception:
                                pass

                        seniority = _infer_seniority(f"{title} {desc_clean}")

                        nj = NormalizedJob(
                            external_id=link,
                            source=self.name,
                            url=link,
                            title=title,
                            company=company,
                            location=region,
                            work_mode="remote",
                            seniority=seniority,
                            employment_type="clt",
                            area="Tecnologia",
                            description=desc_clean[:6000],
                            salary_min=None,
                            salary_max=None,
                            currency="USD",
                            requirements=[],
                            nice_to_have=[],
                            published_at=pub_dt,
                            date_status=date_status,
                            raw_data={"rss_pubdate": pub_date_str, "region": region}
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
