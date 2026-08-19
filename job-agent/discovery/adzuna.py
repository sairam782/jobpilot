"""Adzuna public job search adapter.

Adzuna aggregates postings from thousands of sources and exposes a free
search API::

    https://api.adzuna.com/v1/api/jobs/{country}/search/{page}

Requires ``app_id`` and ``app_key`` from the operator's free Adzuna
developer account.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class AdzunaAdapter:
    """Search Adzuna's aggregated posting index."""

    name = "adzuna"
    _URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def __init__(self, app_id: str | None = None, app_key: str | None = None) -> None:
        self.app_id = app_id or settings.adzuna_app_id
        self.app_key = app_key or settings.adzuna_app_key

    def enabled(self) -> bool:
        return bool(self.app_id and self.app_key)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.enabled():
            return []

        jobs: list[Job] = []
        country = (query.country or "us").lower()
        roles = query.roles or [""]
        per_role = max(1, min(limit, 50))

        async with httpx.AsyncClient() as client:
            for role in roles:
                if len(jobs) >= limit:
                    break
                params: dict[str, str | int] = {
                    "app_id": self.app_id,
                    "app_key": self.app_key,
                    "results_per_page": per_role,
                    "content-type": "application/json",
                }
                if role:
                    params["what"] = role
                if query.locations:
                    params["where"] = query.locations[0]
                if query.max_age_days:
                    params["max_days_old"] = query.max_age_days

                url = self._URL.format(country=country, page=1)
                try:
                    payload = await get_json(url, params=params, client=client)
                except HTTPClientError as exc:
                    log.warning("adzuna fetch failed", extra={"role": role, "error": str(exc)})
                    continue

                for raw in (payload or {}).get("results") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict) -> Job | None:
    url = raw.get("redirect_url") or raw.get("url")
    title = raw.get("title")
    if not url or not title:
        return None
    company = ((raw.get("company") or {}).get("display_name")) if isinstance(raw.get("company"), dict) else raw.get("company")
    location = ((raw.get("location") or {}).get("display_name") or "") if isinstance(raw.get("location"), dict) else ""
    return Job(
        url=url,
        title=str(title),
        company=str(company) if company else None,
        location=location,
        description=strip_html(raw.get("description"), max_len=4000),
        posted_at=raw.get("created"),
        source="adzuna",
        remote=None,
        salary_min=raw.get("salary_min"),
        salary_max=raw.get("salary_max"),
        salary_currency="USD",
        metadata={
            "provider": "adzuna",
            "category": (raw.get("category") or {}).get("label"),
            "contract_type": raw.get("contract_type"),
            "adref": raw.get("adref"),
        },
    )
