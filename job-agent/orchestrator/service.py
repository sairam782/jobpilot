"""High-level orchestration bridging discovery, queue, and the LangGraph loop."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.settings import settings
from discovery.aggregator import AggregateResult, aggregate_search
from discovery.base import SearchQuery
from orchestrator import queue, rate_limiter
from scoring.matcher import ResumeProfile, ScoredJob, score_jobs
from services.logging_config import get_logger

log = get_logger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "target_config.json"


def load_target_config(path: Path | None = None) -> dict[str, Any]:
    """Load the operator's target config (titles, locations, exclusions)."""

    config_path = path or DEFAULT_CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


def query_from_target(target: dict[str, Any]) -> SearchQuery:
    """Coerce the legacy target_config dict into a typed SearchQuery."""

    return SearchQuery(
        roles=_as_str_list(target.get("target_titles")),
        locations=_as_str_list(target.get("locations")),
        remote_preference=str(target.get("remote_preference") or "remote_or_hybrid"),
        keywords=_as_str_list(target.get("keywords")),
        exclusion_keywords=_as_str_list(target.get("exclusion_keywords")),
        employment_types=_as_str_list(target.get("employment_types")),
    )


# ---------- Search (Part 1) ------------------------------------------------


@dataclass
class SearchReport:
    """Return value of ``search_jobs``: ranked results + per-source telemetry."""

    query: dict[str, Any]
    total_before_dedup: int
    total_after_dedup: int
    per_source: list[dict[str, Any]]
    results: list[dict[str, Any]] = field(default_factory=list)


async def search_jobs(
    *,
    query: SearchQuery,
    sources: list[str] | None = None,
    per_source_limit: int = 50,
    resume_text: str | None = None,
    min_score: float | None = None,
    top_n: int = 100,
) -> SearchReport:
    """Fan out the query across every enabled adapter and return ranked results."""

    aggregate: AggregateResult = await aggregate_search(
        query,
        sources=sources,
        per_source_limit=per_source_limit,
    )
    profile = ResumeProfile.from_text(resume_text if resume_text is not None else _read_resume_text())
    scored: list[ScoredJob] = score_jobs(aggregate.jobs, query=query, resume_profile=profile)
    threshold = min_score if min_score is not None else 0.0
    accepted = [s for s in scored if s.score >= threshold][:top_n]

    return SearchReport(
        query=query.as_dict(),
        total_before_dedup=aggregate.total_before_dedup,
        total_after_dedup=len(aggregate.jobs),
        per_source=[ar.__dict__ for ar in aggregate.per_source],
        results=[s.as_dict() for s in accepted],
    )


# ---------- Discovery (queue-side) -----------------------------------------


@dataclass
class DiscoveryReport:
    """Summary returned from ``discover_and_enqueue``."""

    scanned: int
    matched: int
    enqueued: int
    per_source: list[dict[str, Any]]
    top: list[dict[str, Any]]


async def discover_and_enqueue(
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 50,
    min_score: float | None = None,
    target_config: dict[str, Any] | None = None,
    resume_text: str | None = None,
    query: SearchQuery | None = None,
    db_path: Path | None = None,
) -> DiscoveryReport:
    """Aggregate → score → enqueue matches above threshold."""

    target = target_config if target_config is not None else load_target_config()
    q = query or query_from_target(target)
    threshold = min_score if min_score is not None else settings.score_min_accept
    dbp = db_path or settings.database_path

    report = await search_jobs(
        query=q,
        sources=sources,
        per_source_limit=limit_per_source,
        resume_text=resume_text,
        min_score=threshold,
        top_n=1000,
    )

    enqueued = 0
    for scored in report.results:
        row = queue.enqueue(
            dbp,
            url=scored["job"]["url"],
            title=scored["job"].get("title") or "Untitled role",
            company=scored["job"].get("company"),
            source=scored["job"].get("source", "unknown"),
            score=scored["score"],
            reasons=scored["breakdown"]["reasons"],
            metadata={
                **(scored["job"].get("metadata") or {}),
                "score_breakdown": {
                    k: v for k, v in scored["breakdown"].items() if k != "reasons"
                },
            },
        )
        if row.status == queue.QUEUED:
            enqueued += 1

    log.info(
        "discovery complete",
        extra={
            "sources": sources or "enabled",
            "scanned": report.total_after_dedup,
            "matched": len(report.results),
            "enqueued": enqueued,
        },
    )

    return DiscoveryReport(
        scanned=report.total_after_dedup,
        matched=len(report.results),
        enqueued=enqueued,
        per_source=report.per_source,
        top=[
            {
                "url": s["job"]["url"],
                "title": s["job"].get("title"),
                "company": s["job"].get("company"),
                "score": round(s["score"], 3),
                "source": s["job"].get("source"),
                "matched_skills": s["breakdown"]["matched_skills"][:8],
            }
            for s in report.results[:10]
        ],
    )


# ---------- Run (Part 2) ---------------------------------------------------


@dataclass
class RunReport:
    """Summary returned from ``process_next``."""

    job_id: int
    status: str
    message: str
    filled_fields: dict[str, str]
    answer_previews: list[str]
    audit_entries: list[str]


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
    """Pick the next queued job and drive the agent against it."""

    dbp = db_path or settings.database_path
    is_dry = settings.dry_run if dry_run is None else dry_run
    needs_approval = settings.require_approval if require_approval is None else require_approval

    if not is_dry:
        rate_limiter.check(dbp, settings.max_applies_per_day)

    job = queue.pick_next(dbp)
    if not job or job.id is None:
        return None

    # Stamp job_id / url / score on every log line emitted below so any
    # single record in the JSON log stream can be filtered back to its run.
    job_log = log.bind(job_id=job.id, url=job.url, score=job.score, dry_run=is_dry)
    job_log.info("processing job")

    goal = (
        f"Fill the application for '{job.title}' at "
        f"{job.company or 'the employer'} using the candidate's profile."
    )

    run = runner or _default_runner
    try:
        result = await run(job.url, goal, is_dry)
    except Exception as exc:  # noqa: BLE001 - isolate runner failures per-job
        job_log.exception("job runner errored", extra={"outcome": "failed"})
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
        job_log.warning("agent reported error", extra={"outcome": "failed", "error": error_text[:200]})
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
        job_log.info("agent stopped: blocked", extra={"outcome": "skipped"})
        row = queue.mark_skipped(dbp, job.id, note="agent stopped: blocked")
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Agent stopped: page blocked (CAPTCHA, ambiguity, or recovery cap).",
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )

    if needs_approval or is_dry:
        job_log.info(
            "ready for human approval",
            extra={"outcome": "needs_approval", "filled_count": len(filled)},
        )
        row = queue.mark_needs_approval(
            dbp, job.id,
            filled_fields=filled, answer_previews=answers, audit_entries=audit,
        )
        return RunReport(
            job_id=row.id or 0,
            status=row.status,
            message="Form ready for human approval.",
            filled_fields=filled,
            answer_previews=answers,
            audit_entries=audit,
        )

    job_log.info("submitted", extra={"outcome": "submitted"})
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


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
