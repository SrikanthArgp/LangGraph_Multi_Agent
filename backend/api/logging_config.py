"""Structured logging (Phase 12 baseline + Phase 14 trace correlation).

structlog is configured as a thin layer over stdlib `logging` rather than replacing it: most
of the existing codebase (api/dependencies.py, auth/dependencies.py, cache/*, etc.) already
calls `logging.getLogger(__name__).warning(...)` directly and isn't being rewritten for this
phase. `structlog.stdlib.ProcessorFormatter` bridges both worlds — stdlib log records and
structlog-originated ones are rendered through the same JSON pipeline, and
`merge_contextvars` pulls in whatever request_id/user_id/session_id has been bound via
`structlog.contextvars.bind_contextvars(...)` for the current request, whichever kind of
logger emitted the record.

Phase 14 adds `_add_trace_context`: every log line emitted while an OTel span is active
(i.e. during a request, once api/otel_client.setup_otel() has instrumented the app) picks up
that span's trace_id/span_id, so a log line in Loki can be clicked through to its matching
trace in Tempo. This is additive to Phase 12's baseline, not a parallel/competing config —
kept in this same file rather than a separate one, since a second logging config would just
mean two things to keep in sync.
"""

import logging

import structlog
from opentelemetry import trace


def _add_trace_context(logger, method_name, event_dict):
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


def configure_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_trace_context,
    ]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
