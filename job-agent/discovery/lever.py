"""Lever public job-board adapter.

Lever exposes each customer's postings at::

    https://api.lever.co/v0/postings/<company>?mode=json

Same shape idea as Greenhouse: a public, non-scraping endpoint used by
Lever's own embed.
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from config.settings import settings
from services.logging_config import get_logger

log = get_logger(__name__)


class LeverAdapter:
    """Fetch public postings for one or more Lever-hosted boards."""

    name = "lever"
    _BASE = "https://api.lever.co/v0/postings/{company}"

    def __init__(self, companies: list[str] | None = None) -> None:
        self.companies = companies if companies is not None else settings.lever_company_list

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
                    resp = await client.get(self._BASE.format(company=company), params={"mode": "json"})
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
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


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_html(text: str | None) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text))).strip()


def _normalize(raw: dict[str, Any], company: str) -> dict[str, Any] | None:
    url = raw.get("hostedUrl") or raw.get("applyUrl")
    title = raw.get("text")
    if not url or not title:
        return None

    categories = raw.get("categories") or {}
    location = str(categories.get("location") or "")

    description_parts = [_clean_html(raw.get("descriptionPlain") or raw.get("description"))]
    for section in raw.get("lists") or []:
        description_parts.append(f"{section.get('text') or ''}: {_clean_html(section.get('content'))}")
    description = " ".join(part for part in description_parts if part).strip()
    if len(description) > 4000:
        description = description[:4000] + "…"

    return {
        "url": url,
        "title": str(title),
        "company": company,
        "location": location,
        "description": description,
        "posted_at": raw.get("createdAt"),
        "metadata": {
            "provider": "lever",
            "internal_id": raw.get("id"),
            "team": categories.get("team"),
            "commitment": categories.get("commitment"),
            "workplace_type": categories.get("workplaceType"),
        },
    }
