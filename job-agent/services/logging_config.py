"""Structured logging configuration for JobPilot."""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar

from config.settings import settings

_CONFIGURED = False


class JSONFormatter(logging.Formatter):
    """Format log records as one-line JSON objects."""

    _RESERVED: ClassVar[set[str]] = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            payload[key] = _safe(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def _safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def configure_logging(level: str | None = None, fmt: str | None = None) -> None:
    """Idempotently configure root logging based on settings."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = (level or settings.log_level).upper()
    resolved_fmt = (fmt or settings.log_format).lower()

    handler = logging.StreamHandler(sys.stdout)
    if resolved_fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved_level)

    # Quiet noisy libraries a little.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(max(logging.INFO, root.level))

    _CONFIGURED = True


def get_logger(name: str) -> logging.LoggerAdapter[logging.Logger]:
    """Return a logger adapter that attaches contextual `extra` fields."""

    configure_logging()
    base = logging.getLogger(name)
    return logging.LoggerAdapter(base, {})
