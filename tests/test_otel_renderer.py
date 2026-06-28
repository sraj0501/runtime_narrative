from __future__ import annotations

from datetime import datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from runtime_narrative.events import (
    FailureOccurred,
    LLMAnalysisReady,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.otel_renderer import OtelRenderer


def _make_provider():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, provider


def _ts(second: int = 0) -> datetime:
    return datetime(2024, 1, 1, 12, 0, second)


def _failure(**kwargs) -> FailureOccurred:
    defaults = dict(
        story_id="s1",
        story_name="S",
        stage_name="Step",
        error_type="ValueError",
        error_message="bad value",
        filename="app.py",
        lineno=42,
        function="do_thing",
        source_line="raise ValueError('bad value')",
        exception_chain="ValueError: bad value",
        exact_cause="bad value was passed",
        llm_analysis=None,
        stage_timeline="Step",
        progress_percent=0,
        completed_stages=0,
        total_stages=1,
        timestamp=_ts(1),
        traceback_text="Traceback (most recent call last):\n  ...",
    )
    defaults.update(kwargs)
    return FailureOccurred(**defaults)


# ── happy path ────────────────────────────────────────────────────────────────

def test_story_produces_root_span() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Load Data", timestamp=_ts(0)))
    r.handle(StoryCompleted(story_id="s1", story_name="Load Data", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(5)))

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "Load Data"
    assert spans[0].status.status_code == StatusCode.OK


def test_stage_produces_child_span() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Pipeline", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Fetch", timestamp=_ts(1)))
    r.handle(StageCompleted(story_id="s1", stage_name="Fetch", timestamp=_ts(2), duration_seconds=1.0))
    r.handle(StoryCompleted(story_id="s1", story_name="Pipeline", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(3)))

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    child = next(s for s in spans if s.name == "Fetch")
    root = next(s for s in spans if s.name == "Pipeline")
    assert child.parent is not None
    assert child.parent.span_id == root.get_span_context().span_id


def test_stage_span_duration() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Work", timestamp=_ts(1)))
    r.handle(StageCompleted(story_id="s1", stage_name="Work", timestamp=_ts(3), duration_seconds=2.0))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(3)))

    spans = exporter.get_finished_spans()
    child = next(s for s in spans if s.name == "Work")
    duration_ns = child.end_time - child.start_time
    assert abs(duration_ns - 2 * 10**9) < 100  # within 100 nanoseconds


# ── failure path ──────────────────────────────────────────────────────────────

def test_failure_sets_error_status() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Step", timestamp=_ts(1)))
    r.handle(_failure())
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "S")
    assert root.status.status_code == StatusCode.ERROR


def test_failure_sets_attributes() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(_failure(error_type="TypeError", error_message="wrong type", filename="svc.py", lineno=99, function="run"))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "S")
    attrs = root.attributes
    assert attrs["error.type"] == "TypeError"
    assert attrs["error.message"] == "wrong type"
    assert attrs["code.filepath"] == "svc.py"
    assert attrs["code.lineno"] == 99
    assert attrs["code.function"] == "run"
    assert attrs["narrative.stage_name"] == "Step"


def test_failure_ends_stage_span_with_error() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Step", timestamp=_ts(1)))
    r.handle(_failure(stage_name="Step"))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    stage_span = next((s for s in spans if s.name == "Step"), None)
    assert stage_span is not None
    assert stage_span.status.status_code == StatusCode.ERROR


def test_story_completed_success_false_preserves_error_status() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(_failure())
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "S")
    assert root.status.status_code == StatusCode.ERROR


# ── LLM analysis ─────────────────────────────────────────────────────────────

def test_llm_analysis_ready_adds_span_event() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(LLMAnalysisReady(story_id="s1", story_name="S", stage_name="Step", llm_analysis="Check line 47", timestamp=_ts(1)))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "S")
    assert len(root.events) == 1
    assert root.events[0].name == "llm_analysis_ready"
    assert root.events[0].attributes["narrative.llm_analysis"] == "Check line 47"
    assert root.events[0].attributes["narrative.stage_name"] == "Step"


# ── concurrency / isolation ───────────────────────────────────────────────────

def test_multiple_concurrent_stories() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Story A", timestamp=_ts(0)))
    r.handle(StoryStarted(story_id="s2", story_name="Story B", timestamp=_ts(0)))
    r.handle(StoryCompleted(story_id="s1", story_name="Story A", success=True, progress_percent=100, completed_stages=0, total_stages=0, timestamp=_ts(1)))
    r.handle(StoryCompleted(story_id="s2", story_name="Story B", success=True, progress_percent=100, completed_stages=0, total_stages=0, timestamp=_ts(2)))

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert {s.name for s in spans} == {"Story A", "Story B"}
    for span in spans:
        assert span.parent is None


# ── attribute truncation ──────────────────────────────────────────────────────

def test_attribute_truncation() -> None:
    exporter, provider = _make_provider()
    r = OtelRenderer(tracer_provider=provider, max_attribute_length=10)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(_failure(error_message="x" * 20))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(1)))

    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "S")
    assert root.attributes["error.message"] == "x" * 10 + "[truncated]"


# ── missing dependency ────────────────────────────────────────────────────────

def test_missing_opentelemetry_raises_on_init(monkeypatch) -> None:
    import runtime_narrative.renderer.otel_renderer as mod
    monkeypatch.setattr(mod, "_OTEL_AVAILABLE", False)
    with pytest.raises(ImportError, match="opentelemetry"):
        OtelRenderer()
