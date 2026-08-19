from types import SimpleNamespace

import pytest

from orchestrator import queue
from orchestrator.service import discover_and_enqueue, process_next


class _FakeAdapter:
    name = "fake"

    def __init__(self, jobs):
        self._jobs = jobs

    async def fetch(self, *, target, limit):
        return self._jobs[:limit]


@pytest.mark.asyncio
async def test_discover_and_enqueue_persists_matches(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "resume.txt")
    (tmp_path / "resume.txt").write_text(
        "AI engineer python pytorch transformers rag agents.", encoding="utf-8"
    )

    fake = _FakeAdapter(
        [
            {
                "url": "https://ex/a",
                "title": "AI Engineer",
                "company": "Acme",
                "location": "Remote",
                "description": "python pytorch transformers rag agents",
            },
            {
                "url": "https://ex/b",
                "title": "Sales Rep",
                "company": "Acme",
                "location": "Onsite",
                "description": "cold calls quota commission only",
            },
        ]
    )

    import orchestrator.service as svc

    monkeypatch.setattr(svc.discovery_registry, "enabled_sources", lambda: ["fake"])
    monkeypatch.setattr(svc.discovery_registry, "get_adapter", lambda name: fake)

    target = {
        "target_titles": ["AI Engineer"],
        "locations": ["Remote"],
        "remote_preference": "remote_or_hybrid",
        "exclusion_keywords": ["commission only"],
    }
    report = await discover_and_enqueue(target_config=target, min_score=0.5)

    assert report.matched == 1
    assert report.enqueued == 1
    rows = queue.list_jobs(settings.database_path)
    assert len(rows) == 1
    assert rows[0].url == "https://ex/a"


class _StubResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_process_next_needs_approval_when_dry_run(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")

    queue.enqueue(
        settings.database_path,
        url="https://ex/x",
        title="AI Engineer",
        company="Acme",
        source="test",
        score=0.9,
    )

    async def runner(url, goal, dry_run):
        return _StubResult(
            filled_fields={"#email": "a@b.co"},
            answer_previews=["hi"],
            audit_entries=["step"],
            errors=[],
            done=True,
            validation=SimpleNamespace(status="ready"),
        )

    report = await process_next(dry_run=True, require_approval=True, runner=runner)
    assert report is not None
    assert report.status == queue.NEEDS_APPROVAL
    assert report.filled_fields == {"#email": "a@b.co"}


@pytest.mark.asyncio
async def test_process_next_marks_failed_on_runner_exception(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    queue.enqueue(
        settings.database_path,
        url="https://ex/y",
        title="AI Engineer",
        source="test",
        score=0.9,
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
