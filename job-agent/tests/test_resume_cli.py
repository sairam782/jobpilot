"""CLI `resume expand` and `resume show` subcommands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "main.py", "resume", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )


def _env(tmp_path: Path) -> dict:
    """A minimal env that isolates state to tmp_path and disables the LLM."""

    import os
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""              # forces offline copy path
    env["DATABASE_PATH"] = str(tmp_path / "db.sqlite3")
    env["RESUME_EXPANDED_PATH"] = str(tmp_path / "resume.txt")
    env["QA_CACHE_PATH"] = str(tmp_path / "qa.json")
    env["AUDIT_LOG_PATH"] = str(tmp_path / "audit.log")
    env["LOG_FORMAT"] = "console"
    env["LOG_LEVEL"] = "WARNING"   # keep INFO logs off the JSON stdout
    return env


def test_resume_expand_from_txt_writes_output_and_prints_summary(tmp_path: Path) -> None:
    src = tmp_path / "in.txt"
    src.write_text(
        "Senior AI engineer with Python, PyTorch, RAG, LangChain, "
        "Kubernetes, PostgreSQL, FastAPI experience.",
        encoding="utf-8",
    )
    result = _run(_env(tmp_path), "expand", str(src))
    assert result.returncode == 0, result.stderr

    out_path = Path(tmp_path / "resume.txt")
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "PyTorch" in text or "pytorch" in text.lower()

    payload = json.loads(result.stdout)
    assert payload["path"] == str(out_path)
    assert payload["chars"] > 0
    assert payload["words"] > 0
    assert payload["seniority_signal"] == "senior"
    # Detected skills come from the curated vocabulary.
    assert {"python", "pytorch"}.issubset(set(payload["detected_skills"]))


def test_resume_show_reads_default_expanded_path(tmp_path: Path) -> None:
    (tmp_path / "resume.txt").write_text(
        "Junior data scientist. Python pandas experience.",
        encoding="utf-8",
    )
    result = _run(_env(tmp_path), "show")
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["seniority_signal"] == "junior"
    assert "python" in payload["detected_skills"]


def test_resume_expand_errors_on_missing_file(tmp_path: Path) -> None:
    result = _run(_env(tmp_path), "expand", str(tmp_path / "nope.pdf"))
    assert result.returncode == 2
    assert "does not exist" in result.stdout + result.stderr
