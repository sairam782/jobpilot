"""SQLite persistence for episodic JobPilot memory."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class AuditRow:
    """One row of the action_log table."""

    id: int
    timestamp: str
    url: str
    action: str
    llm_prompt: str
    llm_output: str
    result: str
    error_text: str | None


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
        # Recent-first reads without a scan; url filter for per-job audit views.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_log_timestamp "
            "ON action_log(timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_log_url_timestamp "
            "ON action_log(url, timestamp DESC)"
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


def list_recent(db_path: Path, limit: int = 50, url: str | None = None) -> list[AuditRow]:
    """Return the most recent audit rows, newest first.

    Bounded to 500 results per call to keep the API response cap sane;
    callers that need a full export should read the SQLite file directly.
    """

    init_db(db_path)
    limit = max(1, min(int(limit), 500))
    query = "SELECT id, timestamp, url, action, llm_prompt, llm_output, result, error_text FROM action_log"
    params: tuple = ()
    if url:
        query += " WHERE url = ?"
        params = (url,)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params = (*params, limit)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        AuditRow(
            id=row[0],
            timestamp=row[1],
            url=row[2],
            action=row[3],
            llm_prompt=row[4],
            llm_output=row[5],
            result=row[6],
            error_text=row[7],
        )
        for row in rows
    ]
