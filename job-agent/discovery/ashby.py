"""Ashby public job-board adapter.

Endpoint::

    https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true

Per-company only. No auth for the public board.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import normalize_employment_type, strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class AshbyAdapter:
    """Fetch public postings for one or more Ashby-hosted boards."""

    name = "ashby"
    _URL = "https://api.ashbyhq.com/posting-api/job-board/{org}"

    def __init__(self, orgs: list[str] | None = None) -> None:
        self.orgs = orgs if orgs is not None else settings.ashby_company_list

    def enabled(self) -> bool:
        return bool(self.orgs)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.orgs:
            return []

        jobs: list[Job] = []
        async with httpx.AsyncClient() as client:
            for org in self.orgs:
                if len(jobs) >= limit:
                    break
                try:
                    payload = await get_json(
                        self._URL.format(org=org),
                        params={"includeCompensation": "true"},
                        client=client,
                    )
                except HTTPClientError as exc:
                    log.warning("ashby fetch failed", extra={"org": org, "error": str(exc)})
                    continue
                for raw in (payload or {}).get("jobs") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw, org)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict, org: str) -> Job | None:
    url = raw.get("jobUrl") or raw.get("applyUrl")
    title = raw.get("title")
    if not url or not title:
        return None
    location = str(raw.get("location") or "")
    workplace = str(raw.get("workplaceType") or "").lower()
    description = strip_html(raw.get("descriptionHtml") or raw.get("descriptionPlain"), max_len=6000)
    comp = raw.get("compensation") or {}
    tier = (comp.get("summaryComponents") or [{}])[0]
    return Job(
        url=url,
        title=str(title),
        company=raw.get("companyName") or org,
        location=location,
        description=description,
        posted_at=raw.get("publishedDate") or raw.get("updatedAt"),
        source="ashby",
        remote=(workplace == "remote") if workplace else None,
        salary_min=tier.get("minValue"),
        salary_max=tier.get("maxValue"),
        salary_currency=tier.get("currencyCode"),
        employment_type=normalize_employment_type(raw.get("employmentType")),
        metadata={
            "provider": "ashby",
            "department": raw.get("department"),
            "team": raw.get("team"),
            "employment_type": raw.get("employmentType"),
        },
    )
