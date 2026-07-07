import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine

from api import otel_client
from config import get_settings


class _FakeAsyncEngine:
    """Stands in for db/base.py's real AsyncEngine - setup_otel only ever touches
    `.sync_engine`, and SQLAlchemyInstrumentor doesn't need a reachable database to
    instrument an engine's connection-pool hooks, so a real in-memory sqlite engine
    (stdlib, no extra driver needed) is enough without pulling in Supabase for a unit test.
    """

    def __init__(self, sync_engine):
        self.sync_engine = sync_engine


def _unconfigured_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "otel_exporter_otlp_endpoint", None)
    monkeypatch.setattr(settings, "grafana_otlp_instance_id", None)
    monkeypatch.setattr(settings, "grafana_otlp_token", None)
    return settings


def test_build_otlp_headers_encodes_basic_auth():
    headers = otel_client._build_otlp_headers("12345", "secret-token")
    expected = base64.b64encode(b"12345:secret-token").decode()
    assert headers == {"Authorization": f"Basic {expected}"}


def test_setup_otel_degrades_without_raising_when_otlp_unconfigured(monkeypatch):
    """Per plan.md Phase 14 step 7/get_langfuse_handler's fail-open precedent: a missing
    Grafana Cloud config must never block app startup.
    """
    _unconfigured_settings(monkeypatch)

    app = FastAPI()
    fake_engine = _FakeAsyncEngine(create_engine("sqlite:///:memory:"))

    otel_client.setup_otel(app, fake_engine)  # must not raise


def test_setup_otel_instruments_fastapi_and_records_spans(monkeypatch):
    """The InMemorySpanExporter check from plan.md Phase 14 step 7 - confirms a real span is
    created for a request through an app instrumented by setup_otel(), independent of
    whether Grafana Cloud is reachable (this test runs fully offline).
    """
    _unconfigured_settings(monkeypatch)

    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    fake_engine = _FakeAsyncEngine(create_engine("sqlite:///:memory:"))
    provider = otel_client.setup_otel(app, fake_engine)

    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with TestClient(app) as client:
        response = client.get("/ping")
    assert response.status_code == 200

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    assert any(span.attributes.get("http.route") == "/ping" for span in spans)
