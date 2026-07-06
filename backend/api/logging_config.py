"""Baseline structured logging (Phase 12) — stdout JSON only, no trace correlation yet.

structlog is configured as a thin layer over stdlib `logging` rather than replacing it: most
of the existing codebase (api/dependencies.py, auth/dependencies.py, cache/*, etc.) already
calls `logging.getLogger(__name__).warning(...)` directly and isn't being rewritten for this
phase. `structlog.stdlib.ProcessorFormatter` bridges both worlds — stdlib log records and
structlog-originated ones are rendered through the same JSON pipeline, and
`merge_contextvars` pulls in whatever request_id/user_id/session_id has been bound via
`structlog.contextvars.bind_contextvars(...)` for the current request, whichever kind of
logger emitted the record.

Phase 14 (`observability/logging_config.py`, per plan.md) replaces the two literal processors
below (`TimeStamper` + `JSONRenderer`) with a trace_id/span_id-injecting version wired into
OTel — that's a superset of this, not a parallel system.
"""

import logging

import structlog


def configure_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
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
