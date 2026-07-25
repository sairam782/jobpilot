"""SQLite persistence for episodic JobPilot memory."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def init_db(db_path: Path) -> None:
    """Create the audit memory database if it does not exist."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                url TEXT NOT NULL,
                action TEXT NOT NULL,
                llm_prompt TEXT NOT NULL,
                llm_output TEXT NOT NULL,
                result TEXT NOT NULL,
                error_text TEXT
            )
            """
        )


def log_iteration(
    db_path: Path,
    url: str,
    action: str,
    llm_prompt: str,
    llm_output: str,
    result: str,
    error_text: str | None = None,
) -> None:
    """Insert one graph iteration into the audit log."""

    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO action_log
            (timestamp, url, action, llm_prompt, llm_output, result, error_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                url,
                action[:4000],
                llm_prompt[:4000],
                llm_output[:4000],
                result[:4000],
                error_text[:4000] if error_text else None,
            ),
        )
