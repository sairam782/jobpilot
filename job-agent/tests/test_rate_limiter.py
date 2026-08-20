import pytest

from orchestrator import queue, rate_limiter


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "queue.sqlite3"


def _submit(db, url: str) -> None:
    row = queue.enqueue(db, url=url, title="X", source="t", score=1.0)
    queue.pick_next(db)
    queue.mark_needs_approval(
        db, row.id, filled_fields={}, answer_previews=[], audit_entries=[]
    )
    queue.approve(db, row.id)
    queue.mark_submitted(db, row.id)


def test_status_reflects_submissions(db) -> None:
    for i in range(3):
        _submit(db, f"https://ex.test/{i}")
    snap = rate_limiter.status(db, max_per_day=5)
    assert snap.submitted_24h == 3
    assert snap.remaining == 2
    assert snap.allowed is True


def test_check_raises_when_exhausted(db) -> None:
    for i in range(2):
        _submit(db, f"https://ex.test/{i}")
    with pytest.raises(RuntimeError):
        rate_limiter.check(db, max_per_day=2)
