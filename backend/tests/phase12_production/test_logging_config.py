import json
import logging

import structlog

from api.logging_config import configure_logging


def test_configure_logging_does_not_raise():
    configure_logging()


def test_bound_contextvars_appear_in_every_log_line(capsys):
    """The whole point of binding request_id/user_id/session_id via contextvars (api/main.py's
    middleware, auth/dependencies.py's get_current_user, the routers' _get_owned_session_or_404
    helpers) instead of passing them explicitly is that they show up on *every* log line during
    that request - including ones from plain stdlib `logging.getLogger(__name__)` calls
    scattered across the codebase, not just structlog-originated ones. This asserts both paths.
    """
    configure_logging()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-request-id")

    try:
        structlog.get_logger("test.structlog").info("structlog_event", foo="bar")
        logging.getLogger("test.stdlib").warning("stdlib_event")
    finally:
        structlog.contextvars.clear_contextvars()

    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 2

    structlog_record = json.loads(lines[0])
    assert structlog_record["event"] == "structlog_event"
    assert structlog_record["foo"] == "bar"
    assert structlog_record["request_id"] == "test-request-id"

    stdlib_record = json.loads(lines[1])
    assert stdlib_record["event"] == "stdlib_event"
    assert stdlib_record["request_id"] == "test-request-id"


def test_clear_contextvars_prevents_leaking_into_later_log_lines(capsys):
    configure_logging()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="leaked-id")
    structlog.contextvars.clear_contextvars()

    structlog.get_logger("test.structlog").info("after_clear")

    captured = capsys.readouterr()
    record = json.loads(captured.err.strip())
    assert "request_id" not in record
