"""Structured logging: one JSON object per line, with an event name and fields.

``log_event("authz.decision", tool="pay_upi", allowed=False, ...)`` is the only way the
agent loop, gateways and pipeline log, so every agent step and every authorization
decision is greppable and machine-readable.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

LOGGER_NAME = "whosaid"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=False)


def setup_logging(level: str = "INFO", stream=None) -> None:
    """Install the JSON handler on the ``whosaid`` logger. Idempotent."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    logging.getLogger(LOGGER_NAME).log(level, event, extra={"fields": fields})
