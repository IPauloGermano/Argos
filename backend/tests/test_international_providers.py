import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.providers.jobs.getonbrd import GetOnBoardJobSource
from app.providers.jobs.weworkremotely import WeWorkRemotelyJobSource
from app.providers.jobs.jobicy import JobicyJobSource
from app.providers.jobs.factory import get_job_sources, SOURCE_REGISTRY
from app.providers.jobs.linkedin import LinkedInJobSource
from app.services.validation import validate_job


def test_factory_registers_international_sources():
    """Valida que getonbrd, weworkremotely e jobicy estão registrados e instanciáveis."""
    assert "getonbrd" in SOURCE_REGISTRY
    assert "weworkremotely" in SOURCE_REGISTRY
    assert "jobicy" in SOURCE_REGISTRY

    sources = get_job_sources(["getonbrd", "weworkremotely", "jobicy"])
    names = [s.name for s in sources]
    assert "getonbrd" in names
    assert "weworkremotely" in names
    assert "jobicy" in names


def test_getonbrd_search_parsing():
    """Valida parsing de vagas da API do Get on Board (Chile/LatAm)."""
    src = GetOnBoardJobSource(max_pages=1)
    src.circuit_breaker.record_success()

    fake_item = {
        "id": "senior-python-engineer-falabella-chile",
        "type": "job",
        "links": {"public_url": "https://www.getonbrd.com/jobs/senior-python-engineer-falabella-chile"},
        "attributes": {
            "title": "Senior Python Engineer",
            "description": "<p>Desarrollo backend en Python y AWS.</p>",
            "functions": "<p>Diseñar microservicios escalables.</p>",
            "benefits": "<p>Seguro de salud complementario y bono anual.</p>",
            "remote": True,
            "remote_modality": "full_remote",
            "countries": ["Chile"],
            "location_cities": {"data": [{"name": "Santiago"}]},
            "min_salary": 3500,
            "max_salary": 4500,
            "published_at": 1758000000,
            "seniority": "senior",
            "tags": ["python", "aws", "docker"],
            "company": {"data": {"id": 999}}
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [fake_item]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        jobs = asyncio.run(src.search({"desired_roles": ["Python"], "locations": ["Chile"]}))

    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Senior Python Engineer"
    assert "Santiago" in j.location or "Chile" in j.location
    assert j.work_mode == "remote"
    assert j.salary_min == 3500.0
    assert j.salary_max == 4500.0
    assert j.date_status == "verified"
    assert j.published_at is not None
    assert j.url == "https://www.getonbrd.com/jobs/senior-python-engineer-falabella-chile"


def test_weworkremotely_rss_parsing():
    """Valida parsing de vagas do feed RSS do We Work Remotely (EUA/Global)."""
    src = WeWorkRemotelyJobSource(max_pages=1)
    src.circuit_breaker.record_success()

    fake_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>GitLab: Senior Backend Engineer, Python</title>
          <link>https://weworkremotely.com/remote-jobs/gitlab-senior-backend-engineer-python</link>
          <description>&lt;p&gt;Work on GitLab core platform in Python.&lt;/p&gt;</description>
          <region>USA / Worldwide</region>
          <pubDate>Mon, 15 Sep 2026 14:00:00 +0000</pubDate>
        </item>
      </channel>
    </rss>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_xml

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        jobs = asyncio.run(src.search({"desired_roles": ["Python"]}))

    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "GitLab"
    assert j.title == "Senior Backend Engineer, Python"
    assert j.work_mode == "remote"
    assert j.location == "USA / Worldwide"
    assert j.date_status == "verified"
    assert j.published_at is not None
    assert "gitlab" in j.url


def test_jobicy_api_parsing():
    """Valida parsing da API pública do Jobicy (EUA/Remoto)."""
    src = JobicyJobSource(max_pages=1)
    src.circuit_breaker.record_success()

    fake_job = {
        "id": 12345,
        "url": "https://jobicy.com/jobs/12345-python-engineer",
        "jobTitle": "Lead Python Engineer",
        "companyName": "Automattic",
        "jobGeo": "USA",
        "jobLevel": "Senior",
        "jobDescription": "<p>Develop distributed systems with Python and Kubernetes.</p>",
        "pubDate": "2026-09-16T12:00:00+00:00",
        "salaryMin": 140000,
        "salaryMax": 180000,
        "salaryCurrency": "USD"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobs": [fake_job]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        jobs = asyncio.run(src.search({"desired_roles": ["Python"]}))

    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Lead Python Engineer"
    assert j.company == "Automattic"
    assert "USA" in j.location
    assert j.salary_min == 140000.0
    assert j.salary_max == 180000.0
    assert j.currency == "USD"
    assert j.date_status == "verified"
    assert j.published_at is not None


def test_linkedin_foreign_location_preserves_country():
    """Garante que locais no exterior não recebam ', Brasil' erroneamente."""
    src = LinkedInJobSource(max_pages=1)
    query = {
        "desired_roles": ["Python"],
        "locations": ["Santiago, Chile", "Asunción, Paraguay", "United States", "Campinas, SP"]
    }

    # Intercepta as chamadas para verificar os targets gerados
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        asyncio.run(src.search(query))

        called_locations = [call.kwargs["params"]["location"] for call in mock_get.call_args_list]
        assert "Santiago, Chile" in called_locations
        assert "Asunción, Paraguay" in called_locations
        assert "United States" in called_locations
        assert "Campinas, SP, Brasil" in called_locations
        assert "Santiago, Chile, Brasil" not in called_locations


def test_validation_accepts_foreign_jobs_when_requested():
    """Valida que vagas em Santiago, Chile ou Paraguai são aceitas se o usuário tiver interesse no exterior."""
    prefs = {
        "desired_roles": ["Desenvolvedor Python"],
        "locations": ["Santiago, Chile", "Remoto"],
        "work_modes": ["remote", "hybrid", "onsite"],
    }
    job_chile_onsite = {
        "title": "Desenvolvedor Python Pleno",
        "company": "Banco de Chile",
        "url": "https://bancochile.cl/vaga/1",
        "description": "Vaga em Santiago, Chile para atuação com Python e Django.",
        "location": "Santiago, Chile",
        "work_mode": "onsite",
    }
    is_valid, reason = validate_job(job_chile_onsite, prefs)
    assert is_valid is True, f"Vaga no Chile deveria ter sido aceita: {reason}"
