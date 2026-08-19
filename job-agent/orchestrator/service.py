"""High-level orchestration bridging discovery, queue, and the LangGraph loop.

Callers get one entry-point per concern:

- ``discover_and_enqueue``: pull jobs from configured discovery adapters,
  score them against the target config, and add the qualified ones to the
  queue.
- ``process_next``: pick the highest-scoring queued job, drive the browser
  agent against it, and record the result. Honors ``dry_run``, approval,
  and daily rate limits.

The LangGraph loop is imported lazily to keep API startup cheap and to
allow tests to substitute a fake runner.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import settings
from discovery import registry as discovery_registry
from orchestrator import queue, rate_limiter
from scoring.matcher import ScoredJob, score_jobs
from services.logging_config import get_logger

log = get_logger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "target_config.json"


def load_target_config(path: Path | None = None) -> dict[str, Any]:
    """Load the operator's target config (titles, locations, exclusions)."""

    config_path = path or DEFAULT_CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


@dataclass
class DiscoveryReport:
    """Summary returned from ``discover_and_enqueue``."""

    scanned: int
    matched: int
    enqueued: int
    top: list[dict[str, Any]]


async def discover_and_enqueue(
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 50,
    min_score: float | None = None,
    target_config: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> DiscoveryReport:
    """Pull jobs from discovery adapters, score, and enqueue those above threshold."""

    target = target_config or load_target_config()
    resume_text = _read_resume_text()
    threshold = min_score if min_score is not None else settings.score_min_accept
    dbp = db_path or settings.database_path
    active_sources = sources or discovery_registry.enabled_sources()

    all_jobs: list[dict[str, Any]] = []
    for source in active_sources:
        adapter = discovery_registry.get_adapter(source)
        try:
            raw = await adapter.fetch(target=target, limit=limit_per_source)
        except Exception as exc:  # noqa: BLE001 - adapter failures shouldn't kill discovery
            log.warning("discovery source failed", extra={"source": source, "error": str(exc)})
            continue
        for job in raw:
            job.setdefault("source", source)
        all_jobs.extend(raw)

    scored: list[ScoredJob] = score_jobs(all_jobs, target=target, resume_text=resume_text)
    accepted = [s for s in scored if s.score >= threshold]

    enqueued = 0
    for s in accepted:
        row = queue.enqueue(
            dbp,
            url=s.job["url"],
            title=s.job.get("title") or "Untitled role",
            company=s.job.get("company"),
            source=s.job.get("source", "unknown"),
            score=s.score,
            reasons=s.reasons,
            metadata=s.job.get("metadata") or {},
        )
        if row.status == queue.QUEUED:
            enqueued += 1

    log.info(
        "discovery complete",
        extra={
            "sources": active_sources,
            "scanned": len(all_jobs),
            "matched": len(accepted),
            "enqueued": enqueued,
        },
    )

    return DiscoveryReport(
        scanned=len(all_jobs),
        matched=len(accepted),
        enqueued=enqueued,
        top=[
            {
                "url": s.job["url"],
                "title": s.job.get("title"),
                "company": s.job.get("company"),
                "score": round(s.score, 3),
                "reasons": s.reasons,
            }
            for s in accepted[:10]
        ],
    )


@dataclass
class RunReport:
    """Summary returned from ``process_next``."""

    job_id: int
    status: str
    message: str
    filled_fields: dict[str, str]
    answer_previews: list[str]
    audit_entries: list[str]


# RunnerFn signature: (job_url, goal, dry_run) -> awaitable of an agent state dict.
RunnerFn = Callable[[str, str, bool], Awaitable[Any]]


async def _default_runner(url: str, goal: str, dry_run: bool) -> Any:
    """Real graph runner (imported lazily; requires Playwright)."""

    from agent.graph import build_graph
    from agent.schemas import AgentState
    from services.browser_controller import BrowserController

    async with BrowserController(headless=settings.browser_headless) as browser:
        await browser.navigate(url)
        graph = build_graph(browser)
        initial = AgentState(goal=goal, target_url=url, metadata={"dry_run": dry_run})
        return await graph.ainvoke(initial)


async def process_next(
    *,
    dry_run: bool | None = None,
    require_approval: bool | None = None,
    runner: RunnerFn | None = None,
    db_path: Path | None = None,
) -> RunReport | None:
    """Pick the next queued job and drive the agent against it.

    Returns None when the queue is empty. Raises when the daily rate limit
    is exhausted (submission-side; queued rows can still accumulate).
    """

    dbp = db_path or settings.database_path
    is_dry = settings.dry_run if dry_run is None else dry_run
    needs_approval = settings.require_approval if require_approval is None else require_approval

    if not is_dry:
        rate_limiter.check(dbp, settings.max_applies_per_day)

    job = queue.pick_next(dbp)
    if not job or job.id is None:
        return None

    log.info(
        "processing job",
        extra={"job_id": job.id, "url": job.url, "score": job.score, "dry_run": is_dry},
    )

    goal = (
        f"Fill the application for '{job.title}' at "
        f"{job.company or 'the employer'} using the candidate's profile."
    )

    run = runner or _default_runner
    try:
        result = await run(job.url, goal, is_dry)
    except Exception as exc:
        log.exception("job runner errored", extra={"job_id": job.id})
        row = queue.mark_failed(dbp, job.id, error=f"{type(exc).__name__}: {exc}")
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Runner raised an exception.",
            filled_fields={},
            answer_previews=[],
            audit_entries=[],
        )

    filled, answers, audit, validation_status, error_text, done = _extract_result(result)

    if error_text and not done:
        row = queue.mark_failed(dbp, job.id, error=error_text)
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Agent reported an execution error.",
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )

    if validation_status == "blocked":
        row = queue.mark_skipped(dbp, job.id, note="agent stopped: blocked")
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Agent stopped: page blocked (CAPTCHA, ambiguity, or recovery cap).",
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )

    # Ready-for-submit path.
    if needs_approval or is_dry:
        row = queue.mark_needs_approval(
            dbp,
            job.id,
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Form ready for human approval.",
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )

    # Fully autonomous submit path — the graph itself is responsible for the
    # final click. We record the submission attempt here so daily caps stay
    # honest.
    row = queue.mark_submitted(dbp, job.id)
    return RunReport(
        job_id=row.id or 0,
        status=row.status,
        message="Submitted (autonomous).",
        filled_fields=filled,
        answer_previews=answers,
        audit_entries=audit,
    )


def _read_resume_text() -> str:
    path = settings.resume_expanded_path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_result(
    result: Any,
) -> tuple[dict[str, str], list[str], list[str], str | None, str | None, bool]:
    """Pull the fields we care about out of an AgentState-like object or dict."""

    def _pluck(name: str, default: Any) -> Any:
        if isinstance(result, dict):
            return result.get(name, default)
        return getattr(result, name, default)

    filled = dict(_pluck("filled_fields", {}) or {})
    answers = list(_pluck("answer_previews", []) or [])
    audit = list(_pluck("audit_entries", []) or [])
    errors = list(_pluck("errors", []) or [])
    done = bool(_pluck("done", False))

    validation = _pluck("validation", None)
    if hasattr(validation, "status"):
        status = validation.status
    elif isinstance(validation, dict):
        status = validation.get("status")
    else:
        status = None

    error_text = errors[-1] if errors else None
    return filled, answers, audit, status, error_text, done
