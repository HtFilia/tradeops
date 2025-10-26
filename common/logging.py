from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable


RESERVED_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}

DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class StructuredLogFormatter(logging.Formatter):
    """Formats log records into a standard JSON structure."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self._component = component

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        component_name = (
            getattr(record, "component", None)
            or getattr(record, "name", None)
            or self._component
        )
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": component_name,
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "span_id": getattr(record, "span_id", None),
        }

        # Capture additional contextual fields.
        context: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in RESERVED_RECORD_ATTRS:
                continue
            if key in payload and payload[key] == value:
                continue
            if key in {"component", "event", "request_id", "correlation_id", "span_id"}:
                payload[key] = value
                continue
            if key == "context" and isinstance(value, dict):
                context.update(value)
            elif key not in payload:
                context[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if context:
            payload["context"] = context

        # Remove null values for cleanliness before serialization.
        compact_payload = {k: v for k, v in payload.items() if v is not None}
        return json.dumps(compact_payload, separators=(",", ":"))


def configure_structured_logging(component: str, *, level: str | int | None = None) -> logging.Logger:
    """Configure and return a logger that emits structured JSON logs."""

    log_level = level or DEFAULT_LOG_LEVEL
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger(component)
    logger.setLevel(log_level)
    logger.propagate = False

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(StructuredLogFormatter(component=component))

    logger.handlers.clear()
    logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger that inherits structured configuration."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        parent_name = name.split(".")[0]
        configure_structured_logging(parent_name)
        logger = logging.getLogger(name)
    return logger


def log_schema_fields() -> Iterable[str]:
    """Expose schema field names for documentation or validation."""

    return (
        "timestamp",
        "level",
        "component",
        "event",
        "message",
        "request_id",
        "correlation_id",
        "span_id",
        "context",
        "exception",
    )
