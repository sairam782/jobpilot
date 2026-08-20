from datetime import UTC, datetime, timedelta

import pytest

from orchestrator import queue


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "queue.sqlite3"


def test_enqueue_deduplicates_by_url(db) -> None:
    a = queue.enqueue(db, url="https://example.test/a", title="AI Engineer", source="test", score=0.7)
    b = queue.enqueue(db, url="https://example.test/a", title="AI Engineer", source="test", score=0.9)

    assert a.id == b.id
    counts = queue.count_by_status(db)
    assert counts[queue.QUEUED] == 1


def test_pick_next_returns_highest_score(db) -> None:
    queue.enqueue(db, url="https://ex.test/1", title="Low", source="t", score=0.3)
    queue.enqueue(db, url="https://ex.test/2", title="High", source="t", score=0.9)
    queue.enqueue(db, url="https://ex.test/3", title="Mid", source="t", score=0.6)

    picked = queue.pick_next(db)
    assert picked is not None
    assert picked.title == "High"
    assert picked.status == queue.RUNNING

    # queued=2, running=1
    counts = queue.count_by_status(db)
    assert counts.get(queue.QUEUED) == 2
    assert counts.get(queue.RUNNING) == 1


def test_full_approval_lifecycle_transitions_submissions_log(db) -> None:
    row = queue.enqueue(db, url="https://ex.test/lifecycle", title="X", source="t", score=0.8)
    picked = queue.pick_next(db)
    assert picked.id == row.id

    queue.mark_needs_approval(
        db,
        picked.id,
        filled_fields={"#email": "a@b.co"},
        answer_previews=["preview"],
        audit_entries=["step 1"],
    )
    queue.approve(db, picked.id, note="looks good")
    submitted = queue.mark_submitted(db, picked.id)

    assert submitted.status == queue.SUBMITTED
    assert submitted.filled_fields == {"#email": "a@b.co"}
    assert submitted.answer_previews == ["preview"]
    assert queue.submissions_since(db, datetime.now(UTC) - timedelta(minutes=1)) == 1


def test_invalid_transition_raises(db) -> None:
    row = queue.enqueue(db, url="https://ex.test/bad", title="X", source="t")
    with pytest.raises(queue.QueueError):
        queue.approve(db, row.id)  # queued -> approved is invalid


def test_failed_can_be_requeued(db) -> None:
    row = queue.enqueue(db, url="https://ex.test/retry", title="X", source="t")
    queue.pick_next(db)
    queue.mark_failed(db, row.id, error="boom")
    requeued = queue.requeue(db, row.id)
    assert requeued.status == queue.QUEUED
