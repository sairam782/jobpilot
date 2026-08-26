"""URL canonicalization catches more cross-source duplicates."""

from __future__ import annotations

from discovery.base import Job
from discovery.dedup import canonicalize_url, dedupe

# ---- canonicalize_url unit tests -----------------------------------------


def test_strips_www_prefix() -> None:
    a = canonicalize_url("https://www.themuse.com/jobs/42")
    b = canonicalize_url("https://themuse.com/jobs/42")
    assert a == b == "https://themuse.com/jobs/42"


def test_strips_default_ports() -> None:
    assert canonicalize_url("https://x.com:443/y") == "https://x.com/y"
    assert canonicalize_url("http://x.com:80/y") == "http://x.com/y"
    # Non-default ports stay put.
    assert canonicalize_url("https://x.com:8443/y") == "https://x.com:8443/y"


def test_lowercases_scheme_and_host_but_keeps_path_case() -> None:
    url = canonicalize_url("HTTPS://Boards.Greenhouse.io/Acme/Jobs/42")
    assert url == "https://boards.greenhouse.io/Acme/Jobs/42"


def test_collapses_repeated_slashes_and_trims_trailing() -> None:
    assert canonicalize_url("https://x.com//a///b/") == "https://x.com/a/b"


def test_drops_fragment_and_common_tracking_params() -> None:
    raw = "https://x.com/j/1?utm_source=twitter&gh_src=widget&role=eng#apply"
    assert canonicalize_url(raw) == "https://x.com/j/1?role=eng"


def test_sorts_remaining_query_params_for_stable_key() -> None:
    a = canonicalize_url("https://x.com/j?b=2&a=1")
    b = canonicalize_url("https://x.com/j?a=1&b=2")
    assert a == b == "https://x.com/j?a=1&b=2"


def test_returns_empty_for_empty_and_verbatim_for_garbage() -> None:
    assert canonicalize_url("") == ""
    # Not a URL — passed through untouched (still keyable).
    assert canonicalize_url("not-a-url") == canonicalize_url("not-a-url")


# ---- dedupe integration ---------------------------------------------------


def test_dedupe_folds_www_and_tracking_duplicates() -> None:
    jobs = [
        Job(url="https://boards.greenhouse.io/openai/jobs/1?utm_source=x",
            title="AI Engineer", company="OpenAI", source="greenhouse"),
        Job(url="https://www.boards.greenhouse.io/openai/jobs/1?gh_src=y",
            title="AI Engineer", company="OpenAI", source="adzuna"),
        Job(url="HTTPS://Boards.Greenhouse.io:443/openai/jobs/1/",
            title="AI Engineer", company="OpenAI", source="jooble"),
    ]
    out = dedupe(jobs)
    assert len(out) == 1
    also = out[0].metadata.get("also_seen_on")
    sources = {entry["source"] for entry in also or []}
    assert sources == {"adzuna", "jooble"}


def test_dedupe_still_keeps_distinct_postings() -> None:
    jobs = [
        Job(url="https://x.com/a/1", title="AI Engineer", company="Acme", source="greenhouse"),
        Job(url="https://x.com/a/2", title="Data Scientist", company="Acme", source="greenhouse"),
    ]
    assert len(dedupe(jobs)) == 2
