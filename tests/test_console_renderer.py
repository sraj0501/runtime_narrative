from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import runtime_narrative.renderer.console as console_mod
from runtime_narrative.events import (
    FailureOccurred,
    LogRecorded,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.console import ConsoleRenderer, _short_id, _stdout_supports_unicode


# ── T1: Unicode detection and glyph selection ─────────────────────────────────

def test_unicode_detection_false_for_cp1252(monkeypatch):
    mock = MagicMock()
    mock.encoding = "cp1252"
    monkeypatch.setattr(sys, "stdout", mock)
    assert _stdout_supports_unicode() is False


def test_unicode_detection_true_for_utf8(monkeypatch):
    mock = MagicMock()
    mock.encoding = "utf-8"
    monkeypatch.setattr(sys, "stdout", mock)
    assert _stdout_supports_unicode() is True


def test_renderer_ascii_glyphs_on_non_unicode_terminal(monkeypatch):
    monkeypatch.setattr(console_mod, "_stdout_supports_unicode", lambda: False)
    r = ConsoleRenderer()
    assert r._glyph_arrow == ">"
    assert r._glyph_check == "[ok]"
    assert r._glyph_cross == "[FAIL]"
    assert r._glyph_dash == "-"


def test_renderer_unicode_glyphs_on_unicode_terminal(monkeypatch):
    monkeypatch.setattr(console_mod, "_stdout_supports_unicode", lambda: True)
    r = ConsoleRenderer()
    assert r._glyph_arrow == "▶"
    assert r._glyph_check == "✔"
    assert r._glyph_cross == "❌"
    assert r._glyph_dash == "—"


def test_rich_locals_line_uses_ascii_dash_on_non_unicode_terminal(monkeypatch, capsys):
    """The 'frame_N — file:line in func' locals heading must go through the same
    ASCII-fallback path as the other glyphs, not a hardcoded em-dash that would
    degrade to a '?' replacement character on a non-UTF-8 stream."""
    monkeypatch.setattr(console_mod, "_stdout_supports_unicode", lambda: False)
    r = ConsoleRenderer()
    event = FailureOccurred(
        story_id="sid", story_name="S", stage_name="St",
        error_type="TypeError", error_message="m", filename="f.py", lineno=1,
        function="fn", source_line="raise TypeError", exception_chain="TypeError: m",
        exact_cause="because", llm_analysis=None, stage_timeline="x",
        progress_percent=0, completed_stages=0, total_stages=1,
        timestamp=datetime(2024, 1, 1),
        diagnostics_mode="rich", primary_frame_reason="innermost_app",
        stack_frames=[], source_snippet=None, compressed_stack_summary="",
        hidden_frame_count=0, traceback_truncated=False,
        locals_by_frame={"frame_0": {"filename": "f.py", "lineno": 1, "function": "fn", "locals": {"x": "1"}}},
        redaction_removed_keys=0,
        traceback_text="Traceback...",
    )
    r.handle(event)
    out = capsys.readouterr().out
    assert "frame_0 - f.py:1 in fn" in out
    assert "—" not in out


def test_secho_survives_unicode_encode_error_from_typer(monkeypatch):
    """_secho catches UnicodeEncodeError from typer.secho and retries with lossy encoding."""
    secho_calls: list[str] = []

    def fake_secho(text, **kwargs):
        secho_calls.append(text)
        if "▶" in text:
            raise UnicodeEncodeError("cp1252", text, 0, 1, "ordinal not in range")

    class FakeTyper:
        colors = MagicMock()
        secho = staticmethod(fake_secho)

    mock_stdout = MagicMock()
    mock_stdout.encoding = "cp1252"
    monkeypatch.setattr(sys, "stdout", mock_stdout)
    monkeypatch.setattr(console_mod, "typer", FakeTyper)

    r = ConsoleRenderer()
    r._secho("▶ Story started")  # directly invoke _secho with a problematic character

    # First call raises, second call is the lossy-encoded retry
    assert len(secho_calls) == 2
    assert "▶" not in secho_calls[1]


# ── T7: ConsoleRenderer works when typer is None ──────────────────────────────

def test_all_event_types_render_without_typer(monkeypatch, capsys):
    monkeypatch.setattr(console_mod, "typer", None)
    ts = datetime(2024, 6, 1)
    r = ConsoleRenderer()

    r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=ts))
    r.handle(StageStarted(story_id="s1", stage_name="Step A", timestamp=ts))
    r.handle(StageCompleted(story_id="s1", stage_name="Step A", duration_seconds=0.05, timestamp=ts))
    r.handle(StoryCompleted(
        story_id="s1", story_name="My Story", success=True,
        progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts,
    ))

    out = capsys.readouterr().out
    assert "My Story" in out
    assert "Step A" in out
    assert "SUCCESS" in out


