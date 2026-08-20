"""RemoteOK JSON feed adapter.

Endpoint::

    https://remoteok.com/api

Returns a big JSON list of ~1000 recent postings; no auth. First
element is metadata, remaining elements are jobs. Filtered client-side
by role keywords.
"""

from __future__ import annotations

import httpx

from discovery._text import normalize_employment_type, strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class RemoteOKAdapter:
    """RemoteOK global remote-job feed, filtered by role keywords."""

    name = "remoteok"
    _URL = "https://remoteok.com/api"

    def enabled(self) -> bool:
        return True

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        try:
            async with httpx.AsyncClient() as client:
                payload = await get_json(
                    self._URL,
                    headers={"User-Agent": "JobPilot/1.0 (+discovery)"},
                    client=client,
                )
        except HTTPClientError as exc:
            log.warning("remoteok fetch failed", extra={"error": str(exc)})
            return []
        if not isinstance(payload, list):
            return []

        needles = [r.lower() for r in (query.roles or []) if r]
        keyword_needles = [k.lower() for k in query.keywords]
        jobs: list[Job] = []
        for raw in payload:
            if not isinstance(raw, dict) or "id" not in raw:
                continue
            title = raw.get("position") or raw.get("title") or ""
            desc = strip_html(raw.get("description"), max_len=4000)
            haystack = f"{title} {desc}".lower()
            if needles and not any(n in haystack for n in needles):
                continue
            if keyword_needles and not any(k in haystack for k in keyword_needles):
                # keywords are additional evidence; if the caller sets them, require at least one
                continue
            job = _normalize(raw, title)
            if job:
                jobs.append(job)
            if len(jobs) >= limit:
                break
        return jobs


def _normalize(raw: dict, title: str) -> Job | None:
    url = raw.get("url") or raw.get("apply_url")
    if not url or not title:
        return None
    if url.startswith("//"):
        url = "https:" + url
    return Job(
        url=url,
        title=str(title),
        company=raw.get("company"),
        location=raw.get("location") or "Remote",
        description=strip_html(raw.get("description"), max_len=4000),
        posted_at=raw.get("date"),
        source="remoteok",
        remote=True,
        salary_min=_to_float(raw.get("salary_min")),
        salary_max=_to_float(raw.get("salary_max")),
        salary_currency="USD",
        employment_type=normalize_employment_type(raw.get("position") or raw.get("job_type")),
        metadata={
            "provider": "remoteok",
            "tags": raw.get("tags"),
            "epoch": raw.get("epoch"),
        },
    )


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
