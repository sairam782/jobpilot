"""The Muse public jobs API adapter.

Endpoint::

    https://www.themuse.com/api/public/jobs?category=<role>&location=<loc>&page=<n>

No API key required.
"""

from __future__ import annotations

import httpx

from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class TheMuseAdapter:
    """Search The Muse's public job listings."""

    name = "themuse"
    _URL = "https://www.themuse.com/api/public/jobs"

    def enabled(self) -> bool:
        return True

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        jobs: list[Job] = []
        roles = query.roles or [""]
        per_page = 20
        max_pages = max(1, min((limit + per_page - 1) // per_page, 3))

        async with httpx.AsyncClient() as client:
            for role in roles:
                for page in range(1, max_pages + 1):
                    if len(jobs) >= limit:
                        break
                    params: dict[str, str | int] = {
                        "page": page,
                        "descending": "true",
                    }
                    if role:
                        params["category"] = role
                    if query.locations:
                        params["location"] = query.locations[0]
                    try:
                        payload = await get_json(self._URL, params=params, client=client)
                    except HTTPClientError as exc:
                        log.warning("themuse fetch failed", extra={"role": role, "error": str(exc)})
                        break
                    results = (payload or {}).get("results") or []
                    if not results:
                        break
                    for raw in results:
                        if len(jobs) >= limit:
                            break
                        job = _normalize(raw)
                        if job:
                            jobs.append(job)
        return jobs


def _normalize(raw: dict) -> Job | None:
    refs = raw.get("refs") or {}
    url = refs.get("landing_page")
    title = raw.get("name")
    if not url or not title:
        return None
    company = ((raw.get("company") or {}).get("name")) if isinstance(raw.get("company"), dict) else None
    locations = raw.get("locations") or []
    loc_names = [loc.get("name") for loc in locations if loc.get("name")]
    location = "; ".join(loc_names)
    return Job(
        url=url,
        title=str(title),
        company=company,
        location=location,
        description=strip_html(raw.get("contents"), max_len=4000),
        posted_at=raw.get("publication_date"),
        source="themuse",
        remote=any("remote" in n.lower() for n in loc_names),
        metadata={
            "provider": "themuse",
            "levels": [lvl.get("name") for lvl in raw.get("levels") or [] if lvl.get("name")],
            "categories": [cat.get("name") for cat in raw.get("categories") or [] if cat.get("name")],
        },
    )
