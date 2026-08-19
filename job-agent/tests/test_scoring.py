from scoring.matcher import score_jobs

TARGET = {
    "target_titles": ["AI Engineer", "Machine Learning Engineer"],
    "locations": ["Remote", "New York, NY"],
    "remote_preference": "remote_or_hybrid",
    "exclusion_keywords": ["unpaid", "commission only"],
}


def test_high_relevance_beats_low_relevance() -> None:
    jobs = [
        {
            "url": "https://ex/a",
            "title": "Senior AI Engineer",
            "location": "Remote",
            "description": "python pytorch transformers rag agents",
        },
        {
            "url": "https://ex/b",
            "title": "Front-end Designer",
            "location": "Berlin",
            "description": "figma css illustration",
        },
    ]
    resume = "AI engineer with python pytorch transformers rag agents nlp experience"
    scored = score_jobs(jobs, target=TARGET, resume_text=resume)
    assert scored[0].job["title"].startswith("Senior AI")
    assert scored[0].score > scored[1].score


def test_exclusion_keyword_zeroes_out_score() -> None:
    jobs = [
        {
            "url": "https://ex/c",
            "title": "AI Engineer (Commission only)",
            "location": "Remote",
            "description": "AI engineer commission only",
        }
    ]
    scored = score_jobs(jobs, target=TARGET, resume_text="ai engineer")
    assert scored[0].score == 0.0
    assert any(r.startswith("excluded_keyword") for r in scored[0].reasons)


def test_remote_preference_lifts_remote_posting() -> None:
    jobs = [
        {"url": "https://ex/d", "title": "AI Engineer", "location": "Anywhere", "description": ""},
    ]
    scored = score_jobs(jobs, target=TARGET, resume_text="ai engineer")
    assert scored[0].score > 0.4
