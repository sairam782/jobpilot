"""Deterministic resume-vs-job scoring.

Four signals combine into a single ``[0, 1]`` score:

- **Title match** — fuzzy ratio of the job title vs each configured role.
- **Location match** — configured-location substring hit, remote-preference lift.
- **Skills overlap** — |resume_skills ∩ jd_skills| / min(len(resume_skills), 12)
  so a resume with 30 skills isn't punished for one JD that only names 8.
- **Resume overlap** — token overlap across the full JD text as a
  general-purpose "does this posting look like the candidate's world".

Exclusions gate everything. Seniority mismatch is a soft penalty
(never a zero).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from config.settings import settings
from discovery.base import Job, SearchQuery
from scoring.skills import ExtractedSkills, detect_seniority, extract_skills

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}")
_STOPWORDS = {
    "the", "and", "for", "with", "you", "our", "your", "are", "will", "have",
    "has", "this", "that", "from", "into", "team", "role", "work", "working",
    "job", "position", "who", "what", "when", "where", "why", "how",
    "any", "all", "can", "may", "should", "must", "than", "then", "also",
    "which", "such", "using", "use", "used", "well", "very", "much",
    "would", "could", "about", "here", "there", "their", "them", "they",
    "some", "other", "over", "under", "each",
}
_SENIORITY_RANK = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4}


@dataclass
class ScoreBreakdown:
    """Per-signal detail attached to every scored job."""

    title: float = 0.0
    location: float = 0.0
    skills: float = 0.0
    resume: float = 0.0
    seniority_penalty: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class ScoredJob:
    """A ``Job`` with its combined score and full breakdown."""

    job: Job
    score: float
    breakdown: ScoreBreakdown

    def as_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.as_dict(),
            "score": self.score,
            "breakdown": {
                "title": self.breakdown.title,
                "location": self.breakdown.location,
                "skills": self.breakdown.skills,
                "resume": self.breakdown.resume,
                "seniority_penalty": self.breakdown.seniority_penalty,
                "matched_skills": self.breakdown.matched_skills,
                "missing_skills": self.breakdown.missing_skills[:10],
                "reasons": self.breakdown.reasons,
            },
        }


@dataclass
class ResumeProfile:
    """Cached resume features so every job doesn't re-extract them."""

    text: str
    tokens: set[str]
    skills: ExtractedSkills
    seniority: str | None

    @classmethod
    def from_text(cls, text: str) -> ResumeProfile:
        return cls(
            text=text or "",
            tokens=_tokenize(text or ""),
            skills=extract_skills(text or ""),
            seniority=detect_seniority(text or ""),
        )


def score_jobs(
    jobs: list[Job] | list[dict[str, Any]],
    *,
    query: SearchQuery | None = None,
    target: dict[str, Any] | None = None,
    resume_text: str = "",
    resume_profile: ResumeProfile | None = None,
) -> list[ScoredJob]:
    """Score and sort ``jobs`` (Job objects or dicts) descending."""

    q = _coerce_query(query, target)
    profile = resume_profile or ResumeProfile.from_text(resume_text)
    scored = [_score_one(_coerce_job(j), q, profile) for j in jobs]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def _coerce_query(query: SearchQuery | None, target: dict[str, Any] | None) -> SearchQuery:
    if query is not None:
        return query
    target = target or {}
    return SearchQuery(
        roles=_as_str_list(target.get("target_titles")),
        locations=_as_str_list(target.get("locations")),
        remote_preference=str(target.get("remote_preference") or "remote_or_hybrid"),
        keywords=[],
        exclusion_keywords=_as_str_list(target.get("exclusion_keywords")),
    )


def _coerce_job(j: Job | dict[str, Any]) -> Job:
    if isinstance(j, Job):
        return j
    return Job.from_dict(j)


