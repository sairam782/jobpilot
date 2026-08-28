"""process_next emits log lines carrying job_id/url/outcome context."""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace

import pytest

from orchestrator import queue
from orchestrator.service import process_next
from services.logging_config import JSONFormatter


def _capture_orchestrator_logs() -> tuple[io.StringIO, logging.Handler]:
    """Attach a JSON stream handler onto the orchestrator.service logger only."""

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(logging.DEBUG)

    orchestrator_log = logging.getLogger("orchestrator.service")
    orchestrator_log.setLevel(logging.DEBUG)
    orchestrator_log.addHandler(handler)
    orchestrator_log.propagate = False
    return buffer, handler


def _detach(handler: logging.Handler) -> None:
    logging.getLogger("orchestrator.service").removeHandler(handler)


def _records(buffer: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    return settings.database_path


@pytest.mark.asyncio
async def test_process_next_binds_job_id_and_url_on_every_line(db) -> None:
    row = queue.enqueue(db, url="https://ex/bind/1", title="AI Engineer",
                        company="Acme", source="test", score=0.7)

    async def runner(url, goal, dry_run):
        return SimpleNamespace(
            filled_fields={"#a": "b", "#c": "d"},
            answer_previews=["preview"],
            audit_entries=["step 1"],
            errors=[], done=True,
            validation=SimpleNamespace(status="ready"),
        )

    buffer, handler = _capture_orchestrator_logs()
    try:
        report = await process_next(dry_run=True, require_approval=True, runner=runner)
    finally:
        _detach(handler)

    assert report is not None and report.status == queue.NEEDS_APPROVAL
    records = _records(buffer)
    assert records, "expected process_next to emit at least one log record"
    for r in records:
        assert r["job_id"] == row.id
        assert r["url"] == "https://ex/bind/1"
        assert r["score"] == 0.7
        assert r["dry_run"] is True

    outcomes = {r.get("outcome") for r in records}
    assert "needs_approval" in outcomes


@pytest.mark.asyncio
async def test_process_next_logs_failure_outcome_when_runner_raises(db) -> None:
    row = queue.enqueue(db, url="https://ex/bind/2", title="AI Engineer",
                        source="test", score=0.5)

    async def bad_runner(*_a, **_k):
        raise RuntimeError("boom")

    buffer, handler = _capture_orchestrator_logs()
    try:
        report = await process_next(dry_run=True, require_approval=True, runner=bad_runner)
    finally:
        _detach(handler)

    assert report is not None and report.status == queue.FAILED
    records = _records(buffer)
    fail_records = [r for r in records if r.get("outcome") == "failed"]
    assert fail_records, "expected an outcome=failed log line"
    assert all(r["job_id"] == row.id for r in fail_records)
    assert all(r["url"] == "https://ex/bind/2" for r in fail_records)
