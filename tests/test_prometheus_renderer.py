from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from prometheus_client import CollectorRegistry

from runtime_narrative.events import (
    FailureOccurred,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.prometheus_renderer import PrometheusRenderer


def _make_renderer() -> tuple[PrometheusRenderer, CollectorRegistry]:
    registry = CollectorRegistry()
    return PrometheusRenderer(registry=registry), registry


def _ts(second: int = 0) -> datetime:
    return datetime(2024, 1, 1, 12, 0, second)


def _metric(registry: CollectorRegistry, name: str, labels: dict) -> float:
    """Fetch a single metric sample value by sample name and exact label set."""
    for metric in registry.collect():
        for sample in metric.samples:
            if sample.name == name and all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    raise KeyError(f"metric {name!r} with labels {labels} not found")


def _failure(**kwargs) -> FailureOccurred:
    defaults = dict(
        story_id="s1",
        story_name="Pipeline",
        stage_name="Step",
        error_type="ValueError",
        error_message="bad",
        filename="app.py",
        lineno=1,
        function="run",
        source_line="raise",
        exception_chain="ValueError: bad",
        exact_cause="bad",
        llm_analysis=None,
        stage_timeline="Step",
        progress_percent=0,
        completed_stages=0,
        total_stages=1,
        timestamp=_ts(2),
        traceback_text="Traceback ...",
    )
    defaults.update(kwargs)
    return FailureOccurred(**defaults)


# ── story duration ────────────────────────────────────────────────────────────

def test_story_duration_recorded_on_success() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="Load", timestamp=_ts(0)))
    r.handle(StoryCompleted(story_id="s1", story_name="Load", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(5)))

    count = _metric(registry, "narrative_story_duration_seconds_count", {"story_name": "Load", "success": "true"})
    assert count == 1.0
    total = _metric(registry, "narrative_story_duration_seconds_sum", {"story_name": "Load", "success": "true"})
    assert abs(total - 5.0) < 0.01


def test_story_duration_labelled_false_on_failure() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="Load", timestamp=_ts(0)))
    r.handle(_failure(story_name="Load"))
    r.handle(StoryCompleted(story_id="s1", story_name="Load", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(3)))

    count = _metric(registry, "narrative_story_duration_seconds_count", {"story_name": "Load", "success": "false"})
    assert count == 1.0


# ── story total counter ───────────────────────────────────────────────────────

def test_story_total_increments() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(1)))

    count = _metric(registry, "narrative_story_total", {"story_name": "S", "success": "true"})
    assert count == 1.0


def test_story_total_multiple_runs() -> None:
    r, registry = _make_renderer()

    for i in range(3):
        r.handle(StoryStarted(story_id=f"s{i}", story_name="Batch", timestamp=_ts(0)))
        r.handle(StoryCompleted(story_id=f"s{i}", story_name="Batch", success=True, progress_percent=100, completed_stages=0, total_stages=0, timestamp=_ts(1)))

    count = _metric(registry, "narrative_story_total", {"story_name": "Batch", "success": "true"})
    assert count == 3.0


# ── stage duration ────────────────────────────────────────────────────────────

def test_stage_duration_recorded() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="Pipeline", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Fetch", timestamp=_ts(1)))
    r.handle(StageCompleted(story_id="s1", stage_name="Fetch", timestamp=_ts(3), duration_seconds=2.0))
    r.handle(StoryCompleted(story_id="s1", story_name="Pipeline", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=_ts(3)))

    total = _metric(registry, "narrative_stage_duration_seconds_sum", {"story_name": "Pipeline", "stage_name": "Fetch"})
    assert abs(total - 2.0) < 0.001


def test_multiple_stages_tracked_independently() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="A", timestamp=_ts(0)))
    r.handle(StageCompleted(story_id="s1", stage_name="A", timestamp=_ts(1), duration_seconds=1.0))
    r.handle(StageStarted(story_id="s1", stage_name="B", timestamp=_ts(1)))
    r.handle(StageCompleted(story_id="s1", stage_name="B", timestamp=_ts(4), duration_seconds=3.0))
    r.handle(StoryCompleted(story_id="s1", story_name="S", success=True, progress_percent=100, completed_stages=2, total_stages=2, timestamp=_ts(4)))

    sum_a = _metric(registry, "narrative_stage_duration_seconds_sum", {"story_name": "S", "stage_name": "A"})
    sum_b = _metric(registry, "narrative_stage_duration_seconds_sum", {"story_name": "S", "stage_name": "B"})
    assert abs(sum_a - 1.0) < 0.001
    assert abs(sum_b - 3.0) < 0.001


# ── failure counter ───────────────────────────────────────────────────────────

def test_failure_counter_increments() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_name="Job", error_type="RuntimeError"))
    r.handle(StoryCompleted(story_id="s1", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    count = _metric(registry, "narrative_story_failures_total", {"story_name": "Job", "error_type": "RuntimeError"})
    assert count == 1.0


def test_failure_counter_uses_error_type_label() -> None:
    r, registry = _make_renderer()

    r.handle(StoryStarted(story_id="s1", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_name="Job", error_type="TypeError"))
    r.handle(StoryCompleted(story_id="s1", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    r.handle(StoryStarted(story_id="s2", story_name="Job", timestamp=_ts(0)))
    r.handle(_failure(story_name="Job", error_type="ValueError"))
    r.handle(StoryCompleted(story_id="s2", story_name="Job", success=False, progress_percent=0, completed_stages=0, total_stages=1, timestamp=_ts(2)))

    type_err = _metric(registry, "narrative_story_failures_total", {"story_name": "Job", "error_type": "TypeError"})
    val_err = _metric(registry, "narrative_story_failures_total", {"story_name": "Job", "error_type": "ValueError"})
    assert type_err == 1.0
    assert val_err == 1.0


# ── custom registry ───────────────────────────────────────────────────────────

def test_custom_registry_isolates_metrics() -> None:
    reg1 = CollectorRegistry()
    reg2 = CollectorRegistry()
    r1 = PrometheusRenderer(registry=reg1)
    r2 = PrometheusRenderer(registry=reg2)

    r1.handle(StoryStarted(story_id="s1", story_name="A", timestamp=_ts(0)))
    r1.handle(StoryCompleted(story_id="s1", story_name="A", success=True, progress_percent=100, completed_stages=0, total_stages=0, timestamp=_ts(1)))

    # reg2 should have its own counter at 0 (or raise KeyError if never used)
    count_r1 = _metric(reg1, "narrative_story_total", {"story_name": "A", "success": "true"})
    assert count_r1 == 1.0
    with pytest.raises(KeyError):
        _metric(reg2, "narrative_story_total", {"story_name": "A", "success": "true"})


# ── missing dependency ────────────────────────────────────────────────────────

def test_missing_prometheus_raises_on_init(monkeypatch) -> None:
    import runtime_narrative.renderer.prometheus_renderer as mod
    monkeypatch.setattr(mod, "_PROMETHEUS_AVAILABLE", False)
    with pytest.raises(ImportError, match="prometheus-client"):
        PrometheusRenderer()
