"""Adapter tests using httpx.MockTransport so nothing goes to the network."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from discovery.base import SearchQuery
from discovery.greenhouse import GreenhouseAdapter
from discovery.greenhouse import _normalize as gh_normalize
from discovery.lever import LeverAdapter
from discovery.lever import _normalize as lever_normalize
from discovery.remoteok import RemoteOKAdapter
from discovery.remotive import RemotiveAdapter
from discovery.themuse import TheMuseAdapter
from discovery.usajobs import USAJobsAdapter


def _install_mock(monkeypatch: pytest.MonkeyPatch, module_paths: list[str], handler: Callable[[httpx.Request], httpx.Response]) -> None:
    transport = httpx.MockTransport(handler)

    class StubClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    for path in module_paths:
        monkeypatch.setattr(f"{path}.httpx.AsyncClient", StubClient)


# ---------- Greenhouse -----------------------------------------------------


def test_greenhouse_normalize_extracts_fields() -> None:
    raw = {
        "id": 42,
        "requisition_id": "REQ-1",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
        "title": "AI Engineer",
        "location": {"name": "Remote — US"},
        "content": "<p>Build <b>autonomous</b> agents.</p>",
        "updated_at": "2026-01-15T00:00:00Z",
        "departments": [{"name": "Research"}],
    }
    job = gh_normalize(raw, company="acme")
    assert job is not None
    assert job.company == "acme"
    assert job.title == "AI Engineer"
    assert "autonomous" in job.description
    assert "<" not in job.description


@pytest.mark.asyncio
async def test_greenhouse_fetch_paginates_companies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"jobs": [{
            "id": 1,
            "absolute_url": f"https://ex{request.url.path}",
            "title": "AI Engineer",
            "location": {"name": "Remote"},
            "content": "python",
            "updated_at": "2026-01-01",
        }]})

    _install_mock(monkeypatch, ["discovery.greenhouse", "discovery.http"], handler)
    adapter = GreenhouseAdapter(companies=["acme", "widget"])
    jobs = await adapter.fetch(query=SearchQuery(), limit=10)
    assert len(jobs) == 2
    assert all(j.source == "greenhouse" for j in jobs)
    assert len(calls) == 2


# ---------- Lever ----------------------------------------------------------


def test_lever_normalize_extracts_fields() -> None:
    raw = {
        "id": "abc",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "text": "ML Engineer",
        "categories": {"location": "SF", "team": "ML", "workplaceType": "hybrid"},
        "descriptionPlain": "Work on models.",
        "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
    }
    job = lever_normalize(raw, company="acme")
    assert job is not None
    assert job.url.endswith("/abc")
    assert "Python" in job.description


@pytest.mark.asyncio
async def test_lever_fetch_handles_non_list_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "not a list"})

    _install_mock(monkeypatch, ["discovery.lever", "discovery.http"], handler)
    adapter = LeverAdapter(companies=["acme"])
    jobs = await adapter.fetch(query=SearchQuery(), limit=10)
    assert jobs == []


# ---------- USAJobs --------------------------------------------------------


@pytest.mark.asyncio
async def test_usajobs_fetch_parses_search_result(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "PositionURI": "https://usajobs.gov/GetJob/ViewDetails/1",
                        "PositionTitle": "IT Specialist",
                        "OrganizationName": "USDA",
                        "PositionLocation": [{"LocationName": "Washington, DC"}],
                        "PositionRemuneration": [{"MinimumRange": "80000", "MaximumRange": "120000", "RateIntervalCode": "PA"}],
                        "PublicationStartDate": "2026-01-01",
                        "UserArea": {"Details": {"JobSummary": "Do IT things.", "MajorDuties": ["A", "B"]}},
                    }
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "data.usajobs.gov"
        assert request.headers["Authorization-Key"] == "key"
        return httpx.Response(200, json=payload)

    _install_mock(monkeypatch, ["discovery.usajobs", "discovery.http"], handler)
    adapter = USAJobsAdapter(user_agent="ops@example.com", api_key="key")
    jobs = await adapter.fetch(query=SearchQuery(roles=["IT"]), limit=5)
    assert len(jobs) == 1
    assert jobs[0].company == "USDA"
    assert jobs[0].salary_min == 80000


def test_usajobs_disabled_without_credentials() -> None:
    assert USAJobsAdapter(user_agent=None, api_key=None).enabled() is False
    assert USAJobsAdapter(user_agent="e@x", api_key="k").enabled() is True


# ---------- The Muse -------------------------------------------------------


@pytest.mark.asyncio
async def test_themuse_fetch_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "name": "Software Engineer",
                "company": {"name": "Muse Corp"},
                "locations": [{"name": "Remote (USA)"}],
                "contents": "<p>Build stuff</p>",
                "publication_date": "2026-01-02",
                "refs": {"landing_page": "https://themuse.com/jobs/1"},
                "levels": [{"name": "Mid Level"}],
                "categories": [{"name": "Engineering"}],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _install_mock(monkeypatch, ["discovery.themuse", "discovery.http"], handler)
    adapter = TheMuseAdapter()
    jobs = await adapter.fetch(query=SearchQuery(roles=["Engineering"]), limit=5)
    assert len(jobs) == 1
    assert jobs[0].company == "Muse Corp"
    assert jobs[0].remote is True


# ---------- Remotive -------------------------------------------------------


@pytest.mark.asyncio
async def test_remotive_fetch_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "jobs": [
            {
                "url": "https://remotive.com/jobs/1",
                "title": "Backend Engineer",
                "company_name": "Rem",
                "candidate_required_location": "USA Only",
                "description": "python golang",
                "publication_date": "2026-01-03",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _install_mock(monkeypatch, ["discovery.remotive", "discovery.http"], handler)
    adapter = RemotiveAdapter()
    jobs = await adapter.fetch(query=SearchQuery(roles=["Backend"]), limit=5)
    assert len(jobs) == 1
    assert jobs[0].remote is True


# ---------- RemoteOK -------------------------------------------------------


@pytest.mark.asyncio
async def test_remoteok_filters_by_role(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"legal": "meta row"},
        {"id": "1", "position": "AI Engineer", "company": "A", "description": "<p>python</p>",
         "url": "https://remoteok.com/1", "location": "Anywhere"},
        {"id": "2", "position": "Sales Rep", "company": "B", "description": "<p>cold calls</p>",
         "url": "https://remoteok.com/2"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _install_mock(monkeypatch, ["discovery.remoteok", "discovery.http"], handler)
    adapter = RemoteOKAdapter()
    jobs = await adapter.fetch(query=SearchQuery(roles=["AI"]), limit=5)
    assert len(jobs) == 1
    assert jobs[0].title.startswith("AI")


# ---------- Failure isolation ---------------------------------------------


@pytest.mark.asyncio
async def test_adapter_returns_empty_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _install_mock(monkeypatch, ["discovery.themuse", "discovery.http"], handler)
    adapter = TheMuseAdapter()
    jobs = await adapter.fetch(query=SearchQuery(roles=["engineering"]), limit=5)
    assert jobs == []
