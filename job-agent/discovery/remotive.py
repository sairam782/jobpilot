"""Remotive public jobs API adapter.

Endpoint::

    https://remotive.com/api/remote-jobs?search=<role>&limit=<n>

No auth required.
"""

from __future__ import annotations

import httpx

from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class RemotiveAdapter:
    """Search Remotive's remote-jobs feed."""

    name = "remotive"
    _URL = "https://remotive.com/api/remote-jobs"

    def enabled(self) -> bool:
        return True

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        jobs: list[Job] = []
        roles = query.roles or [""]
        per_role = max(1, min(limit, 100))
        async with httpx.AsyncClient() as client:
            for role in roles:
                if len(jobs) >= limit:
                    break
                params: dict[str, str | int] = {"limit": per_role}
                if role:
                    params["search"] = role
                try:
                    payload = await get_json(self._URL, params=params, client=client)
                except HTTPClientError as exc:
                    log.warning("remotive fetch failed", extra={"role": role, "error": str(exc)})
                    continue
                for raw in (payload or {}).get("jobs") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict) -> Job | None:
    url = raw.get("url")
    title = raw.get("title")
    if not url or not title:
        return None
    return Job(
        url=url,
        title=str(title),
        company=raw.get("company_name"),
        location=raw.get("candidate_required_location") or "Remote",
        description=strip_html(raw.get("description"), max_len=4000),
        posted_at=raw.get("publication_date"),
        source="remotive",
        remote=True,
        metadata={
            "provider": "remotive",
            "category": raw.get("category"),
            "job_type": raw.get("job_type"),
        },
    )
