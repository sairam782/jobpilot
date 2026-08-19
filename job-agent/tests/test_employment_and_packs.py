"""Employment-type gate + curated-pack expansion."""

from __future__ import annotations

from discovery._text import normalize_employment_type
from discovery.base import Job, SearchQuery
from discovery.companies import GREENHOUSE_PACKS, available_packs, resolve_companies
from scoring.matcher import score_jobs


def test_normalize_employment_type_aliases() -> None:
    assert normalize_employment_type("Full-time") == "full_time"
    assert normalize_employment_type("PART TIME") == "part_time"
    assert normalize_employment_type("Contract") == "contract"
    assert normalize_employment_type("1099") == "contract"
    assert normalize_employment_type("Intern") == "internship"
    assert normalize_employment_type("Full-time employee, benefits eligible") == "full_time"
    assert normalize_employment_type("") is None
    assert normalize_employment_type(None) is None
    assert normalize_employment_type("Volunteer") is None


def test_employment_gate_excludes_off_type() -> None:
    jobs = [
        Job(url="https://ex/ft", title="AI Engineer", description="python", employment_type="full_time"),
        Job(url="https://ex/pt", title="AI Engineer", description="python", employment_type="part_time"),
        Job(url="https://ex/int", title="AI Engineer", description="python", employment_type="internship"),
        Job(url="https://ex/unk", title="AI Engineer", description="python", employment_type=None),  # unknown → passes
    ]
    q = SearchQuery(roles=["AI Engineer"], employment_types=["full_time", "contract"])
    scored = score_jobs(jobs, query=q, resume_text="python")

    by_url = {s.job.url: s for s in scored}
    assert by_url["https://ex/ft"].score > 0
    assert by_url["https://ex/unk"].score > 0  # unknown type is not punished
    assert by_url["https://ex/pt"].score == 0
    assert by_url["https://ex/int"].score == 0
    assert any(r.startswith("excluded_employment_type") for r in by_url["https://ex/pt"].breakdown.reasons)


def test_empty_employment_types_means_no_filter() -> None:
    jobs = [
        Job(url="https://ex/int", title="AI Engineer", employment_type="internship"),
    ]
    q = SearchQuery(roles=["AI Engineer"])  # no employment_types set
    scored = score_jobs(jobs, query=q, resume_text="")
    assert scored[0].score > 0


def test_resolve_companies_dedupes_and_preserves_order() -> None:
    packs = ["ai-labs", "ai-tooling"]
    slugs = resolve_companies("greenhouse", packs)
    assert slugs
    assert len(slugs) == len({s.lower() for s in slugs})
    # Every slug came from one of the two packs.
    combined = set(GREENHOUSE_PACKS["ai-labs"]) | set(GREENHOUSE_PACKS["ai-tooling"])
    assert set(slugs) <= combined


def test_available_packs_lists_known_names() -> None:
    gh = set(available_packs("greenhouse"))
    assert {"ai-labs", "big-tech-ai", "healthcare-ai", "robotics"} <= gh
    assert available_packs("unknown-provider") == []


def test_settings_expands_pack_env(tmp_path, monkeypatch) -> None:
    from config.settings import Settings

    monkeypatch.setenv("GREENHOUSE_COMPANIES", "custom-one, custom-two")
    monkeypatch.setenv("GREENHOUSE_PACKS", "ai-labs, robotics")
    s = Settings()
    slugs = s.greenhouse_company_list
    # Explicit ones come first, packs after, no dupes.
    assert slugs[0] == "custom-one"
    assert slugs[1] == "custom-two"
    assert len(slugs) > 2
    assert len(slugs) == len({x.lower() for x in slugs})
