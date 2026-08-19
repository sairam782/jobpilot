"""Deterministic scoring that ranks discovered jobs against the target config.

The matcher is intentionally boring: three signals combine into one score
in ``[0, 1]``. This keeps behavior explainable and testable without needing
an LLM in the loop for triage.

Signals
-------
- **Title match** — fuzzy ratio of the job title against each configured
  ``target_titles`` entry; the best per-target ratio wins.
- **Location match** — 1.0 if any configured location substring appears
  in the job location string, 0.0 otherwise. Remote preference lifts
  the floor when the posting is remote.
- **Resume overlap** — fraction of shared keyword tokens between the
  resume text and the job title + description.

Exclusions
----------
Any exclusion keyword found in the title or description forces a score of
0 and a "excluded_keyword:<keyword>" reason. This never converts to an
enqueue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from config.settings import settings

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "you",
    "our",
    "your",
    "are",
    "will",
    "have",
    "has",
    "this",
    "that",
    "from",
    "into",
    "team",
    "role",
    "work",
    "working",
    "job",
    "position",
    "we",
    "us",
    "as",
    "of",
    "in",
    "on",
    "to",
    "at",
    "by",
    "an",
    "a",
    "is",
    "be",
    "or",
    "not",
    "but",
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "any",
    "all",
    "can",
    "may",
    "should",
    "must",
    "than",
    "then",
    "also",
    "which",
    "such",
    "so",
    "if",
    "it",
    "its",
    "using",
    "use",
    "used",
}


@dataclass
class ScoredJob:
    """One job with its score breakdown."""

    job: dict[str, Any]
    score: float
    reasons: list[str]


def score_jobs(
    jobs: list[dict[str, Any]],
    *,
    target: dict[str, Any],
    resume_text: str,
) -> list[ScoredJob]:
    """Score a batch of jobs, sorted by score descending."""

    resume_tokens = _tokenize(resume_text)
    scored = [_score_one(job, target=target, resume_tokens=resume_tokens) for job in jobs]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def _score_one(
    job: dict[str, Any],
    *,
    target: dict[str, Any],
    resume_tokens: set[str],
) -> ScoredJob:
    reasons: list[str] = []
    title = str(job.get("title") or "")
    description = str(job.get("description") or "")
    location = str(job.get("location") or "")

    # Exclusions gate everything else.
    for keyword in _as_str_list(target.get("exclusion_keywords")):
        if not keyword:
            continue
        needle = keyword.lower()
        if needle in title.lower() or needle in description.lower():
            return ScoredJob(job=job, score=0.0, reasons=[f"excluded_keyword:{keyword}"])

    title_score = _title_match(title, _as_str_list(target.get("target_titles")))
    reasons.append(f"title_match:{round(title_score, 2)}")

    location_score = _location_match(
        location, _as_str_list(target.get("locations")), target.get("remote_preference")
    )
    reasons.append(f"location_match:{round(location_score, 2)}")

    resume_score = _resume_overlap(resume_tokens, title + " " + description)
    reasons.append(f"resume_overlap:{round(resume_score, 2)}")

    total = (
        settings.score_title_weight * title_score
        + settings.score_location_weight * location_score
        + settings.score_resume_weight * resume_score
    )
    weights = (
        settings.score_title_weight
        + settings.score_location_weight
        + settings.score_resume_weight
    )
    if weights > 0:
        total /= weights

    return ScoredJob(job=job, score=round(float(total), 4), reasons=reasons)


def _title_match(title: str, targets: list[str]) -> float:
    if not title or not targets:
        return 0.0
    best = 0.0
    for t in targets:
        ratio = fuzz.token_set_ratio(title, t) / 100.0
        best = max(best, ratio)
    return best


def _location_match(
    location: str, wanted: list[str], remote_preference: Any
) -> float:
    if not location and not wanted:
        return 0.5
    loc_lower = location.lower()
    is_remote_posting = any(term in loc_lower for term in ("remote", "anywhere", "distributed"))

    if wanted:
        for w in wanted:
            if not w:
                continue
            if w.lower() in loc_lower:
                return 1.0

    pref = str(remote_preference or "").lower()
    if is_remote_posting and pref in {"remote_only", "remote_or_hybrid", "remote"}:
        return 0.9
    if pref == "onsite_only" and is_remote_posting:
        return 0.0
    return 0.3


def _resume_overlap(resume_tokens: set[str], text: str) -> float:
    if not resume_tokens:
        return 0.5  # no resume yet — don't punish jobs for it
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    overlap = resume_tokens & tokens
    return min(1.0, len(overlap) / max(20, len(tokens) // 4))


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = {t for t in _TOKEN_RE.findall(lowered) if len(t) > 2 and t not in _STOPWORDS}
    return tokens


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
