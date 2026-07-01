from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from runtime_narrative import stage, story
from runtime_narrative.events import FailureOccurred, StoryCompleted, StoryStarted
from runtime_narrative.story import StoryRuntime

from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


def test_sync_story_success_emits_started_and_completed() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        pass
    names = [e.__class__.__name__ for e in cap.events]
    assert names == ["StoryStarted", "StoryCompleted"]
    assert cap.events[-1].success is True


def test_sync_story_failure_emits_failure_with_diagnostics() -> None:
    cap = CapturingRenderer()
    with pytest.raises(ValueError):
        with story("S", renderers=[cap], failure_diagnostics="rich", runtime_environment="development"):
            with stage("Step"):
                x = 1
                raise ValueError("bad")

    names = [e.__class__.__name__ for e in cap.events]
    assert "StoryStarted" in names
    assert "FailureOccurred" in names
    assert names[-1] == "StoryCompleted"
    assert cap.events[-1].success is False

    fail = next(e for e in cap.events if isinstance(e, FailureOccurred))
    assert fail.error_type == "ValueError"
    assert fail.stage_name == "Step"
    assert fail.diagnostics_mode == "rich"
    assert fail.locals_by_frame is not None
    assert "frame_0" in fail.locals_by_frame


def test_sync_story_production_forces_lean() -> None:
    cap = CapturingRenderer()
    with pytest.raises(ValueError):
        with story(
            "S",
            renderers=[cap],
            runtime_environment="production",
            failure_diagnostics="rich",
        ):
            with stage("Step"):
                raise ValueError("x")

    fail = next(e for e in cap.events if isinstance(e, FailureOccurred))
    assert fail.diagnostics_mode == "lean"
    assert fail.locals_by_frame is None


def test_async_story_records_all_stage_events() -> None:
    # Stage lifecycle uses sync emit(); use a sync renderer. Async renderers are only
    # fully applied to events dispatched via emit_async (story enter/exit, failures).
    cap = CapturingRenderer()

    async def run() -> None:
        async with story("A", renderers=[cap]):
            async with stage("S"):
                pass

    asyncio.run(run())
    assert [e.__class__.__name__ for e in cap.events] == [
        "StoryStarted",
        "StageStarted",
        "StageCompleted",
        "StoryCompleted",
    ]


def test_async_story_failure_enriched_async_path() -> None:
    cap = CapturingRenderer()

    async def run() -> None:
        async with story("A", renderers=[cap], failure_diagnostics="lean"):
            async with stage("Do"):
                raise RuntimeError("async err")

    with pytest.raises(RuntimeError):
        asyncio.run(run())

    fail = next(e for e in cap.events if isinstance(e, FailureOccurred))
    assert fail.diagnostics_mode == "lean"
    assert fail.stack_frames
    assert fail.primary_frame_reason in ("innermost_app", "leaf", "innermost_non_stdlib")


# ── T2: Renderer exception isolation ─────────────────────────────────────────

def test_emit_renderer_exception_does_not_propagate(capsys) -> None:
    class BoomRenderer:
        def handle(self, event: object) -> None:
            raise RuntimeError("boom")

    cap = CapturingRenderer()
    runtime = StoryRuntime(name="S", renderers=[BoomRenderer(), cap])
    runtime.emit(StoryStarted(story_id="x", story_name="S", timestamp=datetime.now()))

    assert len(cap.events) == 1
    err = capsys.readouterr().err
    assert "BoomRenderer" in err
    assert "RuntimeError" in err


def test_emit_async_renderer_exception_does_not_propagate(capsys) -> None:
    class AsyncBoomRenderer:
        async def handle(self, event: object) -> None:
            raise ValueError("async boom")

    cap = AsyncCapturingRenderer()
    runtime = StoryRuntime(name="S", renderers=[AsyncBoomRenderer(), cap])
    asyncio.run(runtime.emit_async(StoryStarted(story_id="x", story_name="S", timestamp=datetime.now())))

    assert len(cap.events) == 1
    err = capsys.readouterr().err
    assert "AsyncBoomRenderer" in err


# ── T10: Nested stories have independent ContextVar contexts ──────────────────

def test_nested_stories_inner_renderer_sees_only_inner_stages() -> None:
    outer_cap = CapturingRenderer()
    inner_cap = CapturingRenderer()

    with story("Outer", renderers=[outer_cap]):
        with stage("Before"):
            pass
        with story("Inner", renderers=[inner_cap]):
            with stage("Inner Step"):
                pass
        with stage("After"):
            pass

    inner_stage_names = [e.stage_name for e in inner_cap.events if hasattr(e, "stage_name")]
    assert "Inner Step" in inner_stage_names
    assert "Before" not in inner_stage_names
    assert "After" not in inner_stage_names


