from types import SimpleNamespace

import pytest

from discovery.base import Job, SearchQuery
from orchestrator import queue
from orchestrator.service import discover_and_enqueue, process_next, search_jobs


class _FakeAdapter:
    def __init__(self, jobs):
        self.name = "fake"
        self._jobs = jobs

    def enabled(self):
        return True

    async def fetch(self, *, query, limit):
        return self._jobs[:limit]


@pytest.mark.asyncio
async def test_search_returns_scored_results(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "r.txt")
    (tmp_path / "r.txt").write_text(
        "AI engineer python pytorch transformers rag agents.", encoding="utf-8"
    )

    fake = _FakeAdapter(
        [
            Job(url="https://ex/a", title="AI Engineer", company="Acme", location="Remote",
                description="python pytorch transformers rag agents"),
            Job(url="https://ex/b", title="Sales Rep", company="Acme", location="Onsite",
                description="commission only cold calls"),
        ]
    )

    import discovery.registry as reg
    monkeypatch.setattr(reg, "enabled_adapters", lambda only=None: [fake])

    q = SearchQuery(
        roles=["AI Engineer"], locations=["Remote"],
        remote_preference="remote_or_hybrid", exclusion_keywords=["commission only"],
    )
    report = await search_jobs(query=q, per_source_limit=10, min_score=0.4)
    assert report.total_after_dedup == 2
    assert len(report.results) == 1
    top = report.results[0]
    assert top["job"]["url"] == "https://ex/a"
    assert top["breakdown"]["matched_skills"]


@pytest.mark.asyncio
async def test_discover_and_enqueue_persists_matches(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "r.txt")
    (tmp_path / "r.txt").write_text(
        "AI engineer python pytorch rag agents.", encoding="utf-8"
    )

    fake = _FakeAdapter(
        [
            Job(url="https://ex/a", title="AI Engineer", company="Acme", location="Remote",
                description="python pytorch rag agents"),
            Job(url="https://ex/b", title="Sales Rep", company="Acme", location="Onsite",
                description="commission only"),
        ]
    )
    import discovery.registry as reg
    monkeypatch.setattr(reg, "enabled_adapters", lambda only=None: [fake])

    q = SearchQuery(
        roles=["AI Engineer"], locations=["Remote"],
        remote_preference="remote_or_hybrid", exclusion_keywords=["commission only"],
    )
    report = await discover_and_enqueue(query=q, min_score=0.4)
    assert report.matched == 1
    assert report.enqueued == 1
    rows = queue.list_jobs(settings.database_path)
    assert len(rows) == 1
    assert rows[0].url == "https://ex/a"


@pytest.mark.asyncio
async def test_process_next_needs_approval_when_dry_run(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")

    queue.enqueue(
        settings.database_path,
        url="https://ex/x", title="AI Engineer", company="Acme", source="test", score=0.9,
    )

    async def runner(url, goal, dry_run):
        return SimpleNamespace(
            filled_fields={"#email": "a@b.co"},
            answer_previews=["hi"],
            audit_entries=["step"],
            errors=[], done=True,
            validation=SimpleNamespace(status="ready"),
        )

    report = await process_next(dry_run=True, require_approval=True, runner=runner)
    assert report is not None
    assert report.status == queue.NEEDS_APPROVAL


@pytest.mark.asyncio
async def test_process_next_marks_failed_on_runner_exception(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    queue.enqueue(
        settings.database_path, url="https://ex/y", title="X", source="test", score=0.9,
    )

    async def bad_runner(*_a, **_k):
        raise RuntimeError("browser blew up")

    report = await process_next(dry_run=True, require_approval=True, runner=bad_runner)
    assert report is not None
    assert report.status == queue.FAILED


@pytest.mark.asyncio
async def test_process_next_returns_none_when_empty(tmp_path, monkeypatch) -> None:
    from config.settings import settings
    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    result = await process_next(runner=lambda *_a, **_k: None)
    assert result is None