def _score_one(job: Job, q: SearchQuery, profile: ResumeProfile) -> ScoredJob:
    breakdown = ScoreBreakdown()

    haystack_title = (job.title or "").lower()
    haystack_desc = (job.description or "").lower()

    # Exclusions gate everything else.
    for keyword in q.exclusion_keywords:
        needle = keyword.lower()
        if needle and (needle in haystack_title or needle in haystack_desc):
            breakdown.reasons.append(f"excluded_keyword:{keyword}")
            return ScoredJob(job=job, score=0.0, breakdown=breakdown)

    breakdown.title = _title_match(job.title or "", q.roles)
    breakdown.reasons.append(f"title:{round(breakdown.title, 2)}")

    breakdown.location = _location_match(job.location or "", q.locations, q.remote_preference, job.remote)
    breakdown.reasons.append(f"location:{round(breakdown.location, 2)}")

    jd_skills = extract_skills(f"{job.title} {job.description}")
    breakdown.skills, breakdown.matched_skills, breakdown.missing_skills = _skill_match(
        profile.skills.skills, jd_skills.skills
    )
    breakdown.reasons.append(f"skills:{round(breakdown.skills, 2)}")

    breakdown.resume = _resume_overlap(profile.tokens, job.title + " " + job.description)
    breakdown.reasons.append(f"resume:{round(breakdown.resume, 2)}")

    breakdown.seniority_penalty = _seniority_penalty(profile.seniority, f"{job.title} {job.description}")
    if breakdown.seniority_penalty:
        breakdown.reasons.append(f"seniority_penalty:{round(breakdown.seniority_penalty, 2)}")

    total = (
        settings.score_title_weight * breakdown.title
        + settings.score_location_weight * breakdown.location
        + settings.score_skills_weight * breakdown.skills
        + settings.score_resume_weight * breakdown.resume
    )
    weights = (
        settings.score_title_weight
        + settings.score_location_weight
        + settings.score_skills_weight
        + settings.score_resume_weight
    )
    if weights > 0:
        total /= weights
    total = max(0.0, total - breakdown.seniority_penalty)
    return ScoredJob(job=job, score=round(float(total), 4), breakdown=breakdown)


def _title_match(title: str, targets: list[str]) -> float:
    if not title or not targets:
        return 0.0
    return max(fuzz.token_set_ratio(title, t) / 100.0 for t in targets)


def _location_match(
    location: str,
    wanted: list[str],
    remote_preference: str,
    remote_flag: bool | None,
) -> float:
    if not location and not wanted:
        return 0.5
    loc_lower = location.lower()
    is_remote_posting = (
        (remote_flag is True)
        or any(term in loc_lower for term in ("remote", "anywhere", "distributed"))
    )

    if wanted:
        for w in wanted:
            if not w:
                continue
            if w.lower() in loc_lower:
                return 1.0

    pref = (remote_preference or "").lower()
    if is_remote_posting and pref in {"remote_only", "remote_or_hybrid", "remote"}:
        return 0.9
    if pref == "onsite_only" and is_remote_posting:
        return 0.1
    return 0.35


def _skill_match(
    resume_skills: set[str], jd_skills: set[str]
) -> tuple[float, list[str], list[str]]:
    if not jd_skills:
        return 0.5 if resume_skills else 0.0, [], []
    overlap = resume_skills & jd_skills
    denom = max(6, min(12, len(jd_skills)))
    score = min(1.0, len(overlap) / denom)
    matched = sorted(overlap)
    missing = sorted(jd_skills - resume_skills)
    return score, matched, missing


def _resume_overlap(resume_tokens: set[str], text: str) -> float:
    if not resume_tokens:
        return 0.5
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    overlap = resume_tokens & tokens
    return min(1.0, len(overlap) / max(30, len(tokens) // 4))


def _seniority_penalty(resume_seniority: str | None, jd_text: str) -> float:
    if not resume_seniority:
        return 0.0
    jd_sen = detect_seniority(jd_text)
    if not jd_sen:
        return 0.0
    diff = abs(_SENIORITY_RANK[resume_seniority] - _SENIORITY_RANK[jd_sen])
    if diff == 0:
        return 0.0
    return min(0.25, 0.08 * diff)


def _tokenize(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
