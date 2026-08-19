"""Aggregator behavior: concurrency, timeout isolation, dedup."""

from __future__ import annotations

import asyncio

import pytest

from discovery import registry
from discovery.aggregator import aggregate_search
from discovery.base import Job, SearchQuery
from discovery.dedup import dedupe


class _FakeAdapter:
    def __init__(self, name: str, jobs: list[Job] | None = None, *, sleep: float = 0.0, raise_exc: Exception | None = None):
        self.name = name
        self._jobs = jobs or []
        self._sleep = sleep
        self._raise = raise_exc

    def enabled(self) -> bool:
        return True

    async def fetch(self, *, query: SearchQuery, limit: int):
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raise:
            raise self._raise
        return self._jobs[:limit]


def _install(monkeypatch: pytest.MonkeyPatch, adapters: list[_FakeAdapter]) -> None:
    monkeypatch.setattr(registry, "enabled_adapters", lambda only=None: adapters)


@pytest.mark.asyncio
async def test_aggregate_merges_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    a = _FakeAdapter("a", [Job(url="https://ex/1", title="AI Engineer", company="Acme")])
    b = _FakeAdapter("b", [Job(url="https://ex/2", title="ML Engineer", company="Bee")])
    _install(monkeypatch, [a, b])

    result = await aggregate_search(SearchQuery(roles=["ai"]), per_source_limit=10)
    assert result.total_before_dedup == 2
    assert len(result.jobs) == 2
    names = {r.name for r in result.per_source}
    assert names == {"a", "b"}
    assert all(r.ok for r in result.per_source)


@pytest.mark.asyncio
async def test_aggregate_isolates_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    good = _FakeAdapter("good", [Job(url="https://ex/1", title="AI", company="Acme")])
    bad = _FakeAdapter("bad", raise_exc=RuntimeError("boom"))
    _install(monkeypatch, [good, bad])

    result = await aggregate_search(SearchQuery(), per_source_limit=10)
    assert len(result.jobs) == 1
    ok_map = {r.name: r for r in result.per_source}
    assert ok_map["bad"].ok is False
    assert "boom" in (ok_map["bad"].error or "")
    assert ok_map["good"].ok is True


@pytest.mark.asyncio
async def test_aggregate_times_out_slow_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    slow = _FakeAdapter("slow", [Job(url="https://ex/1", title="X")], sleep=5.0)
    fast = _FakeAdapter("fast", [Job(url="https://ex/2", title="Y")])
    _install(monkeypatch, [slow, fast])

    result = await aggregate_search(SearchQuery(), per_source_limit=10, adapter_timeout=0.1)
    ok_map = {r.name: r for r in result.per_source}
    assert ok_map["slow"].ok is False
    assert ok_map["slow"].error == "timeout"
    assert ok_map["fast"].ok is True
    assert len(result.jobs) == 1


@pytest.mark.asyncio
async def test_aggregate_dedupes_across_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    j = Job(url="https://boards.greenhouse.io/acme/jobs/123?utm=x",
            title="AI Engineer", company="Acme", source="greenhouse")
    j2 = Job(url="https://boards.greenhouse.io/acme/jobs/123",
             title="AI Engineer", company="Acme", source="adzuna",
             description="Longer description")

    a = _FakeAdapter("a", [j])
    b = _FakeAdapter("b", [j2])
    _install(monkeypatch, [a, b])

    result = await aggregate_search(SearchQuery(), per_source_limit=10)
    assert result.total_before_dedup == 2
    assert len(result.jobs) == 1
    also = result.jobs[0].metadata.get("also_seen_on")
    assert also and any(entry["source"] == "adzuna" for entry in also)
    # Non-empty description backfilled from duplicate.
    assert result.jobs[0].description == "Longer description"


def test_dedupe_fuzzy_company_title() -> None:
    a = Job(url="https://a.com/1", title="Senior AI Engineer", company="Acme")
    b = Job(url="https://b.com/x", title="Senior AI Engineer  ", company="acme")
    out = dedupe([a, b])
    assert len(out) == 1
    also = out[0].metadata.get("also_seen_on")
    assert also and also[0]["url"].startswith("https://b.com")


def test_dedupe_keeps_distinct_companies() -> None:
    a = Job(url="https://a.com/1", title="AI Engineer", company="Acme")
    b = Job(url="https://b.com/1", title="AI Engineer", company="Widget")
    out = dedupe([a, b])
    assert len(out) == 2
