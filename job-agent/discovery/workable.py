"""Workable public job-board adapter.

Endpoint (per-company)::

    https://apply.workable.com/api/v1/widget/accounts/<subdomain>?details=true

Workable also publishes an aggregated search at
``https://jobs.workable.com/api/v1/jobs`` but that is undocumented and
frequently changes shape; we stay on the stable per-company feed.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from discovery._text import strip_html
from discovery.base import Job, SearchQuery
from discovery.http import HTTPClientError, get_json
from services.logging_config import get_logger

log = get_logger(__name__)


class WorkableAdapter:
    """Fetch public postings for one or more Workable-hosted boards."""

    name = "workable"
    _URL = "https://apply.workable.com/api/v1/widget/accounts/{subdomain}"

    def __init__(self, subdomains: list[str] | None = None) -> None:
        self.subdomains = subdomains if subdomains is not None else settings.workable_company_list

    def enabled(self) -> bool:
        return bool(self.subdomains)

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        if not self.subdomains:
            return []
        jobs: list[Job] = []
        async with httpx.AsyncClient() as client:
            for sub in self.subdomains:
                if len(jobs) >= limit:
                    break
                try:
                    payload = await get_json(
                        self._URL.format(subdomain=sub),
                        params={"details": "true"},
                        client=client,
                    )
                except HTTPClientError as exc:
                    log.warning("workable fetch failed", extra={"subdomain": sub, "error": str(exc)})
                    continue
                account = ((payload or {}).get("accounts") or [{}])[0] if isinstance(payload, dict) else {}
                for raw in (account.get("jobs") or []) if isinstance(account, dict) else []:
                    if len(jobs) >= limit:
                        break
                    job = _normalize(raw, sub, account.get("name"))
                    if job:
                        jobs.append(job)
        return jobs


def _normalize(raw: dict, sub: str, account_name: str | None) -> Job | None:
    shortcode = raw.get("shortcode")
    url = raw.get("url") or (f"https://apply.workable.com/{sub}/j/{shortcode}" if shortcode else None)
    title = raw.get("title")
    if not url or not title:
        return None
    location = raw.get("location") or {}
    if isinstance(location, dict):
        parts = [location.get("city"), location.get("region"), location.get("country")]
        loc_str = ", ".join(str(p) for p in parts if p)
    else:
        loc_str = str(location)
    workplace = str(raw.get("remote") or raw.get("workplace") or "").lower()
    return Job(
        url=url,
        title=str(title),
        company=account_name or sub,
        location=loc_str,
        description=strip_html(raw.get("description") or raw.get("requirements"), max_len=4000),
        posted_at=raw.get("published_on") or raw.get("created_at"),
        source="workable",
        remote=("remote" in workplace) or ("remote" in loc_str.lower()) or None,
        metadata={
            "provider": "workable",
            "department": raw.get("department"),
            "employment_type": raw.get("employment_type"),
            "shortcode": shortcode,
        },
    )
