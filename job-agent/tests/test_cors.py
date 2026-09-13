"""CORS middleware wiring: silent by default, permissive when configured."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def _boot_app(monkeypatch, tmp_path, allow_origins: str) -> TestClient:
    """Reload services.api with the given CORS_ALLOW_ORIGINS baked in."""

    from config.settings import settings

    monkeypatch.setattr(settings, "cors_allow_origins", allow_origins)
    monkeypatch.setattr(settings, "database_path", tmp_path / "db.sqlite3")
    monkeypatch.setattr(settings, "resume_expanded_path", tmp_path / "r.txt")
    monkeypatch.setattr(settings, "qa_cache_path", tmp_path / "qa.json")
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.log")
    (tmp_path / "r.txt").write_text("stub", encoding="utf-8")

    # Re-import so the module-level ``app = FastAPI(...)`` + middleware
    # add_middleware() call sees the new settings value.
    import services.api as api_mod
    importlib.reload(api_mod)
    return TestClient(api_mod.app)


def test_no_cors_header_when_origins_unset(monkeypatch, tmp_path) -> None:
    client = _boot_app(monkeypatch, tmp_path, "")
    r = client.get("/health", headers={"Origin": "https://web.example"})
    assert r.status_code == 200
    # No CORS middleware was installed, so no allow-origin header comes back.
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_header_present_for_allowed_origin(monkeypatch, tmp_path) -> None:
    client = _boot_app(
        monkeypatch, tmp_path, "https://web.example, https://other.example"
    )
    r = client.get("/health", headers={"Origin": "https://web.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://web.example"


def test_cors_absent_for_disallowed_origin(monkeypatch, tmp_path) -> None:
    client = _boot_app(monkeypatch, tmp_path, "https://web.example")
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    # Starlette's CORSMiddleware simply omits the allow-origin header for
    # origins not on the allow list — the browser then blocks the response.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_preflight_options_returns_expected_methods(monkeypatch, tmp_path) -> None:
    client = _boot_app(monkeypatch, tmp_path, "https://web.example")
    r = client.options(
        "/search",
        headers={
            "Origin": "https://web.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    allowed_methods = r.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods
    assert "GET" in allowed_methods


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reload the module after each test so CORS state doesn't leak."""

    yield
    import services.api as api_mod
    importlib.reload(api_mod)
