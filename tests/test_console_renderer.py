from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import runtime_narrative.renderer.console as console_mod
from runtime_narrative.events import (
    FailureOccurred,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.console import ConsoleRenderer, _stdout_supports_unicode


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
