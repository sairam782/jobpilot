"""GET /audit/recent surfaces the sqlite audit rows over HTTP."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from db.sqlite_memory import log_iteration


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "resume.txt")
    monkeypatch.setattr(settings, "qa_cache_path", tmp_path / "qa.json")
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.log")
    (tmp_path / "resume.txt").write_text("stub", encoding="utf-8")

    from services.api import app
    with TestClient(app) as c:
        yield c, settings


def _seed(settings, url: str, i: int) -> None:
    log_iteration(
        db_path=settings.database_path,
        url=url,
        action=f'{{"step":{i}}}',
        llm_prompt="p",
        llm_output="o",
        result="r",
    )
    time.sleep(0.001)


def test_audit_recent_returns_rows_newest_first(client) -> None:
    c, settings = client
    for i, url in enumerate(["https://a", "https://b", "https://a"]):
        _seed(settings, url, i)

    r = c.get("/audit/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    # newest first: last insert was https://a with step=2
    assert body["rows"][0]["url"] == "https://a"
    assert body["rows"][0]["action"] == '{"step":2}'


def test_audit_recent_filters_by_url_and_limits(client) -> None:
    c, settings = client
    for i in range(4):
        _seed(settings, "https://target" if i % 2 == 0 else "https://other", i)

    r = c.get("/audit/recent?url=https://target&limit=1")
    assert r.status_code == 200
    body = r.json()
    assert body["filter_url"] == "https://target"
    assert body["count"] == 1
    assert body["rows"][0]["url"] == "https://target"


def test_audit_recent_empty_when_no_rows(client) -> None:
    c, _ = client
    r = c.get("/audit/recent")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "filter_url": None, "rows": []}


def test_audit_recent_clamps_absurd_limits(client) -> None:
    c, settings = client
    _seed(settings, "https://x", 0)
    # 0 clamps up, 10_000 clamps down — both should return 1 row here.
    for bad in (0, 10_000):
        r = c.get(f"/audit/recent?limit={bad}")
        assert r.status_code == 200
        assert r.json()["count"] == 1
