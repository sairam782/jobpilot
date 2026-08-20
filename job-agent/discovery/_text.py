"""Text cleaning helpers shared across adapters."""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None, *, max_len: int = 6000) -> str:
    """Return whitespace-normalized plain text from an HTML fragment."""

    if not text:
        return ""
    without_tags = _TAG_RE.sub(" ", text)
    cleaned = _WS_RE.sub(" ", html.unescape(without_tags)).strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def truncate(text: str | None, *, max_len: int = 6000) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def coalesce(*values: str | None) -> str:
    for v in values:
        if v:
            return v
    return ""


# Employment-type normalization ---------------------------------------------

_EMPLOYMENT_ALIASES = {
    "full_time": {
        "full time", "full-time", "fulltime", "ft", "regular", "permanent",
        "employee", "salaried",
    },
    "part_time": {"part time", "part-time", "parttime", "pt"},
    "contract": {
        "contract", "contractor", "contract-to-hire", "c2h", "1099", "consultant",
        "freelance", "freelancer",
    },
    "internship": {"intern", "internship", "co-op", "coop"},
    "temporary": {"temp", "temporary", "seasonal", "fixed-term", "fixed term"},
}

_ALIAS_LOOKUP: dict[str, str] = {
    alias: canonical for canonical, aliases in _EMPLOYMENT_ALIASES.items() for alias in aliases
}


def normalize_employment_type(value: str | None) -> str | None:
    """Return one of full_time/part_time/contract/internship/temporary, or None."""

    if not value:
        return None
    v = value.strip().lower().replace("_", " ")
    if v in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[v]
    # Substring match — provider strings sometimes carry extra qualifiers
    # like "Full-time employee, benefits eligible".
    for alias, canonical in _ALIAS_LOOKUP.items():
        if alias in v:
            return canonical
    return None

