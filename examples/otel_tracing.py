"""Demonstrates OtelRenderer, OtelLogRenderer, and OtelMetricsRenderer.

OtelRenderer     — maps story → root span, stage → child span.
OtelLogRenderer  — emits lifecycle events as OTel log records.
OtelMetricsRenderer — records duration histograms and failure counters.

Requires:
    uv sync --group dev --extra otel

This example uses the SDK's in-memory exporters and a console span exporter
so you can see the output without a running collector.

Run:
    uv run python examples/otel_tracing.py
"""
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
except ImportError:
    print(
        "OpenTelemetry SDK not installed.\n"
        "Install with: uv sync --group dev --extra otel"
    )
    raise SystemExit(1)

from runtime_narrative import OtelRenderer, OtelLogRenderer, OtelMetricsRenderer, stage, story

# ── Tracer setup ──────────────────────────────────────────────────────────────
span_exporter = InMemorySpanExporter()
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
trace.set_tracer_provider(tracer_provider)

# ── Metrics setup ─────────────────────────────────────────────────────────────
metric_reader = InMemoryMetricReader()
meter_provider = MeterProvider(metric_readers=[metric_reader])

# ── Renderers ─────────────────────────────────────────────────────────────────
otel_renderer = OtelRenderer(
    tracer_provider=tracer_provider,
    exclude_stages=set(),      # include all stage spans
    min_duration_ms=0.0,       # no minimum
    max_attribute_length=1024,
)
log_renderer = OtelLogRenderer()
metrics_renderer = OtelMetricsRenderer(meter_provider=meter_provider)

renderers = [otel_renderer, log_renderer, metrics_renderer]

# ── Success story ─────────────────────────────────────────────────────────────
print("=== Success story ===")
with story("Process Orders", renderers=renderers, total_stages=2):
    with stage("Validate Orders"):
        orders = [{"id": 1, "amount": 99.00}]

    with stage("Dispatch"):
        dispatched = len(orders)

# ── Failure story ─────────────────────────────────────────────────────────────
print("\n=== Failure story ===")
try:
    with story("Process Orders", renderers=renderers, total_stages=2):
        with stage("Validate Orders"):
            orders = []

        with stage("Dispatch"):
            if not orders:
                raise ValueError("no orders to dispatch — queue is empty")
except ValueError:
    pass

# ── Inspect collected data ────────────────────────────────────────────────────
spans = span_exporter.get_finished_spans()
print(f"\nCollected {len(spans)} OTel spans:")
for s in spans:
    status = s.status.status_code.name
    duration_ms = (s.end_time - s.start_time) / 1e6
    print(f"  [{status:5s}] {s.name!r:40s}  {duration_ms:.1f}ms")

metrics = metric_reader.get_metrics_data()
print(f"\nCollected metrics from {len(metrics.resource_metrics)} resource(s)")
for rm in metrics.resource_metrics:
    for sm in rm.scope_metrics:
        for m in sm.metrics:
            print(f"  {m.name}")
