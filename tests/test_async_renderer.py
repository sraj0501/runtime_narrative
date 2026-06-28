from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import stage, story
from runtime_narrative.events import FailureOccurred, StoryCompleted, StoryStarted

from tests.conftest import AsyncCapturingRenderer


# ── T8: Async renderer receives awaited stage events ─────────────────────────

def test_async_renderer_receives_awaited_stage_events() -> None:
    """async def handle must be awaited for StageStarted and StageCompleted too."""
    cap = AsyncCapturingRenderer()

    async def run() -> None:
        async with story("S", renderers=[cap]):
            async with stage("Step A"):
                pass
            async with stage("Step B"):
                pass

    asyncio.run(run())

    kinds = [type(e).__name__ for e in cap.events]
    assert kinds == [
        "StoryStarted",
        "StageStarted",
        "StageCompleted",
        "StageStarted",
        "StageCompleted",
        "StoryCompleted",
    ]
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert stage_names == ["Step A", "Step A", "Step B", "Step B"]


def test_async_renderer_story_events_are_awaited_without_stages() -> None:
    """Failure and story boundaries use emit_async; async renderers work when no sync stage emit runs."""
    cap = AsyncCapturingRenderer()

    async def run() -> None:
        async with story("NoStages", renderers=[cap]):
            raise ValueError("direct")

    with pytest.raises(ValueError):
        asyncio.run(run())

    kinds = [type(e).__name__ for e in cap.events]
    assert kinds == ["StoryStarted", "FailureOccurred", "StoryCompleted"]
    assert isinstance(cap.events[0], StoryStarted)
    assert isinstance(cap.events[1], FailureOccurred)
    assert isinstance(cap.events[2], StoryCompleted)