def test_story_completed_with_outcome_renders_combined_line(monkeypatch, capsys):
    monkeypatch.setattr(console_mod, "typer", None)
    ts = datetime(2024, 6, 1)
    r = ConsoleRenderer()

    r.handle(StoryCompleted(
        story_id="d7678e", story_name="GET /api/call", success=True,
        progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts,
        duration_seconds=0.023, outcome="200 OK",
    ))

    out = capsys.readouterr().out
    # One self-contained line: name, state, and HTTP outcome together.
    line = next(l for l in out.splitlines() if "Story ended" in l)
    assert "GET /api/call" in line
    assert "SUCCESS" in line
    assert "200 OK" in line


def test_story_completed_without_outcome_keeps_legacy_line(monkeypatch, capsys):
    monkeypatch.setattr(console_mod, "typer", None)
    ts = datetime(2024, 6, 1)
    r = ConsoleRenderer()

    r.handle(StoryCompleted(
        story_id="s1", story_name="My Story", success=True,
        progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts,
        duration_seconds=0.023,
    ))

    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "Story ended" in l)
    assert "My Story" not in line
    assert "SUCCESS (0.023s)" in line


def test_failure_event_renders_without_typer(monkeypatch, capsys):
    monkeypatch.setattr(console_mod, "typer", None)

    r = ConsoleRenderer()
    event = FailureOccurred(
        story_id="s1", story_name="S", stage_name="St",
        error_type="ValueError", error_message="bad input",
        filename="app.py", lineno=12, function="do_it",
        source_line="raise ValueError('bad input')",
        exception_chain="ValueError: bad input",
        exact_cause="bad input",
        llm_analysis=None,
        stage_timeline="St=failed (0.001s)",
        progress_percent=50, completed_stages=1, total_stages=2,
        timestamp=datetime(2024, 6, 1),
        traceback_text="Traceback...",
    )
    r.handle(event)
    out = capsys.readouterr().out
    assert "Failure" in out
    assert "ValueError" in out
    assert "bad input" in out


# ── short-id tag + LogRecorded rendering ─────────────────────────────────────

def test_short_id_uses_first_six_chars_without_dashes() -> None:
    assert _short_id("abcd1234-ef56-...") == "abcd12"
    assert _short_id(None) == "------"
    assert _short_id("") == "------"


