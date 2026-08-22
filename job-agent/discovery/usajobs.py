"""USAJobs.gov public search adapter.

USAJobs is the official job board for the US federal government —
tens of thousands of active postings across every agency, all with a
free, ToS-clean JSON API::

    https://data.usajobs.gov/api/search

The API requires two headers: ``User-Agent`` (an email the operator
owns) and ``Authorization-Key`` (a free key from data.usajobs.gov).
Both are set once and reused for every request.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import normalize_employment_type, strip_html, truncate
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class USAJobsAdapter:
    """Search USAJobs.gov federal postings."""

    name = "usajobs"
    _URL = "https://data.usajobs.gov/api/search"

    def __init__(
        self,
        user_agent: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.user_agent = user_agent or settings.usajobs_user_agent
        self.api_key = api_key or settings.usajobs_api_key

    def enabled(self) -> bool:
        return bool(self.user_agent and self.api_key)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.enabled():
            return []

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": self.user_agent,
            "Authorization-Key": self.api_key,
        }
        jobs: list[Job] = []
        roles = query.roles or [""]
        per_role = max(1, min(limit, 100))

        async with httpx.AsyncClient() as client:
            for role in roles:
                if len(jobs) >= limit:
                    break
                params: dict[str, str | int] = {
                    "ResultsPerPage": per_role,
                    "Fields": "Full",
                }
                if role:
                    params["Keyword"] = role
                if query.locations:
                    params["LocationName"] = ";".join(query.locations)
                try:
                    payload = await get_json(
                        self._URL, params=params, headers=headers, client=client
                    )
                except HTTPClientError as exc:
                    log.warning("usajobs fetch failed", extra={"role": role, "error": str(exc)})
                    continue

                search_result = (payload or {}).get("SearchResult") or {}
                for item in search_result.get("SearchResultItems") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(item)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(item: dict) -> Job | None:
    descriptor = (item or {}).get("MatchedObjectDescriptor") or {}
    url = descriptor.get("PositionURI") or _first(descriptor.get("ApplyURI"))
    title = descriptor.get("PositionTitle")
    if not url or not title:
        return None

    org = descriptor.get("OrganizationName")
    locations = descriptor.get("PositionLocation") or []
    loc_names = [
        (loc or {}).get("LocationName")
        for loc in locations
        if isinstance(loc, dict) and loc.get("LocationName")
    ]
    location = "; ".join(loc_names)

    # UserArea can be a dict, missing, or explicitly null; ``.get(k, {})`` on
    # None crashes, so coalesce first.
    user_area = descriptor.get("UserArea") or {}
    user_data = (user_area.get("Details") if isinstance(user_area, dict) else None) or {}
    summary = user_data.get("JobSummary") or ""
    duties = user_data.get("MajorDuties") or ""
    if isinstance(duties, list):
        duties = " ".join(str(p) for p in duties)
    description = truncate(strip_html(f"{summary} {duties}"), max_len=6000)

    remuneration = _first(descriptor.get("PositionRemuneration")) or {}
    salary_min = _to_float(remuneration.get("MinimumRange"))
    salary_max = _to_float(remuneration.get("MaximumRange"))

    return Job(
        url=url,
        title=str(title),
        company=org,
        location=location,
        description=description,
        posted_at=descriptor.get("PublicationStartDate"),
        source="usajobs",
        remote="remote" in location.lower(),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=remuneration.get("RateIntervalCode") and "USD" or None,
        employment_type=_infer_usajobs_employment(descriptor),
        metadata={
            "provider": "usajobs",
            "series": descriptor.get("JobCategory"),
            "grade": descriptor.get("JobGrade"),
            "position_id": descriptor.get("PositionID"),
        },
    )


def _infer_usajobs_employment(descriptor: dict) -> str | None:
    schedules = descriptor.get("PositionSchedule") or []
    for s in schedules:
        canonical = normalize_employment_type(s.get("Name"))
        if canonical:
            return canonical
    return None


def _first(value) -> object:
    """Return the first non-None element of a list, or None for anything else."""

    if isinstance(value, list):
        for item in value:
            if item is not None:
                return item
    return None


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
