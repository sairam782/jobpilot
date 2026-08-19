"""Jooble public search adapter.

Jooble aggregates postings across job boards and exposes a free JSON
search API::

    POST https://jooble.org/api/<api_key>
    Body: {"keywords": "...", "location": "...", "page": 1}

Requires a free API key from jooble.org.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError
from services.logging_config import get_logger

log = get_logger(__name__)


class JoobleAdapter:
    """Search Jooble's aggregated posting index."""

    name = "jooble"
    _URL = "https://jooble.org/api/{key}"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.jooble_api_key

    def enabled(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.enabled():
            return []

        jobs: list[Job] = []
        roles = query.roles or [""]
        async with httpx.AsyncClient(timeout=settings.discovery_http_timeout) as client:
            for role in roles:
                if len(jobs) >= limit:
                    break
                body = {
                    "keywords": role,
                    "location": ", ".join(query.locations) if query.locations else "",
                    "page": 1,
                }
                try:
                    resp = await client.post(self._URL.format(key=self.api_key), json=body)
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("jooble fetch failed", extra={"role": role, "error": str(exc)})
                    continue
                except HTTPClientError as exc:
                    log.warning("jooble fetch failed", extra={"role": role, "error": str(exc)})
                    continue

                for raw in payload.get("jobs") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict) -> Job | None:
    url = raw.get("link")
    title = raw.get("title")
    if not url or not title:
        return None
    return Job(
        url=url,
        title=str(title),
        company=raw.get("company"),
        location=raw.get("location") or "",
        description=strip_html(raw.get("snippet"), max_len=2000),
        posted_at=raw.get("updated"),
        source="jooble",
        remote=None,
        metadata={
            "provider": "jooble",
            "type": raw.get("type"),
            "salary": raw.get("salary"),
        },
    )
