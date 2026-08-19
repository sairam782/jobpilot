"""Lever public job-board adapter.

Endpoint::

    https://api.lever.co/v0/postings/<company>?mode=json

Per-company only — Lever's public API has no cross-company search.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import normalize_employment_type, strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class LeverAdapter:
    """Fetch public postings for one or more Lever-hosted boards."""

    name = "lever"
    _BASE = "https://api.lever.co/v0/postings/{company}"

    def __init__(self, companies: list[str] | None = None) -> None:
        self.companies = companies if companies is not None else settings.lever_company_list

    def enabled(self) -> bool:
        return bool(self.companies)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.companies:
            return []
        jobs: list[Job] = []
        async with httpx.AsyncClient() as client:
            for company in self.companies:
                if len(jobs) >= limit:
                    break
                try:
                    payload = await get_json(
                        self._BASE.format(company=company),
                        params={"mode": "json"},
                        client=client,
                    )
                except HTTPClientError as exc:
                    log.warning(
                        "lever fetch failed",
                        extra={"company": company, "error": str(exc)},
                    )
                    continue
                if not isinstance(payload, list):
                    continue
                for raw in payload:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw, company)
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict, company: str) -> Job | None:
    url = raw.get("hostedUrl") or raw.get("applyUrl")
    title = raw.get("text")
    if not url or not title:
        return None
    categories = raw.get("categories") or {}
    location = str(categories.get("location") or "")
    workplace = str(categories.get("workplaceType") or "").lower()
    description_parts = [strip_html(raw.get("descriptionPlain") or raw.get("description"), max_len=4000)]
    for section in raw.get("lists") or []:
        description_parts.append(
            f"{section.get('text') or ''}: {strip_html(section.get('content'), max_len=800)}"
        )
    description = " ".join(part for part in description_parts if part).strip()
    return Job(
        url=url,
        title=str(title),
        company=company,
        location=location,
        description=description,
        posted_at=raw.get("createdAt"),
        source="lever",
        remote=(workplace == "remote") if workplace else ("remote" in location.lower() or None),
        employment_type=normalize_employment_type(categories.get("commitment")),
        metadata={
            "provider": "lever",
            "internal_id": raw.get("id"),
            "team": categories.get("team"),
            "commitment": categories.get("commitment"),
            "workplace_type": categories.get("workplaceType"),
        },
    )
