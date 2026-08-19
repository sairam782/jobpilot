"""Base contract for discovery adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DiscoveryAdapter(Protocol):
    """Adapter contract: fetch public job postings for a target profile.

    Each adapter is responsible for talking to exactly one source (an ATS
    provider's public feed, a company's careers RSS, etc.). Adapters MUST
    only touch endpoints their operator has legal permission to use, and
    MUST NOT attempt authentication or scraping tricks — that is the
    browser agent's job on a per-application basis.

    Returned job dicts have the shape::

        {
          "url": "https://...",
          "title": "AI Engineer",
          "company": "Acme",
          "location": "Remote (US)",
          "description": "...",         # plain text, may be truncated
          "posted_at": "2026-01-15",    # ISO date, best effort
          "metadata": {...},            # source-specific extras
        }
    """

    name: str

    async def fetch(self, *, target: dict[str, Any], limit: int) -> list[dict[str, Any]]: ...
