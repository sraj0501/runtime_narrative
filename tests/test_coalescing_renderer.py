from __future__ import annotations

import asyncio
import inspect
from datetime import datetime

from runtime_narrative import story, stage
from runtime_narrative.events import (
    LogRecorded,
    StageCompleted,
    StageStarted,
    StoryCompleted,
)
from runtime_narrative.renderer.coalescing_renderer import CoalescingRenderer

from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


def _stage_started(
    story_id: str, stage_name: str, *, story_name: str = "Story"
) -> StageStarted:
    return StageStarted(
        story_id=story_id,
        stage_name=stage_name,
        timestamp=datetime(2024, 6, 1),
        story_name=story_name,
        root_story_id=story_id,
    )


def _stage_completed(
    story_id: str,
    stage_name: str,
    *,
    duration_seconds: float = 1.0,
    story_name: str = "Story",
) -> StageCompleted:
    return StageCompleted(
        story_id=story_id,
        stage_name=stage_name,
        timestamp=datetime(2024, 6, 1),
        duration_seconds=duration_seconds,
        story_name=story_name,
        root_story_id=story_id,
    )


def _story_completed(story_id: str, *, story_name: str = "Story") -> StoryCompleted:
    return StoryCompleted(
        story_id=story_id,
        story_name=story_name,
        success=True,
        progress_percent=100,
        completed_stages=1,
        total_stages=1,
        timestamp=datetime(2024, 6, 1),
        root_story_id=story_id,
    )


def test_within_threshold_nothing_suppressed() -> None:
    cap = CapturingRenderer()
    r = CoalescingRenderer(cap, threshold=2)

    for _ in range(2):
        r.handle(_stage_started("s1", "Poll"))
        r.handle(_stage_completed("s1", "Poll"))
    r.handle(_story_completed("s1"))

    assert len(cap.events) == 5
    assert not any(isinstance(e, LogRecorded) for e in cap.events)


def test_beyond_threshold_summary_emitted() -> None:
    cap = CapturingRenderer()
    r = CoalescingRenderer(cap, threshold=2)

    for _ in range(5):
        r.handle(_stage_started("s1", "Poll"))
        r.handle(_stage_completed("s1", "Poll", duration_seconds=1.0))
    r.handle(_story_completed("s1"))

    assert [type(e).__name__ for e in cap.events] == [
        "StageStarted",
        "StageCompleted",
        "StageStarted",
        "StageCompleted",
        "LogRecorded",
        "StoryCompleted",
    ]

    summary = cap.events[4]
    assert isinstance(summary, LogRecorded)
    assert "5 total" in summary.message
    assert "3 more time" in summary.message
    assert "5.000s" in summary.message


def test_run_broken_by_different_stage() -> None:
    cap = CapturingRenderer()
    r = CoalescingRenderer(cap, threshold=1)

    for _ in range(3):
        r.handle(_stage_started("s1", "A"))
        r.handle(_stage_completed("s1", "A"))
    r.handle(_stage_started("s1", "B"))

    names = [type(e).__name__ for e in cap.events]
    summary_index = next(
        i for i, e in enumerate(cap.events) if isinstance(e, LogRecorded)
    )
    b_started_index = next(
        i
        for i, e in enumerate(cap.events)
        if isinstance(e, StageStarted) and e.stage_name == "B"
    )
    assert summary_index < b_started_index

    summary = cap.events[summary_index]
    assert "A" in summary.message
    assert "3 total" in summary.message

    b_started = cap.events[b_started_index]
    assert b_started.stage_name == "B"


def test_two_independent_stories_do_not_interfere() -> None:
    cap = CapturingRenderer()
    r = CoalescingRenderer(cap, threshold=1)

    # Interleave s1/"Poll1" and s2/"Poll2", each exceeding threshold=1.
    for _ in range(3):
        r.handle(_stage_started("s1", "Poll1", story_name="Story1"))
        r.handle(_stage_completed("s1", "Poll1", story_name="Story1"))
        r.handle(_stage_started("s2", "Poll2", story_name="Story2"))
        r.handle(_stage_completed("s2", "Poll2", story_name="Story2"))

    r.handle(_story_completed("s1", story_name="Story1"))
    r.handle(_story_completed("s2", story_name="Story2"))

    summaries = [e for e in cap.events if isinstance(e, LogRecorded)]
    assert len(summaries) == 2

    s1_summary = next(s for s in summaries if s.story_id == "s1")
    s2_summary = next(s for s in summaries if s.story_id == "s2")

    assert "Poll1" in s1_summary.message
    assert "3 total" in s1_summary.message
    assert "Poll2" in s2_summary.message
    assert "3 total" in s2_summary.message


def test_async_wrapped_renderer() -> None:
    cap = AsyncCapturingRenderer()
    r = CoalescingRenderer(cap, threshold=2)

    assert inspect.iscoroutinefunction(r.handle)

    async def run() -> None:
        for _ in range(5):
            await r.handle(_stage_started("s1", "Poll"))
            await r.handle(_stage_completed("s1", "Poll", duration_seconds=1.0))
        await r.handle(_story_completed("s1"))

    asyncio.run(run())

    assert [type(e).__name__ for e in cap.events] == [
        "StageStarted",
        "StageCompleted",
        "StageStarted",
        "StageCompleted",
        "LogRecorded",
        "StoryCompleted",
    ]
    summary = cap.events[4]
    assert "5 total" in summary.message
    assert "3 more time" in summary.message
    assert "5.000s" in summary.message


def test_invalid_threshold_raises() -> None:
    try:
        CoalescingRenderer(CapturingRenderer(), threshold=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_integration_with_real_story_and_stage() -> None:
    cap = CapturingRenderer()
    with story("Process Upload", renderers=[CoalescingRenderer(cap, threshold=2)]):
        for _ in range(5):
            with stage("Check Pipeline Status"):
                pass

    summaries = [e for e in cap.events if isinstance(e, LogRecorded)]
    assert len(summaries) == 1
    assert "5 total" in summaries[0].message
