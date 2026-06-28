from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry import propagate

from runtime_narrative.middleware import RuntimeNarrativeMiddleware, _OTEL_PROPAGATION_AVAILABLE
from runtime_narrative.renderer.otel_renderer import OtelRenderer


def _make_app(renderer, **middleware_kwargs):
    async def homepage(request: Request):
        return PlainTextResponse("ok")
    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(RuntimeNarrativeMiddleware, renderers=[renderer], **middleware_kwargs)
    return app


def _make_provider():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, provider


def test_propagation_available():
    assert _OTEL_PROPAGATION_AVAILABLE is True


def test_no_traceparent_creates_root_span():
    exporter, provider = _make_provider()
    renderer = OtelRenderer(tracer_provider=provider)
    app = _make_app(renderer)
    old = propagate.get_global_textmap()
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    try:
        with TestClient(app) as client:
            response = client.get("/")
        assert response.status_code == 200
        spans = exporter.get_finished_spans()
        story_span = next(s for s in spans if s.name == "GET /")
        assert story_span.parent is None
    finally:
        propagate.set_global_textmap(old)


def test_traceparent_header_parents_story_span():
    exporter, provider = _make_provider()
    renderer = OtelRenderer(tracer_provider=provider)
    app = _make_app(renderer)
    old = propagate.get_global_textmap()
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    try:
        traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        with TestClient(app) as client:
            response = client.get("/", headers={"traceparent": traceparent})
        assert response.status_code == 200
        expected_span_id = int("b7ad6b7169203331", 16)
        story_span = next(s for s in exporter.get_finished_spans() if s.name == "GET /")
        assert story_span.parent is not None
        assert story_span.parent.span_id == expected_span_id
    finally:
        propagate.set_global_textmap(old)


def test_propagate_false_ignores_header():
    exporter, provider = _make_provider()
    renderer = OtelRenderer(tracer_provider=provider)
    app = _make_app(renderer, propagate_trace_context=False)
    old = propagate.get_global_textmap()
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    try:
        traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        with TestClient(app) as client:
            response = client.get("/", headers={"traceparent": traceparent})
        assert response.status_code == 200
        story_span = next(s for s in exporter.get_finished_spans() if s.name == "GET /")
        assert story_span.parent is None
    finally:
        propagate.set_global_textmap(old)


def test_propagation_no_otel_is_noop(monkeypatch):
    monkeypatch.setattr("runtime_narrative.middleware._OTEL_PROPAGATION_AVAILABLE", False)
    exporter, provider = _make_provider()
    renderer = OtelRenderer(tracer_provider=provider)
    app = _make_app(renderer)
    traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    with TestClient(app) as client:
        response = client.get("/", headers={"traceparent": traceparent})
    assert response.status_code == 200
