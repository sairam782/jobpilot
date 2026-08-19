"""SmartRecruiters public search adapter.

SmartRecruiters exposes a cross-company search API::

    https://api.smartrecruiters.com/v1/postings?q=<role>&country=<us|...>&limit=<n>

No auth required for the public postings endpoint.
"""

from __future__ import annotations

import httpx

from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class SmartRecruitersAdapter:
    """Search SmartRecruiters' public postings."""

    name = "smartrecruiters"
    _URL = "https://api.smartrecruiters.com/v1/postings"

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
                params: dict[str, str | int] = {"limit": per_role, "offset": 0}
                if role:
                    params["q"] = role
                if query.country:
                    params["country"] = query.country.lower()
                if query.locations:
                    params["city"] = query.locations[0]
                try:
                    payload = await get_json(self._URL, params=params, client=client)
                except HTTPClientError as exc:
                    log.warning("smartrecruiters fetch failed", extra={"role": role, "error": str(exc)})
                    continue
                for raw in (payload or {}).get("content") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict) -> Job | None:
    ref = raw.get("ref") or ""
    url = raw.get("applyUrl") or raw.get("postingUrl") or f"https://jobs.smartrecruiters.com/{ref}"
    title = raw.get("name")
    if not url or not title:
        return None
    company = ((raw.get("company") or {}).get("name")) if isinstance(raw.get("company"), dict) else None
    location = raw.get("location") or {}
    if isinstance(location, dict):
        parts = [location.get("city"), location.get("region"), location.get("country")]
        loc_str = ", ".join(str(p) for p in parts if p)
        remote = bool(location.get("remote"))
    else:
        loc_str = str(location)
        remote = "remote" in loc_str.lower()
    return Job(
        url=url,
        title=str(title),
        company=company,
        location=loc_str,
        description=strip_html(
            ((raw.get("jobAd") or {}).get("sections") or {}).get("jobDescription", {}).get("text"),
            max_len=4000,
        ),
        posted_at=raw.get("releasedDate") or raw.get("createdOn"),
        source="smartrecruiters",
        remote=remote,
        metadata={
            "provider": "smartrecruiters",
            "industry": (raw.get("industry") or {}).get("label"),
            "function": (raw.get("function") or {}).get("label"),
        },
    )
