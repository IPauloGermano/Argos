from __future__ import annotations
from datetime import datetime, timezone, timedelta
from .base import JobSource, NormalizedJob

_TITLES = [
    ("Backend Developer", "Python", ["Python", "FastAPI", "PostgreSQL", "Docker"], "mid", "remote", "clt", 8000.0, 12000.0),
    ("Software Engineer", "Python", ["Python", "Django", "PostgreSQL", "Redis"], "mid", "remote", "clt", 9000.0, 13000.0),
    ("Estágio em Desenvolvimento", "Python", ["Python", "Git", "SQL"], "estagio", "remote", "estagio", 2200.0, 2200.0),
    ("Estagiário de Desenvolvimento", "Python", ["Python", "Git", "SQL"], "estagio", "remote", "estagio", 2200.0, 2200.0),  # Intencional para teste de deduplicação
    ("Fullstack Developer", "TypeScript", ["TypeScript", "Next.js", "React", "PostgreSQL"], "mid", "hybrid", "clt", 7500.0, 11000.0),
    ("Data Engineer", "Python", ["Python", "SQL", "Airflow", "AWS"], "senior", "remote", "clt", 14000.0, 18000.0),
    ("DevOps Engineer", "Cloud", ["AWS", "Kubernetes", "Docker", "Terraform"], "senior", "remote", "clt", 15000.0, 20000.0),
    ("Frontend Developer", "React", ["TypeScript", "React", "Next.js", "Tailwind"], "junior", "remote", "clt", 5000.0, 7500.0),
    ("Trainee em Engenharia de Software", "Java", ["Java", "Spring Boot", "SQL"], "trainee", "hybrid", "trainee", 4500.0, 4500.0),
    ("Backend Developer Senior", "Python", ["Python", "FastAPI", "Celery", "Redis"], "senior", "remote", "clt", 16000.0, 22000.0),
]


class MockJobSource(JobSource):
    name = "mock"

    def __init__(self, count: int = 10):
        super().__init__(timeout=5.0, max_pages=1)
        self.count = count

    async def search(self, query: dict) -> list[NormalizedJob]:
        self.pages_crawled = 1
        roles = [r.lower() for r in (query.get("desired_roles") or [])] or ["backend"]
        jobs: list[NormalizedJob] = []

        now = datetime.now(timezone.utc)
        for i in range(max(1, self.count)):
            tpl = _TITLES[i % len(_TITLES)]
            title, stack, reqs, seniority, mode, emp_type, sal_min, sal_max = tpl
            want = roles[i % len(roles)]
            full_title = f"{title} ({want.title()})" if (want not in title.lower() and "estágio" not in title.lower()) else title

            # Variação de data para teste de frescor
            pub_date = now - timedelta(days=(i * 3))

            jobs.append(NormalizedJob(
                external_id=f"mock-{i}-{title.lower().replace(' ', '-')}",
                source="mock",
                url=f"https://example.com/jobs/mock-{i}",
                title=full_title,
                company=f"Empresa Alpha {i % 3 + 1}",
                location="Brasil (Remoto)" if mode == "remote" else "São Paulo, SP",
                work_mode=mode,
                seniority=seniority,
                employment_type=emp_type,
                area="Tecnologia",
                description=f"Oportunidade {full_title} com foco em {stack}. Tecnologias: {', '.join(reqs)}.",
                salary_min=sal_min,
                salary_max=sal_max,
                currency="BRL",
                requirements=reqs,
                nice_to_have=["English", "AWS"],
                published_at=pub_date,
                date_status="verified",
                raw_data={"mock_id": i}
            ))

        self.circuit_breaker.record_success()
        self.last_status = "success"
        return jobs
