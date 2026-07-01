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


def test_renderer_unicode_glyphs_on_unicode_terminal(monkeypatch):
    monkeypatch.setattr(console_mod, "_stdout_supports_unicode", lambda: True)
    r = ConsoleRenderer()
    assert r._glyph_arrow == "▶"
    assert r._glyph_check == "✔"
    assert r._glyph_cross == "❌"


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
