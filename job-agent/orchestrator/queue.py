"""SQLite-backed application queue.

Tracks the lifecycle of a job application from discovery through submission.
The queue is the source of truth for what JobPilot has seen, is working on,
and has finished. It is intentionally simple: a single table, a small state
machine, and no background thread. Callers drive transitions explicitly.

State machine
-------------
    queued
      | pick_next()
      v
    running
      | mark_needs_approval()          | mark_submitted()   | mark_failed()
      v                                 v                   v
    needs_approval --> approved --> submitted            failed
      |
      v
    rejected / skipped

Terminal states: submitted, rejected, skipped, failed.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

QUEUED = "queued"
RUNNING = "running"
NEEDS_APPROVAL = "needs_approval"
APPROVED = "approved"
SUBMITTED = "submitted"
REJECTED = "rejected"
SKIPPED = "skipped"
FAILED = "failed"

TERMINAL_STATES = {SUBMITTED, REJECTED, SKIPPED, FAILED}
ACTIVE_STATES = {QUEUED, RUNNING, NEEDS_APPROVAL, APPROVED}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    QUEUED: {RUNNING, SKIPPED},
    RUNNING: {NEEDS_APPROVAL, SUBMITTED, FAILED, SKIPPED},
    NEEDS_APPROVAL: {APPROVED, REJECTED, SKIPPED},
    APPROVED: {SUBMITTED, RUNNING, FAILED},
    SUBMITTED: set(),
    REJECTED: set(),
    SKIPPED: set(),
    FAILED: {QUEUED},  # allow retry
}


class QueueError(RuntimeError):
    """Raised for invalid transitions or missing rows."""


@dataclass
class QueuedJob:
    """One row in the application queue."""

    id: int | None
    url: str
    title: str
    company: str | None
    source: str
    score: float
    status: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    filled_fields: dict[str, str] = field(default_factory=dict)
    answer_previews: list[str] = field(default_factory=list)
    audit_entries: list[str] = field(default_factory=list)
    error_text: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_public(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _txn(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    started = False
    try:
        conn.execute("BEGIN IMMEDIATE;")
        started = True
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        if started:
            try:
                conn.execute("ROLLBACK;")
            except sqlite3.Error:
                pass
        raise
    finally:
        conn.close()


def init_queue(db_path: Path) -> None:
    """Create tables and indexes if missing."""

    with _txn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                company TEXT,
                source TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                reasons_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                filled_json TEXT NOT NULL DEFAULT '{}',
                answers_json TEXT NOT NULL DEFAULT '[]',
                audit_json TEXT NOT NULL DEFAULT '[]',
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_status_score "
            "ON queue(status, score DESC);"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submission_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_id INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY(queue_id) REFERENCES queue(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_submission_submitted_at "
            "ON submission_log(submitted_at);"
        )


def _row_to_job(row: sqlite3.Row) -> QueuedJob:
    return QueuedJob(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        company=row["company"],
        source=row["source"],
        score=row["score"],
        status=row["status"],
        reasons=json.loads(row["reasons_json"] or "[]"),
        metadata=json.loads(row["metadata_json"] or "{}"),
        filled_fields=json.loads(row["filled_json"] or "{}"),
        answer_previews=json.loads(row["answers_json"] or "[]"),
        audit_entries=json.loads(row["audit_json"] or "[]"),
        error_text=row["error_text"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def enqueue(
    db_path: Path,
    *,
    url: str,
    title: str,
    source: str,
    company: str | None = None,
    score: float = 0.0,
    reasons: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> QueuedJob:
    """Add a job to the queue, or return the existing row if the URL is a dup."""

    init_queue(db_path)
    now = _now()
    with _txn(db_path) as conn:
        existing = conn.execute("SELECT * FROM queue WHERE url = ?", (url,)).fetchone()
        if existing:
            return _row_to_job(existing)
        cur = conn.execute(
            """
            INSERT INTO queue
                (url, title, company, source, score, status,
                 reasons_json, metadata_json, filled_json, answers_json, audit_json,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', '[]', '[]', ?, ?)
            """,
            (
                url,
                title,
                company,
                source,
                float(score),
                QUEUED,
                json.dumps(reasons or [], ensure_ascii=True),
                json.dumps(metadata or {}, ensure_ascii=True, default=str),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM queue WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_job(row)


def enqueue_many(
    db_path: Path, jobs: list[dict[str, Any]]
) -> tuple[list[QueuedJob], int]:
    """Bulk enqueue. Returns (created_or_existing, new_count)."""

    init_queue(db_path)
    created: list[QueuedJob] = []
    new_count = 0
    for job in jobs:
        before = count_by_status(db_path).get(QUEUED, 0)
        row = enqueue(db_path, **job)
        after = count_by_status(db_path).get(QUEUED, 0)
        if after > before:
            new_count += 1
        created.append(row)
    return created, new_count


def get(db_path: Path, job_id: int | None) -> QueuedJob:
    """Fetch by id."""

    init_queue(db_path)
    if job_id is None:
        raise QueueError("job_id is required")
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise QueueError(f"queue row {job_id} not found")
    return _row_to_job(row)


def list_jobs(
    db_path: Path,
    *,
    status: str | list[str] | None = None,
    limit: int = 100,
) -> list[QueuedJob]:
    """List queue rows, optionally filtered by status."""

    init_queue(db_path)
    limit = max(1, min(limit, 500))
    query = "SELECT * FROM queue"
    params: list[Any] = []
    if status:
        statuses = [status] if isinstance(status, str) else list(status)
        placeholders = ",".join("?" * len(statuses))
        query += f" WHERE status IN ({placeholders})"
        params.extend(statuses)
    query += " ORDER BY score DESC, created_at ASC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_job(row) for row in rows]


def pick_next(db_path: Path) -> QueuedJob | None:
    """Atomically transition the highest-scoring queued job to `running`.

    Returns the picked row, or None if the queue is empty.
    """

    init_queue(db_path)
    with _txn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM queue WHERE status = ? "
            "ORDER BY score DESC, created_at ASC LIMIT 1",
            (QUEUED,),
        ).fetchone()
        if not row:
            return None
        now = _now()
        conn.execute(
            "UPDATE queue SET status = ?, updated_at = ? WHERE id = ?",
            (RUNNING, now, row["id"]),
        )
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (row["id"],)).fetchone()
        return _row_to_job(row)


def _apply_transition(
    db_path: Path,
    job_id: int,
    new_status: str,
    *,
    filled_fields: dict[str, str] | None = None,
    answer_previews: list[str] | None = None,
    audit_entries: list[str] | None = None,
    error_text: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> QueuedJob:
    with _txn(db_path) as conn:
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise QueueError(f"queue row {job_id} not found")
        current = row["status"]
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed and new_status != current:
            raise QueueError(
                f"invalid transition {current} -> {new_status} for job {job_id}"
            )

        updates: list[str] = ["status = ?", "updated_at = ?"]
        params: list[Any] = [new_status, _now()]

        if filled_fields is not None:
            existing = json.loads(row["filled_json"] or "{}")
            existing.update(filled_fields)
            updates.append("filled_json = ?")
            params.append(json.dumps(existing, ensure_ascii=True, default=str))
        if answer_previews is not None:
            existing_ans = json.loads(row["answers_json"] or "[]")
            existing_ans.extend(answer_previews)
            updates.append("answers_json = ?")
            params.append(json.dumps(existing_ans, ensure_ascii=True, default=str))
        if audit_entries is not None:
            existing_audit = json.loads(row["audit_json"] or "[]")
            existing_audit.extend(audit_entries)
            updates.append("audit_json = ?")
            params.append(json.dumps(existing_audit, ensure_ascii=True, default=str))
        if error_text is not None:
            updates.append("error_text = ?")
            params.append(error_text)
        if metadata_patch:
            meta = json.loads(row["metadata_json"] or "{}")
            meta.update(metadata_patch)
            updates.append("metadata_json = ?")
            params.append(json.dumps(meta, ensure_ascii=True, default=str))

        params.append(job_id)
        conn.execute(f"UPDATE queue SET {', '.join(updates)} WHERE id = ?", params)

        if new_status == SUBMITTED:
            conn.execute(
                "INSERT INTO submission_log(queue_id, submitted_at) VALUES(?, ?)",
                (job_id, _now()),
            )

        row = conn.execute("SELECT * FROM queue WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row)


def mark_needs_approval(
    db_path: Path,
    job_id: int,
    *,
    filled_fields: dict[str, str],
    answer_previews: list[str],
    audit_entries: list[str],
) -> QueuedJob:
    """Pause an in-flight job for human review."""

    return _apply_transition(
        db_path,
        job_id,
        NEEDS_APPROVAL,
        filled_fields=filled_fields,
        answer_previews=answer_previews,
        audit_entries=audit_entries,
    )


def approve(db_path: Path, job_id: int, *, note: str | None = None) -> QueuedJob:
    """Mark a needs_approval row as approved."""

    return _apply_transition(
        db_path,
        job_id,
        APPROVED,
        metadata_patch={"approval_note": note} if note else None,
    )


def reject(db_path: Path, job_id: int, *, note: str | None = None) -> QueuedJob:
    """Mark a needs_approval row as rejected (terminal)."""

    return _apply_transition(
        db_path,
        job_id,
        REJECTED,
        metadata_patch={"rejection_note": note} if note else None,
    )


def mark_submitted(db_path: Path, job_id: int) -> QueuedJob:
    return _apply_transition(db_path, job_id, SUBMITTED)


def mark_failed(db_path: Path, job_id: int, *, error: str) -> QueuedJob:
    return _apply_transition(db_path, job_id, FAILED, error_text=error[:4000])


def mark_skipped(db_path: Path, job_id: int, *, note: str | None = None) -> QueuedJob:
    return _apply_transition(
        db_path,
        job_id,
        SKIPPED,
        metadata_patch={"skip_note": note} if note else None,
    )


def requeue(db_path: Path, job_id: int) -> QueuedJob:
    """Reset a failed row back to queued for another attempt."""

    return _apply_transition(db_path, job_id, QUEUED)


def count_by_status(db_path: Path) -> dict[str, int]:
    """Return a status -> count map for the entire queue."""

    init_queue(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM queue GROUP BY status"
        ).fetchall()
    return {row["status"]: row["c"] for row in rows}


def submissions_since(db_path: Path, since: datetime) -> int:
    """Return the number of submissions logged since `since` (inclusive)."""

    init_queue(db_path)
    since_iso = since.astimezone(UTC).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM submission_log WHERE submitted_at >= ?",
            (since_iso,),
        ).fetchone()
    return int(row["c"])


def submissions_today(db_path: Path) -> int:
    """Count of submissions from the last 24 hours (rolling window)."""

    return submissions_since(db_path, datetime.now(UTC) - timedelta(hours=24))
