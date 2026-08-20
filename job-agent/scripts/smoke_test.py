"""End-to-end smoke test for JobPilot without hitting real job boards."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


async def run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-smoke-"))
    (tmp / "resume.txt").write_text(
        "AI engineer with python pytorch rag agents experience.", encoding="utf-8"
    )

    from config.settings import settings

    settings.database_path = tmp / "db.sqlite3"
    settings.resume_expanded_path = tmp / "resume.txt"
    settings.qa_cache_path = tmp / "qa.json"
    settings.audit_log_path = tmp / "audit.log"
    settings.openai_api_key = None

    from discovery import registry
    from discovery.base import Job, SearchQuery
    from orchestrator import queue
    from orchestrator import service as svc

    class Stub:
        name = "stub"

        def enabled(self):
            return True

        async def fetch(self, *, query, limit):
            return [
                Job(url="https://ex/smoke", title="AI Engineer", company="SmokeCo",
                    location="Remote", description="python rag agents pytorch")
            ][:limit]

    registry.enabled_adapters = lambda only=None: [Stub()]  # type: ignore[assignment]

    q = SearchQuery(
        roles=["AI Engineer"], locations=["Remote"],
        remote_preference="remote_or_hybrid",
    )
    report = await svc.discover_and_enqueue(query=q, min_score=0.3)
    assert report.enqueued == 1, f"expected 1 enqueued, got {report.enqueued}"

    async def fake_runner(url, goal, dry_run):
        return SimpleNamespace(
            filled_fields={"#email": "a@b.co"},
            answer_previews=["preview"],
            audit_entries=["step 1"],
            errors=[], done=True,
            validation=SimpleNamespace(status="ready"),
        )

    run_report = await svc.process_next(dry_run=True, require_approval=True, runner=fake_runner)
    assert run_report is not None
    assert run_report.status == queue.NEEDS_APPROVAL

    from services.api import app

    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        got = client.get(f"/queue/{run_report.job_id}")
        assert got.json()["status"] == "needs_approval"
        approved = client.post(f"/queue/{run_report.job_id}/approve", json={"note": "smoke"})
        assert approved.status_code == 200

    counts = queue.count_by_status(settings.database_path)
    print("smoke ok · counts:", counts)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        print(f"smoke FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
