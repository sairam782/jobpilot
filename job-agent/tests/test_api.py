import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "resume.txt")
    monkeypatch.setattr(settings, "qa_cache_path", tmp_path / "qa.json")
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.log")
    monkeypatch.setattr(settings, "openai_api_key", None)
    (tmp_path / "resume.txt").write_text(
        "AI engineer with python pytorch experience.", encoding="utf-8"
    )

    from services.api import app

    with TestClient(app) as c:
        yield c


def test_health_reports_flags(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "queue_counts" in body
    assert body["dry_run"] is True


def test_dashboard_renders(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "JobPilot" in r.text


def test_enqueue_and_get(client) -> None:
    r = client.post("/queue", json={"url": "https://ex/api-1", "title": "AI Eng"})
    assert r.status_code == 200
    job_id = r.json()["id"]
    r = client.get(f"/queue/{job_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "AI Eng"


def test_invalid_transition_returns_400(client) -> None:
    r = client.post("/queue", json={"url": "https://ex/api-2", "title": "X"})
    job_id = r.json()["id"]
    r = client.post(f"/queue/{job_id}/approve", json={})
    assert r.status_code == 400


def test_resume_qa_offline_fallback_returns_chunk(client) -> None:
    r = client.post("/resume_qa", json={"question": "What is your background?"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "offline_fallback"
    assert "python" in body["answer"].lower()


def test_run_next_empty_queue(client) -> None:
    r = client.post("/runs/next", json={})
    assert r.status_code == 200
    assert r.json()["picked"] is False
