"""log.bind(**ctx) merges into every record's extra."""

from __future__ import annotations

import io
import json
import logging

from services.logging_config import JSONFormatter, get_logger


def _capture(handler_setup) -> tuple[io.StringIO, logging.Logger]:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler_setup(handler)
    logger = logging.getLogger("jobpilot.test.bind")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.addHandler(handler)
    logger.propagate = False
    return buffer, logger


def _last_json(buffer: io.StringIO) -> dict:
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert lines, "expected at least one log line"
    return json.loads(lines[-1])


def test_bind_stamps_context_on_every_record() -> None:
    buffer, base = _capture(lambda h: h.setFormatter(JSONFormatter()))
    log = get_logger(base.name).bind(job_id=42, url="https://ex")

    log.info("started")
    log.warning("slow")

    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    assert all(entry["job_id"] == 42 for entry in lines)
    assert all(entry["url"] == "https://ex" for entry in lines)


def test_bind_chains_and_call_site_extra_wins() -> None:
    buffer, base = _capture(lambda h: h.setFormatter(JSONFormatter()))
    log = get_logger(base.name).bind(job_id=1).bind(stage="observe")

    log.info("first")
    entry = _last_json(buffer)
    assert entry["job_id"] == 1
    assert entry["stage"] == "observe"

    # Call-site extra overrides the bound value for this record only.
    log.info("second", extra={"stage": "plan", "retry": 1})
    entry = _last_json(buffer)
    assert entry["job_id"] == 1
    assert entry["stage"] == "plan"
    assert entry["retry"] == 1

    # Original bindings still there on the next unrelated call.
    log.info("third")
    entry = _last_json(buffer)
    assert entry["stage"] == "observe"


def test_bind_returns_new_adapter_without_mutating_parent() -> None:
    parent = get_logger("jobpilot.test.parent")
    child = parent.bind(job_id=7)
    assert child is not parent
    assert child.extra["job_id"] == 7
    assert "job_id" not in (parent.extra or {})
