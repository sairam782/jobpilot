"""queue.mark_many: bulk transitions with per-row failure isolation."""

from __future__ import annotations

import pytest

from orchestrator import queue


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "queue.sqlite3"


def _enqueue_and_park(db, url: str) -> int:
    """Get one job to needs_approval so approve/reject/skip are legal."""

    row = queue.enqueue(db, url=url, title="X", source="test", score=0.9)
    queue.pick_next(db)
    queue.mark_needs_approval(
        db, row.id, filled_fields={}, answer_previews=[], audit_entries=[]
    )
    return row.id


def test_mark_many_approves_a_batch(db) -> None:
    ids = [_enqueue_and_park(db, f"https://ex/{i}") for i in range(3)]
    outcomes = queue.mark_many(db, ids, action="approve", note="looks good")
    assert [o.ok for o in outcomes] == [True, True, True]
    assert [o.status for o in outcomes] == ["approved"] * 3

    counts = queue.count_by_status(db)
    assert counts.get("approved") == 3


def test_mark_many_isolates_per_row_failures(db) -> None:
    good_1 = _enqueue_and_park(db, "https://ex/1")
    good_2 = _enqueue_and_park(db, "https://ex/2")
    # queued rows cannot be approved directly — that's the invalid one.
    invalid = queue.enqueue(db, url="https://ex/3", title="X", source="t", score=0.5).id
    missing = 999_999

    outcomes = queue.mark_many(db, [good_1, invalid, missing, good_2], action="approve")

    by_id = {o.id: o for o in outcomes}
    assert by_id[good_1].ok is True and by_id[good_1].status == "approved"
    assert by_id[good_2].ok is True and by_id[good_2].status == "approved"
    assert by_id[invalid].ok is False and "invalid transition" in by_id[invalid].error
    assert by_id[missing].ok is False and "not found" in by_id[missing].error


def test_mark_many_supports_skip_and_requeue(db) -> None:
    parked = _enqueue_and_park(db, "https://ex/a")
    outcomes = queue.mark_many(db, [parked], action="skip", note="not this round")
    assert outcomes[0].status == "skipped"

    failed = queue.enqueue(db, url="https://ex/b", title="X", source="t").id
    queue.pick_next(db)
    queue.mark_failed(db, failed, error="boom")
    outcomes = queue.mark_many(db, [failed], action="requeue")
    assert outcomes[0].status == "queued"


def test_mark_many_rejects_unknown_action(db) -> None:
    with pytest.raises(queue.QueueError):
        queue.mark_many(db, [1], action="pizza")


def test_mark_many_preserves_input_order(db) -> None:
    ids = [_enqueue_and_park(db, f"https://ex/{i}") for i in range(5)]
    shuffled = [ids[2], ids[4], ids[0], ids[1], ids[3]]
    outcomes = queue.mark_many(db, shuffled, action="reject", note="pass")
    assert [o.id for o in outcomes] == shuffled
