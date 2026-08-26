"""Cross-adapter job deduplication.

Same posting frequently appears on multiple aggregators (RemoteOK
mirrors a Lever job, Adzuna mirrors USAJobs, etc.). Two-pass dedup:

1. Exact canonical URL — the same posting reached via different URL
   surface forms (``www.`` prefix, `:443`, trailing slash, tracking
   query params, uppercased scheme, `//foo/../bar`) still collapses to
   one canonical string. See ``canonicalize_url``.
2. Fuzzy match on ``company::title`` when URLs disagree.

Ordering is stable: the first job wins, later duplicates get merged
into its ``metadata['also_seen_on']`` list so callers can still show
where the job appeared.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from discovery.base import Job

_FUZZY_THRESHOLD = 90  # rapidfuzz token_set_ratio 0..100

# Query-string params to strip: tracking/routing junk that varies across
# adapters but never identifies a different posting. Case-insensitive.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid", "gh_lang",
    "src", "source", "ref", "referer", "referrer",
    "mc_cid", "mc_eid",
    "fbclid", "gclid", "yclid", "msclkid",
    "trk", "trkcampaign",
    "hsCtaTracking",
}
_DEFAULT_PORTS = {"http": "80", "https": "443"}
_SLASH_RUN = re.compile(r"/{2,}")


def canonicalize_url(raw: str) -> str:
    """Return the URL in a shape that dedupes surface-form differences.

    - Lowercase scheme + host.
    - Strip leading ``www.`` from the host.
    - Drop the default port for the scheme (``:80`` on http, ``:443`` on https).
    - Collapse repeated slashes in the path.
    - Trim a trailing slash (except from a bare ``/``).
    - Drop tracking query params; keep the remainder sorted so callers
      that pass the same query in different orders still match.
    - Drop the fragment.

    A URL that fails to parse (empty string, malformed) is returned
    verbatim so the caller can still key on it.
    """

    if not raw:
        return raw
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return raw

    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    host = host.removeprefix("www.")

    port = str(parts.port) if parts.port else ""
    if port and port == _DEFAULT_PORTS.get(scheme):
        port = ""

    netloc = host
    if parts.username:
        auth = parts.username
        if parts.password:
            auth += f":{parts.password}"
        netloc = f"{auth}@{netloc}"
    if port:
        netloc = f"{netloc}:{port}"

    path = _SLASH_RUN.sub("/", parts.path or "")
    if len(path) > 1:
        path = path.rstrip("/")

    query = ""
    if parts.query:
        kept = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        ]
        kept.sort()
        query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))


def dedupe(jobs: list[Job]) -> list[Job]:
    """Return a deduplicated copy of ``jobs`` preserving the first occurrence."""

    result: list[Job] = []
    by_url: dict[str, int] = {}
    by_key: dict[str, list[int]] = {}

    for job in jobs:
        # Pass 1 — exact canonical URL match.
        url_key = canonicalize_url(job.url)
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
