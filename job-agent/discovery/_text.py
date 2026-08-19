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
