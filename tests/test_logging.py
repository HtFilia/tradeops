from __future__ import annotations

import json
import logging

import pytest

from common.logging import StructuredLogFormatter, configure_structured_logging, get_logger, log_schema_fields

pytestmark = pytest.mark.unit


def test_configure_structured_logging_outputs_json(capfd) -> None:
    logger = configure_structured_logging("test.component", level="INFO")
    logger.info(
        "Structured message",
        extra={
            "event": "test.event",
            "context": {"key": "value"},
        },
    )
    captured = capfd.readouterr().out.strip()
    payload = json.loads(captured)
    assert payload["component"] == "test.component"
    assert payload["event"] == "test.event"
    assert payload["context"]["key"] == "value"
    assert payload["message"] == "Structured message"


def test_child_logger_inherits_configuration(capfd) -> None:
    parent = configure_structured_logging("parent", level="INFO")
    child = get_logger("parent.child")
    child.info("child message", extra={"context": {"child": True}})
    captured = capfd.readouterr().out.strip()
    payload = json.loads(captured)
    assert payload["component"] == "parent.child"
    assert payload["context"]["child"] is True


def test_log_schema_field_listing() -> None:
    fields = set(log_schema_fields())
    expected = {
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
    }
    assert fields == expected
