from __future__ import annotations

import asyncio

from runtime_narrative import stage, story
from runtime_narrative.events import StageCompleted, StageStarted
from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


def _stage_started(events, name: str) -> StageStarted:
    return next(e for e in events if isinstance(e, StageStarted) and e.stage_name == name)


def _stage_completed(events, name: str) -> StageCompleted:
    return next(e for e in events if isinstance(e, StageCompleted) and e.stage_name == name)


# ── stage_index ───────────────────────────────────────────────────────────────

def test_stage_index_increments_per_stage() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Alpha"):
            pass
        with stage("Beta"):
            pass
        with stage("Gamma"):
            pass

    assert _stage_started(cap.events, "Alpha").stage_index == 0
    assert _stage_started(cap.events, "Beta").stage_index == 1
    assert _stage_started(cap.events, "Gamma").stage_index == 2


def test_stage_index_on_completed_event() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("First"):
            pass
        with stage("Second"):
            pass

    assert _stage_completed(cap.events, "First").stage_index == 0
    assert _stage_completed(cap.events, "Second").stage_index == 1


# ── parent_stage_name ─────────────────────────────────────────────────────────

def test_top_level_stage_has_no_parent() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Root"):
            pass

    assert _stage_started(cap.events, "Root").parent_stage_name is None


def test_nested_stage_carries_parent_name() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Outer"):
            with stage("Inner"):
                pass

    inner_started = _stage_started(cap.events, "Inner")
    assert inner_started.parent_stage_name == "Outer"


def test_doubly_nested_stage_carries_immediate_parent() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("L1"):
            with stage("L2"):
                with stage("L3"):
                    pass

    assert _stage_started(cap.events, "L2").parent_stage_name == "L1"
    assert _stage_started(cap.events, "L3").parent_stage_name == "L2"


def test_sibling_stages_share_no_parent_relationship() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("A"):
            pass
        with stage("B"):
            pass

    assert _stage_started(cap.events, "A").parent_stage_name is None
    assert _stage_started(cap.events, "B").parent_stage_name is None


def test_parent_name_on_completed_event() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Parent"):
            with stage("Child"):
                pass

    assert _stage_completed(cap.events, "Child").parent_stage_name == "Parent"


# ── async path ────────────────────────────────────────────────────────────────

def test_async_stage_carries_index_and_parent() -> None:
    cap = AsyncCapturingRenderer()

    async def run():
        async with story("S", renderers=[cap]):
            async with stage("First"):
                async with stage("Nested"):
                    pass
            async with stage("Second"):
                pass

    asyncio.run(run())

    assert _stage_started(cap.events, "First").stage_index == 0
    assert _stage_started(cap.events, "First").parent_stage_name is None
    assert _stage_started(cap.events, "Nested").stage_index == 1
    assert _stage_started(cap.events, "Nested").parent_stage_name == "First"
    assert _stage_started(cap.events, "Second").stage_index == 2
    assert _stage_started(cap.events, "Second").parent_stage_name is None
