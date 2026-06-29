from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from runtime_narrative import story, stage
from runtime_narrative.renderer.html_renderer import HtmlReportRenderer


def _run_story(path: Path, *, fail: bool = False) -> None:
    renderer = HtmlReportRenderer(path)
    with story("Test Pipeline", renderers=[renderer]):
        with stage("Load Data"):
            pass
        with stage("Insert Records"):
            if fail:
                raise ValueError("duplicate key")


def test_html_file_is_written(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    _run_story(p)
    assert p.exists()
    assert p.stat().st_size > 0


def test_html_contains_story_name(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    _run_story(p)
    content = p.read_text(encoding="utf-8")
    assert "Test Pipeline" in content


def test_html_contains_stage_names(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    _run_story(p)
    content = p.read_text(encoding="utf-8")
    assert "Load Data" in content
    assert "Insert Records" in content


def test_html_success_badge(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    _run_story(p)
    content = p.read_text(encoding="utf-8")
    assert "SUCCESS" in content
    assert "badge-success" in content


def test_html_failure_badge(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    with pytest.raises(ValueError):
        _run_story(p, fail=True)
    content = p.read_text(encoding="utf-8")
    assert "FAILED" in content
    assert "badge-fail" in content


def test_html_failure_detail(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    with pytest.raises(ValueError):
        _run_story(p, fail=True)
    content = p.read_text(encoding="utf-8")
    assert "ValueError" in content
    assert "duplicate key" in content


def test_html_is_self_contained(tmp_path: Path) -> None:
    p = tmp_path / "report.html"
    _run_story(p)
    content = p.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "<style>" in content
    assert 'src="' not in content
    assert 'href="' not in content


def test_html_async_story(tmp_path: Path) -> None:
    p = tmp_path / "report.html"

    async def run() -> None:
        async with story("Async Pipeline", renderers=[HtmlReportRenderer(p)]):
            async with stage("Fetch"):
                pass

    asyncio.run(run())
    content = p.read_text(encoding="utf-8")
    assert "Async Pipeline" in content
    assert "Fetch" in content