def test_nested_stories_outer_does_not_see_inner_stages() -> None:
    outer_cap = CapturingRenderer()
    inner_cap = CapturingRenderer()

    with story("Outer", renderers=[outer_cap]):
        with stage("Outer Step"):
            pass
        with story("Inner", renderers=[inner_cap]):
            with stage("Inner Step"):
                pass

    outer_stage_names = [e.stage_name for e in outer_cap.events if hasattr(e, "stage_name")]
    assert "Outer Step" in outer_stage_names
    assert "Inner Step" not in outer_stage_names


def test_nested_stories_context_restores_after_inner_exits() -> None:
    """After inner story exits, the outer story's context must be active again."""
    outer_cap = CapturingRenderer()

    with story("Outer", renderers=[outer_cap]) as outer_runtime:
        with story("Inner", renderers=[CapturingRenderer()]):
            pass
        # Stage registered after inner story exits must appear in outer timeline
        with stage("Post-inner Stage"):
            pass

    timeline = outer_runtime.build_stage_timeline()
    assert "Post-inner Stage" in timeline


# ── (existing test follows) ───────────────────────────────────────────────────

# ── Sub-story linkage (parent_story_id / root_story_id) ──────────────────────

def test_substory_gets_parent_and_root_story_id() -> None:
    cap = CapturingRenderer()

    with story("API", renderers=[cap]) as api_runtime:
        with story("DB") as db_runtime:
            pass

    assert db_runtime.parent_story_id == api_runtime.story_id
    assert db_runtime.root_story_id == api_runtime.story_id
    assert api_runtime.parent_story_id is None
    assert api_runtime.root_story_id == api_runtime.story_id

    started = [e for e in cap.events if e.__class__.__name__ == "StoryStarted"]
    db_started = next(e for e in started if e.story_name == "DB")
    assert db_started.parent_story_id == api_runtime.story_id
    assert db_started.root_story_id == api_runtime.story_id


def test_substory_three_levels_share_one_root() -> None:
    with story("Root") as root_runtime:
        with story("Mid") as mid_runtime:
            with story("Leaf") as leaf_runtime:
                pass

    assert mid_runtime.parent_story_id == root_runtime.story_id
    assert leaf_runtime.parent_story_id == mid_runtime.story_id
    assert mid_runtime.root_story_id == root_runtime.story_id
    assert leaf_runtime.root_story_id == root_runtime.story_id


def test_substory_inherits_renderers_and_diagnostics_when_not_given() -> None:
    cap = CapturingRenderer()

    with story("API", renderers=[cap], failure_diagnostics="rich") as api_runtime:
        with story("DB") as db_runtime:
            pass

    assert db_runtime.renderers == api_runtime.renderers
    assert db_runtime._diag_config is api_runtime._diag_config

    names = [e.__class__.__name__ for e in cap.events]
    # DB sub-story's own events reached the inherited (outer) renderer.
    assert names.count("StoryStarted") == 2
    assert names.count("StoryCompleted") == 2


def test_substory_explicit_renderers_override_inheritance() -> None:
    outer_cap = CapturingRenderer()
    inner_cap = CapturingRenderer()

    with story("API", renderers=[outer_cap]):
        with story("DB", renderers=[inner_cap]):
            pass

    assert len(inner_cap.events) == 2  # Started + Completed for "DB" only
    assert all(e.story_name == "DB" for e in inner_cap.events)


def test_story_completed_carries_duration_seconds() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        pass
    completed = next(e for e in cap.events if e.__class__.__name__ == "StoryCompleted")
    assert completed.duration_seconds >= 0.0


def test_background_analysis_emits_llm_ready() -> None:
    class QuickAnalyzer:
        async def analyze_failure_async(self, **kwargs: object) -> str:
            return "hint"

    cap = AsyncCapturingRenderer()

    async def run() -> None:
        with pytest.raises(ValueError):
            async with story(
                "Bg",
                renderers=[cap],
                failure_analyzer=QuickAnalyzer(),
                background_analysis=True,
            ):
                raise ValueError("fail")
        # Same loop: let the background task finish before run() tears down.
        await asyncio.sleep(0.2)

    asyncio.run(run())
    kinds = [type(e).__name__ for e in cap.events]
    assert "FailureOccurred" in kinds
    assert "StoryCompleted" in kinds
    assert "LLMAnalysisReady" in kinds
