"""Concurrent multi-adapter aggregator.

One entry point — ``aggregate_search`` — fans out a ``SearchQuery``
across every enabled discovery adapter in parallel, applies a
per-adapter timeout, isolates per-adapter failures, deduplicates the
combined pool, and returns everything with a per-source breakdown so
callers can see who contributed what.

The aggregator does NOT score jobs — that's the ``scoring/matcher``
job. Keeps this module deterministic and easy to reason about.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from config.settings import settings
from discovery import registry
from discovery.base import DiscoveryAdapter, Job, SearchQuery
from discovery.dedup import dedupe
from services.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class AdapterReport:
    """Per-source outcome of one aggregate_search invocation."""

    name: str
    ok: bool
    took_ms: float
    returned: int
    error: str | None = None


@dataclass
class AggregateResult:
    """Return value of aggregate_search."""

    jobs: list[Job]
    per_source: list[AdapterReport]
    total_before_dedup: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobs": [j.as_dict() for j in self.jobs],
            "per_source": [ar.__dict__ for ar in self.per_source],
            "total_before_dedup": self.total_before_dedup,
        }


async def aggregate_search(
    query: SearchQuery,
    *,
    sources: list[str] | None = None,
    per_source_limit: int | None = None,
    adapter_timeout: float | None = None,
    max_workers: int | None = None,
) -> AggregateResult:
    """Fan the query out to every enabled adapter concurrently."""

    adapters = registry.enabled_adapters(only=sources)
    if not adapters:
        return AggregateResult(jobs=[], per_source=[], total_before_dedup=0)

    timeout = adapter_timeout if adapter_timeout is not None else settings.discovery_adapter_timeout
    workers = max_workers if max_workers is not None else settings.discovery_max_workers
    limit = per_source_limit if per_source_limit is not None else 50

    sem = asyncio.Semaphore(max(1, workers))

    async def _run_one(adapter: DiscoveryAdapter) -> tuple[AdapterReport, list[Job]]:
        loop = asyncio.get_running_loop()
        start = loop.time()
        try:
            async with sem:
                jobs = await asyncio.wait_for(
                    adapter.fetch(query=query, limit=limit), timeout=timeout
                )
        except TimeoutError:
            elapsed = (loop.time() - start) * 1000
            log.warning("adapter timed out", extra={"adapter": adapter.name, "timeout_s": timeout})
            return AdapterReport(adapter.name, False, elapsed, 0, "timeout"), []
        except Exception as exc:
            elapsed = (loop.time() - start) * 1000
            log.exception("adapter raised", extra={"adapter": adapter.name})
            return AdapterReport(adapter.name, False, elapsed, 0, f"{type(exc).__name__}: {exc}"), []
        elapsed = (loop.time() - start) * 1000
        # Ensure adapter set its own source name.
        for job in jobs:
            if not job.source or job.source == "unknown":
                job.source = adapter.name
        return AdapterReport(adapter.name, True, elapsed, len(jobs)), list(jobs)

    results = await asyncio.gather(*(_run_one(a) for a in adapters))
    per_source: list[AdapterReport] = []
    pool: list[Job] = []
    for report, jobs in results:
        per_source.append(report)
        pool.extend(jobs)

    total_before = len(pool)
    deduped = dedupe(pool)

    log.info(
        "aggregate search complete",
        extra={
            "adapters": [ar.name for ar in per_source],
            "total_before_dedup": total_before,
            "total_after_dedup": len(deduped),
        },
    )

    return AggregateResult(jobs=deduped, per_source=per_source, total_before_dedup=total_before)
