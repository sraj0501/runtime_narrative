from __future__ import annotations

from datetime import datetime

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from runtime_narrative.events import (
    FailureOccurred,
    LLMAnalysisReady,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.otel_metrics_renderer import OtelMetricsRenderer


def _make_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return reader, provider


def _ts(second: int = 0) -> datetime:
    return datetime(2024, 1, 1, 12, 0, second)


def _find_metric(reader, name: str):
    data = reader.get_metrics_data()
    if data is None:
        return None
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == name:
                    return m
    return None


def _failure(**kwargs):
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
        timestamp=_ts(2),
        traceback_text="Traceback...",
    )
    defaults.update(kwargs)
    return FailureOccurred(**defaults)


def test_story_duration_recorded_on_success():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Load", timestamp=_ts(0)))
    r.handle(StoryCompleted(story_id="s1", story_name="Load", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(5)))

    metric = _find_metric(reader, "narrative.story.duration")
    assert metric is not None
    dp = metric.data.data_points[0]
    assert abs(dp.sum - 5.0) < 0.01
    assert dp.attributes["success"] == "true"


def test_story_duration_recorded_on_failure():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Load", timestamp=_ts(0)))
    r.handle(_failure(story_name="Load", story_id="s1"))
    r.handle(StoryCompleted(story_id="s1", story_name="Load", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(3)))

    metric = _find_metric(reader, "narrative.story.duration")
    assert metric is not None
    dp = metric.data.data_points[0]
    assert dp.attributes["success"] == "false"


def test_stage_duration_recorded():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Pipeline", timestamp=_ts(0)))
    r.handle(StageCompleted(story_id="s1", stage_name="Fetch", timestamp=_ts(3), duration_seconds=2.0))

    metric = _find_metric(reader, "narrative.stage.duration")
    assert metric is not None
    dp = metric.data.data_points[0]
    assert abs(dp.sum - 2.0) < 0.01
    assert dp.attributes["story_name"] == "Pipeline"
    assert dp.attributes["stage_name"] == "Fetch"


def test_multiple_stage_durations_aggregated():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageCompleted(story_id="s1", stage_name="A", timestamp=_ts(1), duration_seconds=1.0))
    r.handle(StageCompleted(story_id="s1", stage_name="B", timestamp=_ts(4), duration_seconds=3.0))

    metric = _find_metric(reader, "narrative.stage.duration")
    assert metric is not None
    assert len(metric.data.data_points) >= 1
    total_count = sum(dp.count for dp in metric.data.data_points)
    assert total_count >= 2


def test_failure_counter_incremented():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_id="s1", story_name="Job", error_type="ValueError"))
    r.handle(StoryCompleted(story_id="s1", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    metric = _find_metric(reader, "narrative.story.failures")
    assert metric is not None
    dp = metric.data.data_points[0]
    assert dp.value == 1
    assert dp.attributes["error_type"] == "ValueError"


def test_failure_counter_by_error_type():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_id="s1", story_name="Job", error_type="ValueError"))
    r.handle(StoryCompleted(story_id="s1", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    r.handle(StoryStarted(story_id="s2", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_id="s2", story_name="Job", error_type="TypeError"))
    r.handle(StoryCompleted(story_id="s2", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    metric = _find_metric(reader, "narrative.story.failures")
    assert metric is not None
    error_types = {dp.attributes["error_type"] for dp in metric.data.data_points}
    assert "ValueError" in error_types
    assert "TypeError" in error_types


def test_llm_latency_recorded():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(_failure(story_id="s1", story_name="S", timestamp=_ts(2)))
    r.handle(LLMAnalysisReady(story_id="s1", story_name="S", stage_name="Step", llm_analysis="analysis", timestamp=_ts(5)))

    metric = _find_metric(reader, "narrative.llm.analysis_latency")
    assert metric is not None
    dp = metric.data.data_points[0]
    assert abs(dp.sum - 3.0) < 0.01


def test_llm_latency_not_recorded_without_failure():
    reader, provider = _make_provider()
    r = OtelMetricsRenderer(meter_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(LLMAnalysisReady(story_id="s1", story_name="S", stage_name="Step", llm_analysis="analysis", timestamp=_ts(5)))

    metric = _find_metric(reader, "narrative.llm.analysis_latency")
    assert metric is None


def test_custom_meter_provider_isolation():
    reader1, provider1 = _make_provider()
    reader2, provider2 = _make_provider()
    r1 = OtelMetricsRenderer(meter_provider=provider1)
    r2 = OtelMetricsRenderer(meter_provider=provider2)

    r1.handle(StoryStarted(story_id="s1", story_name="A", timestamp=_ts(0)))
    r1.handle(StoryCompleted(story_id="s1", story_name="A", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(1)))

    assert _find_metric(reader1, "narrative.story.duration") is not None
    assert _find_metric(reader2, "narrative.story.duration") is None


def test_missing_dep_raises_import_error(monkeypatch):
    import runtime_narrative.renderer.otel_metrics_renderer as mod
    monkeypatch.setattr(mod, "_OTEL_METRICS_AVAILABLE", False)
    with pytest.raises(ImportError, match="opentelemetry"):
        OtelMetricsRenderer()
