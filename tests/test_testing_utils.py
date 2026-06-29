from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import stage
from runtime_narrative.testing import StoryRecorder


def _pipeline_ok() -> None:
    with stage("Load"):
        pass
    with stage("Validate"):
        pass
    with stage("Insert"):
        pass


def _pipeline_fail() -> None:
    with stage("Load"):
        pass
    with stage("Insert"):
        raise ValueError("duplicate key")


async def _async_pipeline_ok() -> None:
    async with stage("Fetch"):
        pass
    async with stage("Transform"):
        pass


def test_assert_stages_completed_pass() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    r.assert_stages_completed(["Load", "Validate", "Insert"])


def test_assert_stages_completed_fail() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    with pytest.raises(AssertionError, match="Expected stages not completed"):
        r.assert_stages_completed(["Load", "Validate", "Insert", "Missing"])


def test_assert_no_failure_pass() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    r.assert_no_failure()


def test_assert_no_failure_raises_on_failure() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    with pytest.raises(AssertionError, match="Expected no failure"):
        r.assert_no_failure()


def test_assert_stage_failed_correct_stage() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    r.assert_stage_failed("Insert")


def test_assert_stage_failed_with_error_type() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    r.assert_stage_failed("Insert", error_type="ValueError")


def test_assert_stage_failed_wrong_error_type() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    with pytest.raises(AssertionError, match="Expected error type"):
        r.assert_stage_failed("Insert", error_type="KeyError")


def test_assert_stage_failed_wrong_stage() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    with pytest.raises(AssertionError, match="failure occurred at"):
        r.assert_stage_failed("Load")


def test_assert_stage_failed_no_failure() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    with pytest.raises(AssertionError, match="no failure occurred"):
        r.assert_stage_failed("Load")


def test_assert_story_completed_success() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    r.assert_story_completed(success=True)


def test_assert_story_completed_failure() -> None:
    with pytest.raises(ValueError):
        with StoryRecorder("test") as r:
            _pipeline_fail()
    r.assert_story_completed(success=False)


def test_assert_story_completed_no_event() -> None:
    r = StoryRecorder("test")
    with pytest.raises(AssertionError, match="StoryCompleted"):
        r.assert_story_completed()


def test_events_exposed() -> None:
    with StoryRecorder("test") as r:
        _pipeline_ok()
    event_types = {type(e).__name__ for e in r.events}
    assert "StoryStarted" in event_types
    assert "StageCompleted" in event_types
    assert "StoryCompleted" in event_types


def test_async_recorder() -> None:
    async def run() -> StoryRecorder:
        async with StoryRecorder("async-test") as r:
            await _async_pipeline_ok()
        return r

    r = asyncio.run(run())
    r.assert_stages_completed(["Fetch", "Transform"])
    r.assert_no_failure()
