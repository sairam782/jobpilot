from discovery.base import SearchQuery
from scoring.matcher import ResumeProfile, score_jobs

QUERY = SearchQuery(
    roles=["AI Engineer", "Machine Learning Engineer"],
    locations=["Remote", "New York, NY"],
    remote_preference="remote_or_hybrid",
    exclusion_keywords=["unpaid", "commission only"],
)


def test_high_relevance_beats_low_relevance() -> None:
    jobs = [
        {
            "url": "https://ex/a",
            "title": "Senior AI Engineer",
            "location": "Remote",
            "description": "python pytorch transformers rag agents fine-tuning",
        },
        {
            "url": "https://ex/b",
            "title": "Front-end Designer",
            "location": "Berlin",
            "description": "figma css illustration",
        },
    ]
    resume = "Senior AI engineer with python pytorch transformers rag agents fine-tuning experience"
    scored = score_jobs(jobs, query=QUERY, resume_text=resume)
    assert scored[0].job.title.startswith("Senior AI")
    assert scored[0].score > scored[1].score
    assert scored[0].breakdown.matched_skills  # skills were found


def test_exclusion_keyword_zeroes_out_score() -> None:
    jobs = [
        {
            "url": "https://ex/c",
            "title": "AI Engineer (Commission only)",
            "location": "Remote",
            "description": "AI engineer commission only",
        }
    ]
    scored = score_jobs(jobs, query=QUERY, resume_text="ai engineer")
    assert scored[0].score == 0.0
    assert any(r.startswith("excluded_keyword") for r in scored[0].breakdown.reasons)


def test_remote_preference_lifts_remote_posting() -> None:
    jobs = [
        {"url": "https://ex/d", "title": "AI Engineer", "location": "Anywhere", "description": "python"},
    ]
    scored = score_jobs(jobs, query=QUERY, resume_text="ai engineer python")
    assert scored[0].score > 0.4


def test_resume_profile_caches_skill_extraction() -> None:
    profile = ResumeProfile.from_text("Senior ML engineer, PyTorch, RAG, Kubernetes, PostgreSQL")
    assert "pytorch" in profile.skills.skills
    assert "kubernetes" in profile.skills.skills
    assert profile.seniority == "senior"


def test_score_breakdown_reports_matched_and_missing_skills() -> None:
    jobs = [
        {
            "url": "https://ex/e",
            "title": "ML Engineer",
            "location": "Remote",
            "description": "python pytorch kubernetes terraform",
        }
    ]
    scored = score_jobs(jobs, query=QUERY, resume_text="python pytorch")
    b = scored[0].breakdown
    assert "python" in b.matched_skills
    assert "pytorch" in b.matched_skills
    assert set(b.missing_skills) >= {"kubernetes", "terraform"}
