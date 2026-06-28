from __future__ import annotations

from datetime import datetime

import pytest
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor

from runtime_narrative.events import (
    FailureOccurred,
    LLMAnalysisReady,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.otel_log_renderer import OtelLogRenderer


def _make_log_provider():
    exporter = InMemoryLogExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
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


def test_story_started_emits_info_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="Load Data", timestamp=_ts(0)))

    logs = exporter.get_finished_logs()
    assert len(logs) == 1
    record = logs[0].log_record
    assert record.severity_number == SeverityNumber.INFO
    assert "Story started" in record.body
    assert record.attributes["narrative.story_name"] == "Load Data"


def test_stage_started_emits_debug_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Fetch", timestamp=_ts(1)))

    logs = exporter.get_finished_logs()
    assert len(logs) == 2
    record = logs[1].log_record
    assert record.severity_number == SeverityNumber.DEBUG
    assert "Stage started" in record.body
    assert record.attributes["narrative.stage_name"] == "Fetch"


def test_stage_completed_emits_debug_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Fetch", timestamp=_ts(1)))
    r.handle(StageCompleted(story_id="s1", stage_name="Fetch", timestamp=_ts(2), duration_seconds=1.0))

    logs = exporter.get_finished_logs()
    assert len(logs) == 3
    record = logs[2].log_record
    assert record.severity_number == SeverityNumber.DEBUG
    assert "Stage completed" in record.body
    assert "narrative.duration_seconds" in record.attributes


def test_failure_occurred_emits_error_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StageStarted(story_id="s1", stage_name="Step", timestamp=_ts(1)))
    r.handle(_failure())

    logs = exporter.get_finished_logs()
    record = logs[2].log_record
    assert record.severity_number == SeverityNumber.ERROR
    assert record.body == "bad value"
    attrs = record.attributes
    assert attrs["error.type"] == "ValueError"
    assert attrs["error.message"] == "bad value"
    assert attrs["code.filepath"] == "app.py"
    assert attrs["code.lineno"] == 42
    assert attrs["code.function"] == "do_thing"


def test_failure_has_stack_trace_attr() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(_failure(traceback_text="Traceback..."))

    logs = exporter.get_finished_logs()
    record = logs[0].log_record
    assert "error.stack_trace" in record.attributes
    assert record.attributes["error.stack_trace"] == "Traceback..."


def test_llm_analysis_ready_emits_info_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(LLMAnalysisReady(
        story_id="s1",
        story_name="S",
        stage_name="Step",
        llm_analysis="Check line 47",
        timestamp=_ts(1),
    ))

    logs = exporter.get_finished_logs()
    assert len(logs) == 2
    record = logs[1].log_record
    assert record.severity_number == SeverityNumber.INFO
    assert "LLM analysis ready" in record.body
    assert record.attributes["narrative.llm_analysis"] == "Check line 47"


def test_story_completed_emits_info_log() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(StoryCompleted(
        story_id="s1",
        story_name="S",
        success=True,
        progress_percent=100,
        completed_stages=1,
        total_stages=1,
        timestamp=_ts(1),
    ))

    logs = exporter.get_finished_logs()
    assert len(logs) == 2
    record = logs[1].log_record
    assert record.severity_number == SeverityNumber.INFO
    assert "Story completed" in record.body
    assert record.attributes["narrative.success"] is True


def test_story_completed_failure_path() -> None:
    exporter, provider = _make_log_provider()
    r = OtelLogRenderer(logger_provider=provider)

    r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=_ts(0)))
    r.handle(_failure())
    r.handle(StoryCompleted(
        story_id="s1",
        story_name="S",
        success=False,
        progress_percent=0,
        completed_stages=0,
        total_stages=1,
        timestamp=_ts(2),
    ))

    logs = exporter.get_finished_logs()
    record = logs[2].log_record
    assert record.severity_number == SeverityNumber.INFO
    assert record.attributes["narrative.success"] is False


def test_missing_dep_raises_import_error(monkeypatch) -> None:
    import runtime_narrative.renderer.otel_log_renderer as mod
    monkeypatch.setattr(mod, "_OTEL_LOGS_AVAILABLE", False)
    with pytest.raises(ImportError, match="opentelemetry"):
        OtelLogRenderer()
