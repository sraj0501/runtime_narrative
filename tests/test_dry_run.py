from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import story, stage
from tests.conftest import CapturingRenderer


def _make_renderer() -> CapturingRenderer:
    return CapturingRenderer()


def test_dry_run_all_stages_complete() -> None:
    renderer = _make_renderer()

    def body_raises() -> None:
        pass

    with story("s", dry_run=True, renderers=[renderer]):
        with stage("Load"):
            raise ValueError("expensive operation skipped")
        with stage("Insert"):
            raise RuntimeError("db write skipped")

    completed = {e.stage_name for e in renderer.events if type(e).__name__ == "StageCompleted"}
    assert "Load" in completed
    assert "Insert" in completed


def test_dry_run_story_completes_as_success() -> None:
    renderer = _make_renderer()

    with story("s", dry_run=True, renderers=[renderer]):
        with stage("Load"):
            raise ValueError("boom")

    completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert completed.success is True


def test_dry_run_no_failure_occurred_event() -> None:
    renderer = _make_renderer()

    with story("s", dry_run=True, renderers=[renderer]):
        with stage("Broken"):
            raise RuntimeError("should be suppressed")

    event_types = {type(e).__name__ for e in renderer.events}
    assert "FailureOccurred" not in event_types


def test_dry_run_does_not_suppress_without_flag() -> None:
    renderer = _make_renderer()

    with pytest.raises(ValueError):
        with story("s", renderers=[renderer]):
            with stage("Load"):
                raise ValueError("not suppressed")


def test_dry_run_false_by_default() -> None:
    from runtime_narrative.story import StoryRuntime
    rt = StoryRuntime(name="test")
    assert rt.dry_run is False


def test_dry_run_stages_emit_started_and_completed() -> None:
    renderer = _make_renderer()

    with story("s", dry_run=True, renderers=[renderer]):
        with stage("Step A"):
            raise KeyError("skip")
        with stage("Step B"):
            pass

    event_types = [type(e).__name__ for e in renderer.events]
    assert event_types.count("StageStarted") == 2
    assert event_types.count("StageCompleted") == 2


def test_dry_run_async() -> None:
    renderer = _make_renderer()

    async def run() -> None:
        async with story("s", dry_run=True, renderers=[renderer]):
            async with stage("Fetch"):
                raise IOError("network unavailable")
            async with stage("Save"):
                raise RuntimeError("db unavailable")

    asyncio.run(run())

    completed = {e.stage_name for e in renderer.events if type(e).__name__ == "StageCompleted"}
    assert "Fetch" in completed
    assert "Save" in completed

    story_completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert story_completed.success is True


def test_dry_run_with_story_recorder() -> None:
    from runtime_narrative.testing import StoryRecorder

    with StoryRecorder("Pipeline", dry_run=True) as r:
        with stage("Load"):
            raise ValueError("skip expensive load")
        with stage("Validate"):
            raise RuntimeError("skip validation")
        with stage("Export"):
            pass

    r.assert_stages_completed(["Load", "Validate", "Export"])
    r.assert_no_failure()
