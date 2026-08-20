"""Greenhouse public job-board adapter.

Endpoint::

    https://boards-api.greenhouse.io/v1/boards/<company>/jobs?content=true

Same feed Greenhouse's own embeddable widget uses. Per-company only —
Greenhouse has no cross-company search, so this adapter fans out over
``GREENHOUSE_COMPANIES``.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import normalize_employment_type, strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class GreenhouseAdapter:
    """Fetch public postings for one or more Greenhouse-hosted boards."""

    name = "greenhouse"
    _BASE = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    def __init__(self, companies: list[str] | None = None) -> None:
        self.companies = companies if companies is not None else settings.greenhouse_company_list

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
                        params={"content": "true"},
                        client=client,
                    )
                except HTTPClientError as exc:
                    log.warning(
                        "greenhouse fetch failed",
                        extra={"company": company, "error": str(exc)},
                    )
                    continue
                for raw in payload.get("jobs") or []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw, company)
                    if job:
                        jobs.append(job)
        return jobs


def _infer_gh_employment(raw: dict) -> str | None:
    """Greenhouse doesn't expose employment type as a field; guess from title + metadata custom fields."""

    title = str(raw.get("title") or "").lower()
    guess = normalize_employment_type(title)
    if guess:
        return guess
    for field_group in raw.get("metadata") or []:
        name = str((field_group or {}).get("name") or "").lower()
        if "employment" in name or "commitment" in name or "type" in name:
            value = str((field_group or {}).get("value") or "")
            guess = normalize_employment_type(value)
            if guess:
                return guess
    return None


def _normalize(raw: dict, company: str) -> Job | None:
    url = raw.get("absolute_url")
    title = raw.get("title")
    if not url or not title:
        return None
    loc_obj = raw.get("location") or {}
    location = str(loc_obj.get("name") or "") if isinstance(loc_obj, dict) else ""
    description = strip_html(raw.get("content"), max_len=6000)
    return Job(
        url=url,
        title=str(title),
        company=company,
        location=location,
        description=description,
        posted_at=raw.get("updated_at") or raw.get("first_published"),
        source="greenhouse",
        remote=("remote" in location.lower()) if location else None,
        employment_type=_infer_gh_employment(raw),
        metadata={
            "provider": "greenhouse",
            "internal_id": raw.get("id"),
            "requisition_id": raw.get("requisition_id"),
            "departments": [
                d.get("name") for d in (raw.get("departments") or []) if d.get("name")
            ],
        },
    )
