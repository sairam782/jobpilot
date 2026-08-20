"""Cross-adapter job deduplication.

Same posting frequently appears on multiple aggregators (RemoteOK
mirrors a Lever job, Adzuna mirrors USAJobs, etc.). Two-pass dedup:

1. Exact canonical URL (scheme+host+path, no query/fragment).
2. Fuzzy match on ``company::title`` when URLs disagree.

Ordering is stable: the first job wins, later duplicates get merged
into its ``metadata['also_seen_on']`` list so callers can still show
where the job appeared.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from discovery.base import Job

_FUZZY_THRESHOLD = 90  # rapidfuzz token_set_ratio 0..100


def dedupe(jobs: list[Job]) -> list[Job]:
    """Return a deduplicated copy of ``jobs`` preserving the first occurrence."""

    result: list[Job] = []
    by_url: dict[str, int] = {}
    by_key: dict[str, list[int]] = {}

    for job in jobs:
        # Pass 1 — exact URL match.
        url_key = job.canonical_url
        if url_key and url_key in by_url:
            _merge(result[by_url[url_key]], job)
            continue

        # Pass 2 — fuzzy (company, title). Compare only within the same company bucket.
        candidates = by_key.get(job.dedup_key.split("::", 1)[0], [])
        matched_idx = None
        for idx in candidates:
            other = result[idx]
            if _fuzzy_match(job, other):
                matched_idx = idx
                break
        if matched_idx is not None:
            _merge(result[matched_idx], job)
            continue

        # New entry.
        idx = len(result)
        result.append(job)
        if url_key:
            by_url[url_key] = idx
        bucket = job.dedup_key.split("::", 1)[0]
        by_key.setdefault(bucket, []).append(idx)

    return result


def _fuzzy_match(a: Job, b: Job) -> bool:
    company_a = (a.company or "").strip().lower()
    company_b = (b.company or "").strip().lower()
    if company_a and company_b and company_a != company_b:
        return False
    ratio = fuzz.token_set_ratio(a.title or "", b.title or "")
    return ratio >= _FUZZY_THRESHOLD


def _merge(primary: Job, duplicate: Job) -> None:
    """Fold non-empty duplicate fields into primary."""

    also = list(primary.metadata.get("also_seen_on") or [])
    entry = {"source": duplicate.source, "url": duplicate.url}
    if entry not in also:
        also.append(entry)
    primary.metadata["also_seen_on"] = also

    # Fill blanks.
    if not primary.location and duplicate.location:
        primary.location = duplicate.location
    if not primary.description and duplicate.description:
        primary.description = duplicate.description
    if primary.remote is None and duplicate.remote is not None:
        primary.remote = duplicate.remote
    if primary.salary_min is None and duplicate.salary_min is not None:
        primary.salary_min = duplicate.salary_min
    if primary.salary_max is None and duplicate.salary_max is not None:
        primary.salary_max = duplicate.salary_max
    if not primary.salary_currency and duplicate.salary_currency:
        primary.salary_currency = duplicate.salary_currency
