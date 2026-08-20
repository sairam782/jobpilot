"""Daily submission rate limiter backed by the queue's submission log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from orchestrator import queue


@dataclass(frozen=True)
class RateLimitStatus:
    """Snapshot of remaining daily budget."""

    submitted_24h: int
    max_per_day: int
    remaining: int
    reset_at: datetime

    @property
    def allowed(self) -> bool:
        return self.remaining > 0


def status(db_path: Path, max_per_day: int) -> RateLimitStatus:
    """Snapshot the rolling 24-hour submission window."""

    submitted = queue.submissions_since(db_path, datetime.now(UTC) - timedelta(hours=24))
    remaining = max(max_per_day - submitted, 0)
    return RateLimitStatus(
        submitted_24h=submitted,
        max_per_day=max_per_day,
        remaining=remaining,
        reset_at=datetime.now(UTC) + timedelta(hours=24),
    )


def check(db_path: Path, max_per_day: int) -> None:
    """Raise RuntimeError if the daily budget is exhausted."""

    snap = status(db_path, max_per_day)
    if not snap.allowed:
        raise RuntimeError(
            f"Daily submission cap reached: {snap.submitted_24h}/{snap.max_per_day} "
            f"in the last 24h. Resets around {snap.reset_at.isoformat()}."
        )
