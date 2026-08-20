"""FastAPI application exposing JobPilot's control surface.

Endpoints
---------
- ``GET  /health``                  liveness + safety-gate snapshot
- ``POST /resume_qa``               resume-grounded Q&A (used by the graph)
- ``POST /discover``                run discovery adapters and enqueue results
- ``GET  /queue``                   list queued/pending rows
- ``GET  /queue/{id}``              one row with filled fields and answers
- ``POST /queue``                   enqueue a direct URL (bypasses discovery)
- ``POST /queue/{id}/approve``      approve a needs_approval row
- ``POST /queue/{id}/reject``       reject a needs_approval row
- ``POST /queue/{id}/skip``         mark queued/needs_approval as skipped
- ``POST /queue/{id}/requeue``      requeue a failed row
- ``POST /runs/next``               process the next queued job end-to-end
- ``GET  /rate-limit``              current daily-cap snapshot
- ``GET  /``                        HTML dashboard
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from agent.router import TaskType, select_model
from config.settings import settings
from db.sqlite_memory import init_db
from discovery import registry as discovery_registry
from discovery.base import SearchQuery
from orchestrator import queue as queue_mod
from orchestrator import rate_limiter
from orchestrator.service import (
    DiscoveryReport,
    RunReport,
    discover_and_enqueue,
    load_target_config,
    process_next,
    query_from_target,
    search_jobs,
)
from services.logging_config import configure_logging, get_logger
from services.resume_processor import chunk_text

RAG_SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "rag.md").read_text(
    encoding="utf-8"
)
DASHBOARD_HTML = (Path(__file__).resolve().parent / "dashboard.html").read_text(
    encoding="utf-8"
)

log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    configure_logging()
    init_db(settings.database_path)
    queue_mod.init_queue(settings.database_path)
    log.info(
        "jobpilot api ready",
        extra={
            "dry_run": settings.dry_run,
            "require_approval": settings.require_approval,
            "max_applies_per_day": settings.max_applies_per_day,
        },
    )
    yield


app = FastAPI(title="JobPilot", version="1.0.0", lifespan=_lifespan)


# ---------- Health & config ------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    dry_run: bool
    require_approval: bool
    stop_on_captcha: bool
    max_applies_per_day: int
    queue_counts: dict[str, int]
    rate_limit_remaining: int


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    counts = queue_mod.count_by_status(settings.database_path)
    rl = rate_limiter.status(settings.database_path, settings.max_applies_per_day)
    return HealthResponse(
        status="ok",
        version=app.version,
        dry_run=settings.dry_run,
        require_approval=settings.require_approval,
        stop_on_captcha=settings.stop_on_captcha,
        max_applies_per_day=settings.max_applies_per_day,
        queue_counts=counts,
        rate_limit_remaining=rl.remaining,
    )


# ---------- Resume Q&A -----------------------------------------------------


class ResumeQARequest(BaseModel):
    """Request body for the /resume_qa endpoint."""

    question: str


class ResumeQAResponse(BaseModel):
    """Response body for generated resume answers."""

    answer: str
    source: str
    source_chunks: list[str] = Field(default_factory=list)


@app.post("/resume_qa", response_model=ResumeQAResponse)
async def resume_qa(request: ResumeQARequest) -> ResumeQAResponse:
    """Answer a custom question using cached Q&A first, then resume text."""

    cached = _lookup_cache(request.question)
    if cached:
        return ResumeQAResponse(answer=cached, source="qa_cache", source_chunks=[])

    resume_text = settings.resume_expanded_path.read_text(encoding="utf-8")
    chunks = chunk_text(resume_text)
    source_chunks = _select_source_chunks(request.question, chunks)

    if not settings.openai_api_key:
        # Offline fallback: return the best-matching resume chunk as the answer
        # rather than making a network call with a dummy key.
        answer = source_chunks[0] if source_chunks else ""
        return ResumeQAResponse(answer=answer, source="offline_fallback", source_chunks=source_chunks)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=select_model(TaskType.RAG, pydantic_ai=False),
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Resume context chunks:\n"
                    f"{json.dumps(source_chunks, ensure_ascii=True)}\n\n"
                    f"Question:\n{request.question}"
                ),
            },
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    _append_cache(request.question, answer)
    return ResumeQAResponse(
        answer=answer, source=settings.embedding_provider, source_chunks=source_chunks
    )


# ---------- Search + discovery --------------------------------------------


class SearchRequest(BaseModel):
    roles: list[str] = Field(default_factory=list, description="Target job titles.")
    locations: list[str] = Field(default_factory=list)
    remote_preference: str = "remote_or_hybrid"
    keywords: list[str] = Field(default_factory=list)
    exclusion_keywords: list[str] = Field(default_factory=list)
    country: str = "us"
    max_age_days: int | None = Field(default=None, ge=1, le=180)
    employment_types: list[str] = Field(
        default_factory=list,
        description="Any of full_time/part_time/contract/internship/temporary. Empty = all.",
    )

    sources: list[str] | None = Field(default=None, description="Restrict adapters; default is all enabled.")
    per_source_limit: int = Field(default=50, ge=1, le=200)
    min_score: float | None = Field(default=None, ge=0, le=1)
    top_n: int = Field(default=100, ge=1, le=500)
    resume_text: str | None = Field(default=None, description="Inline resume; falls back to RESUME_EXPANDED_PATH.")


class DiscoveryRequest(SearchRequest):
    """Same as SearchRequest but persists matches to the queue."""


def _query_from(request: SearchRequest, fallback_target: dict[str, Any]) -> SearchQuery:
    """Build a SearchQuery from the request, falling back to target_config for empties."""

    fallback = query_from_target(fallback_target)
    return SearchQuery(
        roles=request.roles or fallback.roles,
        locations=request.locations or fallback.locations,
        remote_preference=request.remote_preference or fallback.remote_preference,
        keywords=request.keywords or fallback.keywords,
        exclusion_keywords=request.exclusion_keywords or fallback.exclusion_keywords,
        country=request.country,
        max_age_days=request.max_age_days,
        employment_types=request.employment_types or fallback.employment_types,
    )


@app.get("/sources")
async def list_sources() -> dict[str, Any]:
    """Which adapters exist and which are configured this run."""

    return {
        "registered": discovery_registry.registered_sources(),
        "enabled": discovery_registry.enabled_sources(),
    }


@app.post("/search")
async def search(request: SearchRequest) -> dict[str, Any]:
    """Fan out the search across every enabled adapter and return ranked results."""

    target = load_target_config()
    q = _query_from(request, target)
    report = await search_jobs(
        query=q,
        sources=request.sources,
        per_source_limit=request.per_source_limit,
        resume_text=request.resume_text,
        min_score=request.min_score,
        top_n=request.top_n,
    )
    return {
        "query": report.query,
        "total_before_dedup": report.total_before_dedup,
        "total_after_dedup": report.total_after_dedup,
        "per_source": report.per_source,
        "results": report.results,
    }


@app.post("/discover", response_model=dict)
async def discover(request: DiscoveryRequest) -> dict[str, Any]:
    """Run discovery adapters and enqueue matches above the score threshold."""

    target = load_target_config()
    q = _query_from(request, target)
    report: DiscoveryReport = await discover_and_enqueue(
        query=q,
        sources=request.sources,
        limit_per_source=request.per_source_limit,
        min_score=request.min_score,
        resume_text=request.resume_text,
    )
    return {
        "scanned": report.scanned,
        "matched": report.matched,
        "enqueued": report.enqueued,
        "per_source": report.per_source,
        "top": report.top,
    }


# ---------- Queue endpoints ------------------------------------------------


class EnqueueRequest(BaseModel):
    url: str
    title: str = "Manual URL"
    company: str | None = None
    source: str = "manual"
    score: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalNote(BaseModel):
    note: str | None = None


@app.get("/queue")
async def list_queue(
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    status_filter = [s.strip() for s in status.split(",")] if status else None
    rows = queue_mod.list_jobs(settings.database_path, status=status_filter, limit=limit)
    return {
        "counts": queue_mod.count_by_status(settings.database_path),
        "jobs": [row.to_public() for row in rows],
    }


@app.get("/queue/{job_id}")
async def get_queue_item(job_id: int) -> dict[str, Any]:
    try:
        row = queue_mod.get(settings.database_path, job_id)
    except queue_mod.QueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return row.to_public()


@app.post("/queue")
async def enqueue_manual(request: EnqueueRequest) -> dict[str, Any]:
    row = queue_mod.enqueue(
        settings.database_path,
        url=request.url,
        title=request.title,
        company=request.company,
        source=request.source,
        score=request.score,
        metadata=request.metadata,
    )
    return row.to_public()


def _transition(job_id: int, fn, **kwargs) -> dict[str, Any]:
    try:
        row = fn(settings.database_path, job_id, **kwargs)
    except queue_mod.QueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row.to_public()


@app.post("/queue/{job_id}/approve")
async def approve_item(job_id: int, body: ApprovalNote | None = None) -> dict[str, Any]:
    return _transition(job_id, queue_mod.approve, note=(body.note if body else None))


@app.post("/queue/{job_id}/reject")
async def reject_item(job_id: int, body: ApprovalNote | None = None) -> dict[str, Any]:
    return _transition(job_id, queue_mod.reject, note=(body.note if body else None))


@app.post("/queue/{job_id}/skip")
async def skip_item(job_id: int, body: ApprovalNote | None = None) -> dict[str, Any]:
    return _transition(job_id, queue_mod.mark_skipped, note=(body.note if body else None))


@app.post("/queue/{job_id}/requeue")
async def requeue_item(job_id: int) -> dict[str, Any]:
    return _transition(job_id, queue_mod.requeue)


# ---------- Runs -----------------------------------------------------------


class RunRequest(BaseModel):
    dry_run: bool | None = None
    require_approval: bool | None = None


@app.post("/runs/next")
async def run_next(body: RunRequest | None = None) -> dict[str, Any]:
    """Pick the next queued job and drive the agent against it."""

    payload = body or RunRequest()
    try:
        report: RunReport | None = await process_next(
            dry_run=payload.dry_run,
            require_approval=payload.require_approval,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if report is None:
        return {"picked": False, "reason": "queue empty"}
    return {
        "picked": True,
        "job_id": report.job_id,
        "status": report.status,
        "message": report.message,
        "filled_fields": report.filled_fields,
        "answer_previews": report.answer_previews,
        "audit_entries": report.audit_entries,
    }


@app.get("/rate-limit")
async def rate_limit() -> dict[str, Any]:
    snap = rate_limiter.status(settings.database_path, settings.max_applies_per_day)
    return {
        "submitted_24h": snap.submitted_24h,
        "max_per_day": snap.max_per_day,
        "remaining": snap.remaining,
        "reset_at": snap.reset_at.isoformat(),
        "allowed": snap.allowed,
    }


@app.get("/target-config")
async def target_config() -> dict[str, Any]:
    return load_target_config()


# ---------- Dashboard ------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


# ---------- Helpers --------------------------------------------------------


def _lookup_cache(question: str) -> str | None:
    if not settings.qa_cache_path.exists():
        return None
    cache = json.loads(settings.qa_cache_path.read_text(encoding="utf-8") or "[]")
    for item in cache:
        if fuzz.token_set_ratio(question, item.get("question", "")) >= 92:
            return str(item.get("answer", ""))
    return None


def _append_cache(question: str, answer: str) -> None:
    settings.qa_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = []
    if settings.qa_cache_path.exists():
        cache = json.loads(settings.qa_cache_path.read_text(encoding="utf-8") or "[]")
    cache.append({"question": question, "answer": answer})
    settings.qa_cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _select_source_chunks(question: str, chunks: list[str], limit: int = 4) -> list[str]:
    scored = sorted(
        ((fuzz.token_set_ratio(question, chunk), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    return [chunk for _score, chunk in scored[:limit]]
