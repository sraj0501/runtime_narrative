from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import runtime_narrative.renderer_defaults as renderer_defaults_module
from runtime_narrative.events import StoryStarted
from runtime_narrative.renderer.console import ConsoleRenderer
from runtime_narrative.renderer.json_renderer import JsonRenderer
from runtime_narrative.renderer_defaults import default_renderers


def _tty_stdout() -> MagicMock:
    mock = MagicMock()
    mock.isatty.return_value = True
    mock.encoding = "utf-8"
    return mock


def _non_tty_stdout() -> MagicMock:
    mock = MagicMock()
    mock.isatty.return_value = False
    mock.encoding = "utf-8"
    return mock


# ── Base selection (no env vars) ──────────────────────────────────────────────

def test_tty_no_env_returns_console_renderer_only(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _tty_stdout())
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", raising=False)
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", raising=False)

    renderers = default_renderers()

    assert len(renderers) == 1
    assert isinstance(renderers[0], ConsoleRenderer)


def test_non_tty_no_env_returns_json_renderer_only(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _non_tty_stdout())
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", raising=False)
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", raising=False)

    renderers = default_renderers()

    assert len(renderers) == 1
    assert isinstance(renderers[0], JsonRenderer)


# ── RUNTIME_NARRATIVE_RICH_LOG_FILE ───────────────────────────────────────────

def test_non_tty_with_rich_log_file_adds_file_renderer_alongside_json(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_defaults_module, "_open_rich_log_files", {})
    monkeypatch.setattr(sys, "stdout", _non_tty_stdout())
    log_path = tmp_path / "narrative.log"
    monkeypatch.setenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", str(log_path))
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", raising=False)

    renderers = default_renderers()

    assert len(renderers) == 2
    assert isinstance(renderers[0], JsonRenderer)
    assert isinstance(renderers[1], ConsoleRenderer)

    event = StoryStarted(
        story_id="sid",
        story_name="My Rich Log Story",
        timestamp=datetime(2024, 1, 1),
    )
    for renderer in renderers:
        renderer.handle(event)

    contents = Path(log_path).read_text()
    assert "My Rich Log Story" in contents

    renderers[1]._output.close()  # release handle before tmp_path cleanup on Windows


def test_tty_with_rich_log_file_default_console_enabled_adds_both(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_defaults_module, "_open_rich_log_files", {})
    monkeypatch.setattr(sys, "stdout", _tty_stdout())
    log_path = tmp_path / "narrative.log"
    monkeypatch.setenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", str(log_path))
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", raising=False)

    renderers = default_renderers()

    assert len(renderers) == 2
    assert isinstance(renderers[0], ConsoleRenderer)
    assert isinstance(renderers[1], ConsoleRenderer)

    renderers[1]._output.close()  # release handle before tmp_path cleanup on Windows


def test_tty_with_rich_log_file_console_disabled_returns_file_only(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_defaults_module, "_open_rich_log_files", {})
    monkeypatch.setattr(sys, "stdout", _tty_stdout())
    log_path = tmp_path / "narrative.log"
    monkeypatch.setenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", str(log_path))
    monkeypatch.setenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", "0")

    renderers = default_renderers()

    assert len(renderers) == 1
    assert isinstance(renderers[0], ConsoleRenderer)
    assert renderers[0]._output is not sys.stdout

    renderers[0]._output.close()  # release handle before tmp_path cleanup on Windows


# ── File handle caching ───────────────────────────────────────────────────────

def test_repeated_calls_reuse_same_open_file_handle(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_defaults_module, "_open_rich_log_files", {})
    monkeypatch.setattr(sys, "stdout", _non_tty_stdout())
    log_path = tmp_path / "shared.log"
    monkeypatch.setenv("RUNTIME_NARRATIVE_RICH_LOG_FILE", str(log_path))
    monkeypatch.delenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", raising=False)

    first_renderers = default_renderers()
    second_renderers = default_renderers()

    first_file_renderer = first_renderers[1]
    second_file_renderer = second_renderers[1]
    assert isinstance(first_file_renderer, ConsoleRenderer)
    assert isinstance(second_file_renderer, ConsoleRenderer)
    assert first_file_renderer._output is second_file_renderer._output

    first_file_renderer._output.close()  # release handle before tmp_path cleanup on Windows
