"""Greenhouse public job-board adapter.

Greenhouse publishes each customer's job board at::

    https://boards-api.greenhouse.io/v1/boards/<company>/jobs?content=true

This adapter reads that public endpoint — the same one Greenhouse's own
embeddable widget uses. No auth, no scraping.
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from config.settings import settings
from services.logging_config import get_logger

log = get_logger(__name__)


class GreenhouseAdapter:
    """Fetch public postings for one or more Greenhouse-hosted boards."""

    name = "greenhouse"
    _BASE = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    def __init__(self, companies: list[str] | None = None) -> None:
        self.companies = companies if companies is not None else settings.greenhouse_company_list

    async def fetch(self, *, target: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        if not self.companies:
            return []

        jobs: list[dict[str, Any]] = []
        async with httpx.AsyncClient(
            timeout=settings.discovery_http_timeout,
            headers={"User-Agent": "JobPilot/1.0 (+discovery)"},
        ) as client:
            for company in self.companies:
                if len(jobs) >= limit:
                    break
                try:
                    resp = await client.get(
                        self._BASE.format(company=company),
                        params={"content": "true"},
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning(
                        "greenhouse fetch failed",
                        extra={"company": company, "error": str(exc)},
                    )
                    continue

                for raw in payload.get("jobs", []):
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw, company)
                    if job:
                        jobs.append(job)

        return jobs


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_html(text: str | None) -> str:
    if not text:
        return ""
    without_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", html.unescape(without_tags)).strip()


def _normalize(raw: dict[str, Any], company: str) -> dict[str, Any] | None:
    url = raw.get("absolute_url")
    title = raw.get("title")
    if not url or not title:
        return None

    location = ""
    loc_obj = raw.get("location")
    if isinstance(loc_obj, dict):
        location = str(loc_obj.get("name") or "")

    description = _clean_html(raw.get("content"))
    if len(description) > 4000:
        description = description[:4000] + "…"

    posted_at = raw.get("updated_at") or raw.get("first_published")

    return {
        "url": url,
        "title": str(title),
        "company": company,
        "location": location,
        "description": description,
        "posted_at": posted_at,
        "metadata": {
            "provider": "greenhouse",
            "internal_id": raw.get("id"),
            "requisition_id": raw.get("requisition_id"),
            "departments": [d.get("name") for d in raw.get("departments") or [] if d.get("name")],
        },
    }
