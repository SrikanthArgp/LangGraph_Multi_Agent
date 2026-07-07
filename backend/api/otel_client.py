import base64
import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from config import get_settings

logger = logging.getLogger(__name__)


def _build_otlp_headers(instance_id: str, token: str) -> dict[str, str]:
    credentials = base64.b64encode(f"{instance_id}:{token}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


def setup_otel(app: FastAPI, db_engine: AsyncEngine) -> TracerProvider:
    """Wire general app tracing (FastAPI/SQLAlchemy/Redis) into Grafana Cloud Tempo via OTLP.

    Kept separate from observability/langfuse_client.py, which stays scoped to LLM/chain-level
    detail — this covers everything around it (HTTP requests, DB queries, cache calls).

    Degrades to local-only spans (created, never exported) rather than raising when
    GRAFANA_OTLP_INSTANCE_ID/_TOKEN or OTEL_EXPORTER_OTLP_ENDPOINT aren't configured — same
    fail-open pattern as get_langfuse_handler(), so a missing/misconfigured Grafana Cloud
    stack never blocks app startup.

    Returns the TracerProvider instrumented into `app` - `trace.get_tracer_provider()` is
    process-global and only settable once, so a caller (e.g. a test attaching an
    InMemorySpanExporter) that needs *this* provider specifically, not whatever the process
    global happens to already be, should use the return value rather than the global getter.
    """
    settings = get_settings()
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "crag-multi-agent-api"}))

    if (
        settings.otel_exporter_otlp_endpoint
        and settings.grafana_otlp_instance_id
        and settings.grafana_otlp_token
    ):
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces",
            headers=_build_otlp_headers(
                settings.grafana_otlp_instance_id, settings.grafana_otlp_token
            ),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        logger.warning(
            "otel_otlp_not_configured",
            extra={"detail": "spans created locally only, not exported to Grafana Cloud"},
        )

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    # AsyncEngine wraps a plain sync Engine underneath (.sync_engine) — the instrumentor's
    # connection-pool hooks are sync-engine-only, this is the documented way to instrument
    # a SQLAlchemy async engine, not a workaround.
    SQLAlchemyInstrumentor().instrument(engine=db_engine.sync_engine, tracer_provider=provider)
    RedisInstrumentor().instrument(tracer_provider=provider)

    return provider
