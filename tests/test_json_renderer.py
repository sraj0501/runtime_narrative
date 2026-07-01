from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from io import StringIO

from runtime_narrative.events import FailureOccurred
from runtime_narrative.renderer.json_renderer import JsonRenderer, RotatingJsonRenderer


# ── T3: LLMAnalysisReady is serialised by JsonRenderer ───────────────────────

def test_json_renderer_handles_llm_analysis_ready() -> None:
    from runtime_narrative.events import LLMAnalysisReady

    buf = StringIO()
    r = JsonRenderer(output=buf)
    event = LLMAnalysisReady(
        story_id="sid",
        story_name="My Story",
        stage_name="Step",
        llm_analysis="check line 47",
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
    )
    r.handle(event)
    buf.seek(0)
    data = json.loads(buf.read())
    assert data["event"] == "LLMAnalysisReady"
    assert data["story_id"] == "sid"
    assert data["story_name"] == "My Story"
    assert data["stage_name"] == "Step"
    assert data["llm_analysis"] == "check line 47"
    assert "timestamp" in data


# ── RotatingJsonRenderer ──────────────────────────────────────────────────────

def test_rotating_renderer_writes_events_to_file() -> None:
    from runtime_narrative.events import StoryStarted

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "narrative.log")
        r = RotatingJsonRenderer(path)
        r.handle(StoryStarted(story_id="s1", story_name="S", timestamp=datetime(2024, 1, 1)))
        r._file.flush()
        with open(path) as f:
            data = json.loads(f.readline())
        r._file.close()  # release handle before Windows deletes the temp dir

    assert data["event"] == "StoryStarted"


def test_rotating_renderer_rotates_when_size_exceeded() -> None:
    from runtime_narrative.events import StoryStarted

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "narrative.log")
        r = RotatingJsonRenderer(path, max_bytes=1, backup_count=2)
        ts = datetime(2024, 1, 1)
        r.handle(StoryStarted(story_id="s1", story_name="A", timestamp=ts))
        r.handle(StoryStarted(story_id="s2", story_name="B", timestamp=ts))
        r._file.flush()
        rotated_exists = os.path.exists(path + ".1")
        r._file.close()  # release handle before Windows deletes the temp dir

    assert rotated_exists


def test_json_renderer_failure_includes_diagnostics_fields() -> None:
    buf = StringIO()
    r = JsonRenderer(output=buf)
    event = FailureOccurred(
        story_id="sid",
        story_name="S",
        stage_name="St",
        error_type="ValueError",
        error_message="m",
        filename="f.py",
        lineno=10,
        function="fn",
        source_line="raise ValueError",
        exception_chain="ValueError: m",
        exact_cause="because",
        llm_analysis=None,
        stage_timeline="x",
        progress_percent=0,
        completed_stages=0,
        total_stages=1,
        timestamp=datetime(2020, 1, 1, 12, 0, 0),
        traceback_text="Traceback...",
        diagnostics_mode="rich",
        primary_frame_reason="innermost_app",
        stack_frames=[{"index": 0, "filename": "f.py", "kind": "app", "is_primary": True}],
        source_snippet="> 10 | raise",
        compressed_stack_summary="1 app frame(s), 0 other",
        hidden_frame_count=0,
        traceback_truncated=False,
        locals_by_frame=None,
        redaction_removed_keys=0,
    )
    r.handle(event)
    buf.seek(0)
    data = json.loads(buf.read())
    assert data["event"] == "FailureOccurred"
    assert data["diagnostics_mode"] == "rich"
    assert data["primary_frame_reason"] == "innermost_app"
    assert data["stack_frames"][0]["kind"] == "app"
    assert data["traceback_text"] == "Traceback..."


def test_json_renderer_handles_log_recorded() -> None:
    from runtime_narrative.events import LogRecorded

    buf = StringIO()
    r = JsonRenderer(output=buf)
    event = LogRecorded(
        story_id="sid",
        story_name="API",
        root_story_id="sid",
        stage_name="Call DB",
        level="WARNING",
        logger_name="myapp.db",
        message="slow query",
        timestamp=datetime(2024, 6, 1),
    )
    r.handle(event)
    buf.seek(0)
    data = json.loads(buf.read())
    assert data["event"] == "LogRecorded"
    assert data["level"] == "WARNING"
    assert data["logger_name"] == "myapp.db"
    assert data["message"] == "slow query"
    assert data["stage_name"] == "Call DB"


def test_json_renderer_story_completed_includes_duration_and_parent_id() -> None:
    from runtime_narrative.events import StoryCompleted

    buf = StringIO()
    r = JsonRenderer(output=buf)
    event = StoryCompleted(
        story_id="s2", story_name="DB", success=True, progress_percent=100,
        completed_stages=1, total_stages=1, timestamp=datetime(2024, 6, 1),
        duration_seconds=0.42, parent_story_id="s1", root_story_id="s1",
    )
    r.handle(event)
    buf.seek(0)
    data = json.loads(buf.read())
    assert data["duration_seconds"] == 0.42
    assert data["parent_story_id"] == "s1"
    assert data["root_story_id"] == "s1"
