"""Discovery contract: typed query in, typed job records out.

Every adapter talks to exactly one public source (an ATS provider's
public feed, an aggregator API, a company's careers JSON). Adapters
MUST only touch endpoints their operator is legally allowed to use;
scraping ToS-protected sites (LinkedIn, Indeed) is out of scope.

Adapters are async so the aggregator can fan them out concurrently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class SearchQuery:
    """One search request from the user.

    ``roles`` is the primary axis — the operator picks a small handful
    of target titles (e.g. ["AI Engineer", "ML Engineer"]) and every
    adapter fans out one search per role. Adapters that don't support
    keyword search (per-company ATS feeds like Greenhouse or Lever)
    ignore ``roles`` and rely on the caller having pre-configured a set
    of companies to poll.
    """

    roles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_preference: str = "remote_or_hybrid"
    keywords: list[str] = field(default_factory=list)
    exclusion_keywords: list[str] = field(default_factory=list)
    country: str = "us"
    max_age_days: int | None = None
    # Empty list = no employment-type filter. Recognized values:
    # "full_time", "part_time", "contract", "internship", "temporary".
    employment_types: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Job:
    """A normalized job posting shared across adapters."""

    url: str
    title: str
    company: str | None = None
    location: str = ""
    description: str = ""
    posted_at: str | None = None
    source: str = "unknown"
    remote: bool | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    # Normalized commitment: "full_time" | "part_time" | "contract" |
    # "internship" | "temporary" | None (unknown).
    employment_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @property
    def canonical_url(self) -> str:
        """A URL suitable for cross-adapter dedup.

        See ``discovery.dedup.canonicalize_url`` for the normalization
        rules (host lowercasing, ``www.`` stripping, default-port drop,
        tracking-param strip, slash collapsing, fragment drop).
        """

        # Imported here to avoid a circular import at module load.
        from discovery.dedup import canonicalize_url

        return canonicalize_url(self.url)

    @property
    def dedup_key(self) -> str:
        """Secondary dedup key when URLs disagree (e.g. same job on Greenhouse and Ashby)."""

        return f"{(self.company or '').strip().lower()}::{self.title.strip().lower()[:80]}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        return cls(
            url=data["url"],
            title=data["title"],
            company=data.get("company"),
            location=data.get("location") or "",
            description=data.get("description") or "",
            posted_at=_coerce_posted_at(data.get("posted_at")),
            source=data.get("source") or "unknown",
            remote=data.get("remote"),
            salary_min=data.get("salary_min"),
            salary_max=data.get("salary_max"),
            salary_currency=data.get("salary_currency"),
            employment_type=data.get("employment_type"),
            metadata=dict(data.get("metadata") or {}),
        )


def _coerce_posted_at(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


@runtime_checkable
class DiscoveryAdapter(Protocol):
    """Contract every adapter implements."""

    name: str
    """Registry key (kebab or lowercase snake). Unique across adapters."""

    def enabled(self) -> bool:
        """Return False when the adapter has no way to run (missing key/config)."""

    async def fetch(self, *, query: SearchQuery, limit: int) -> list[Job]:
        """Return normalized Job records for the query, capped at ``limit``."""