def test_story_started_line_includes_short_id_tag(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    r.handle(StoryStarted(story_id="abcdef1234567890", story_name="S", timestamp=datetime(2024, 6, 1)))
    out = capsys.readouterr().out
    assert "[abcdef]" in out


def test_log_recorded_renders_with_short_id_and_stage(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    monkeypatch.setattr(console_mod, "structlog", None)
    r = ConsoleRenderer()
    event = LogRecorded(
        story_id="abcdef1234567890",
        story_name="API",
        root_story_id="abcdef1234567890",
        stage_name="Call DB",
        level="WARNING",
        logger_name="myapp.db",
        message="slow query",
        timestamp=datetime(2024, 6, 1),
    )
    r.handle(event)
    out = capsys.readouterr().out
    assert "[abcdef]" in out
    assert "WARNING" in out
    assert "[Call DB]" in out
    assert "myapp.db" in out
    assert "slow query" in out


def test_log_recorded_includes_exc_text_when_present(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    event = LogRecorded(
        story_id="s1", story_name="API", root_story_id="s1", stage_name="",
        level="ERROR", logger_name="myapp", message="failed",
        timestamp=datetime(2024, 6, 1), exc_text="Traceback...\nValueError: boom",
    )
    r.handle(event)
    out = capsys.readouterr().out
    assert "ValueError: boom" in out


def test_nested_stage_and_substory_lines_are_indented(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    ts = datetime(2024, 6, 1)

    r.handle(StoryStarted(story_id="api", story_name="API", timestamp=ts))
    r.handle(StageStarted(story_id="api", stage_name="Persist Order", timestamp=ts))
    r.handle(StoryStarted(story_id="db", story_name="DB", timestamp=ts, parent_story_id="api", root_story_id="api"))
    r.handle(StageStarted(story_id="db", stage_name="Execute Query", timestamp=ts, root_story_id="api"))
    r.handle(StageCompleted(story_id="db", stage_name="Execute Query", duration_seconds=0.1, timestamp=ts, root_story_id="api"))
    r.handle(StoryCompleted(story_id="db", story_name="DB", success=True, progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts, parent_story_id="api", root_story_id="api"))
    r.handle(StageCompleted(story_id="api", stage_name="Persist Order", duration_seconds=0.2, timestamp=ts))
    r.handle(StoryCompleted(story_id="api", story_name="API", success=True, progress_percent=1, completed_stages=1, total_stages=1, timestamp=ts))

    lines = capsys.readouterr().out.splitlines()
    indent_of = {line.strip(): len(line) - len(line.lstrip(" ")) for line in lines if line.strip()}

    story_line = next(l for l in indent_of if "Story started: API" in l)
    stage_line = next(l for l in indent_of if "Stage started: Persist Order" in l)
    substory_line = next(l for l in indent_of if "Story started: DB" in l)
    substage_line = next(l for l in indent_of if "Stage started: Execute Query" in l)

    assert indent_of[story_line] == 0
    assert indent_of[stage_line] > indent_of[story_line]
    assert indent_of[substory_line] > indent_of[stage_line]
    assert indent_of[substage_line] > indent_of[substory_line]


# ── structured log rendering (structlog integration, level_icons, fields) ────

def _log_event(**overrides) -> LogRecorded:
    defaults = dict(
        story_id="s1", story_name="API", root_story_id="s1", stage_name="Call DB",
        level="WARNING", logger_name="myapp.db", message="slow query",
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
    )
    defaults.update(overrides)
    return LogRecorded(**defaults)


def test_log_recorded_falls_back_to_plain_style_without_structlog(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    monkeypatch.setattr(console_mod, "structlog", None)
    r = ConsoleRenderer()
    r.handle(_log_event(fields={"order_id": "ORD-42"}))
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "slow query" in out
    assert "order_id='ORD-42'" in out


def test_log_recorded_uses_structlog_default_style_when_available(monkeypatch, capsys) -> None:
    pytest.importorskip("structlog")
    r = ConsoleRenderer()
    r.handle(_log_event(fields={"order_id": "ORD-42"}))
    out = capsys.readouterr().out
    assert "slow query" in out
    assert "order_id" in out
    assert "ORD-42" in out
    assert "warning" in out.lower()


def test_log_recorded_does_not_duplicate_timestamp_with_structlog(monkeypatch, capsys) -> None:
    pytest.importorskip("structlog")
    r = ConsoleRenderer()
    r.handle(_log_event())
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "slow query" in l)
    # The story tag ("2024-06-01 12:00:00.000 [......]") already carries the
    # timestamp; structlog's own ConsoleRenderer must not print a second one
    # (issue #41).
    assert line.count("2024-06-01") == 1


def test_level_icons_prepend_to_message(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    monkeypatch.setattr(console_mod, "structlog", None)
    r = ConsoleRenderer(level_icons={"warning": "!! "})
    r.handle(_log_event())
    out = capsys.readouterr().out
    assert "!! slow query" in out


def test_custom_log_renderer_is_used_verbatim(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    calls = []

    def fake_renderer(logger, name, event_dict):
        calls.append(event_dict)
        return f"CUSTOM: {event_dict['event']}"

    r = ConsoleRenderer(log_renderer=fake_renderer)
    r.handle(_log_event())
    out = capsys.readouterr().out
    assert "CUSTOM: slow query" in out
    assert len(calls) == 1
    assert calls[0]["stage"] == "Call DB"


def test_log_recorded_renders_exc_text_after_structured_line(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    monkeypatch.setattr(console_mod, "structlog", None)
    r = ConsoleRenderer()
    r.handle(_log_event(level="ERROR", exc_text="Traceback...\nValueError: boom"))
    out = capsys.readouterr().out
    assert "ValueError: boom" in out


# ── file output (`output=`) ────────────────────────────────────────────────

def test_output_param_writes_to_file_instead_of_stdout(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    log_path = tmp_path / "app.log"
    ts = datetime(2024, 6, 1)

    with open(log_path, "w", encoding="utf-8") as f:
        r = ConsoleRenderer(output=f)
        r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=ts))
        r.handle(StoryCompleted(
            story_id="s1", story_name="My Story", success=True,
            progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts,
        ))

    # Nothing leaked to stdout ...
    assert capsys.readouterr().out == ""
    # ... and everything landed in the file.
    contents = log_path.read_text(encoding="utf-8")
    assert "My Story" in contents
    assert "SUCCESS" in contents


def test_output_param_flushes_after_every_line(monkeypatch, tmp_path) -> None:
    """Output must be visible on disk immediately, not just after the file is closed,
    so a log file reflects state up to the moment of a crash."""
    monkeypatch.setattr(console_mod, "typer", None)
    log_path = tmp_path / "app.log"
    ts = datetime(2024, 6, 1)

    f = open(log_path, "w", encoding="utf-8")
    try:
        r = ConsoleRenderer(output=f)
        r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=ts))
        # Read the file via a second handle while the writer is still open.
        contents = log_path.read_text(encoding="utf-8")
        assert "My Story" in contents
    finally:
        f.close()


def test_output_param_defaults_to_stdout_when_omitted(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=datetime(2024, 6, 1)))
    out = capsys.readouterr().out
    assert "My Story" in out


def test_timestamp_appears_on_every_line(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    ts = datetime(2026, 7, 3, 12, 3, 41, 208000)

    r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=ts))
    r.handle(StageStarted(story_id="s1", stage_name="Step A", timestamp=ts))
    r.handle(StageCompleted(story_id="s1", stage_name="Step A", duration_seconds=0.05, timestamp=ts))
    r.handle(StoryCompleted(
        story_id="s1", story_name="My Story", success=True,
        progress_percent=100, completed_stages=1, total_stages=1, timestamp=ts,
    ))

    out = capsys.readouterr().out
    expected_ts = "2026-07-03 12:03:41.208"
    # Every rendered line should carry the same timestamp prefix.
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines
    assert all(expected_ts in l for l in lines)


def test_module_shown_on_story_started_when_present(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    r.handle(StoryStarted(
        story_id="s1", story_name="My Story", timestamp=datetime(2024, 6, 1), module="app.routes.upload",
    ))
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "Story started" in l)
    assert "(app.routes.upload)" in line


def test_module_omitted_when_empty(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    r.handle(StoryStarted(story_id="s1", story_name="My Story", timestamp=datetime(2024, 6, 1)))
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "Story started" in l)
    assert "(" not in line


def test_stage_module_tag_shown_only_on_change(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    ts = datetime(2024, 6, 1)

    r.handle(StoryStarted(story_id="s1", story_name="Process Upload", timestamp=ts, module="app.upload"))
    r.handle(StageStarted(story_id="s1", stage_name="Validate", timestamp=ts, module="app.validators"))
    r.handle(StageStarted(story_id="s1", stage_name="Validate Again", timestamp=ts, module="app.validators"))
    r.handle(StageStarted(story_id="s1", stage_name="Persist", timestamp=ts, module="app.db"))

    out = capsys.readouterr().out
    lines = out.splitlines()
    validate_line = next(l for l in lines if "Stage started: Validate " in l or l.endswith("Validate"))
    validate_again_line = next(l for l in lines if "Validate Again" in l)
    persist_line = next(l for l in lines if "Persist" in l)

    assert "(app.validators)" in validate_line
    # Same module as the previous stage -- tag suppressed to avoid repetition.
    assert "(app.validators)" not in validate_again_line
    # Different module -- tag shown again.
    assert "(app.db)" in persist_line


def test_last_module_state_cleared_on_story_completed(monkeypatch, capsys) -> None:
    monkeypatch.setattr(console_mod, "typer", None)
    r = ConsoleRenderer()
    ts = datetime(2024, 6, 1)

    r.handle(StoryStarted(story_id="s1", story_name="First", timestamp=ts, module="app.a"))
    r.handle(StoryCompleted(
        story_id="s1", story_name="First", success=True,
        progress_percent=100, completed_stages=0, total_stages=0, timestamp=ts,
    ))
    assert "s1" not in r._last_module

    # A new story reusing the same story_id (unlikely in practice, but the
    # renderer should not carry stale module state across it): its own module
    # differs from the first stage's module, so the stage tag must still show
    # -- it would be wrongly suppressed if leftover state from the completed
    # "First" story (also module="app.a") were still sitting in _last_module.
    r.handle(StoryStarted(story_id="s1", story_name="Second", timestamp=ts, module=""))
    r.handle(StageStarted(story_id="s1", stage_name="Step", timestamp=ts, module="app.a"))
    out = capsys.readouterr().out
    step_line = next(l for l in out.splitlines() if "Stage started: Step" in l)
    assert "(app.a)" in step_line


def test_unicode_glyphs_selected_per_output_stream_encoding(monkeypatch, tmp_path) -> None:
    """A file opened with an encoding that can't represent the glyphs falls back to
    ASCII, independent of whatever sys.stdout supports."""
    monkeypatch.setattr(console_mod, "typer", None)
    monkeypatch.setattr(console_mod, "_stdout_supports_unicode", lambda: True)
    log_path = tmp_path / "app.log"

    with open(log_path, "w", encoding="cp1252") as f:
        r = ConsoleRenderer(output=f)
        assert r._glyph_arrow == ">"
        assert r._glyph_check == "[ok]"
        assert r._glyph_cross == "[FAIL]"
