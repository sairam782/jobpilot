import httpx
import pytest

from discovery.greenhouse import GreenhouseAdapter
from discovery.greenhouse import _normalize as gh_normalize
from discovery.lever import LeverAdapter
from discovery.lever import _normalize as lever_normalize


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
    assert job["company"] == "acme"
    assert job["title"] == "AI Engineer"
    assert "autonomous" in job["description"]
    assert "<" not in job["description"]
    assert job["metadata"]["departments"] == ["Research"]


def test_lever_normalize_extracts_fields() -> None:
    raw = {
        "id": "abc",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "text": "ML Engineer",
        "categories": {
            "location": "SF",
            "team": "ML Infra",
            "commitment": "Full-time",
            "workplaceType": "hybrid",
        },
        "descriptionPlain": "Work on models.",
        "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
    }
    job = lever_normalize(raw, company="acme")
    assert job is not None
    assert job["url"].endswith("/abc")
    assert "Python" in job["description"]
    assert job["metadata"]["team"] == "ML Infra"


@pytest.mark.asyncio
async def test_greenhouse_fetch_hits_stub_transport(monkeypatch) -> None:
    fake_payload = {
        "jobs": [
            {
                "id": 1,
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "title": "AI Engineer",
                "location": {"name": "Remote"},
                "content": "python agents",
                "updated_at": "2026-01-01T00:00:00Z",
                "departments": [],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "acme" in request.url.path
        assert request.url.params.get("content") == "true"
        return httpx.Response(200, json=fake_payload)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    class StubClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("discovery.greenhouse.httpx.AsyncClient", StubClient)

    adapter = GreenhouseAdapter(companies=["acme"])
    jobs = await adapter.fetch(target={}, limit=10)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "acme"


@pytest.mark.asyncio
async def test_lever_fetch_handles_non_list_gracefully(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "not a list"})

    transport = httpx.MockTransport(handler)

    class StubClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("discovery.lever.httpx.AsyncClient", StubClient)

    adapter = LeverAdapter(companies=["acme"])
    jobs = await adapter.fetch(target={}, limit=10)
    assert jobs == []
