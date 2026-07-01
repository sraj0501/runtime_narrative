"""Tests for issues #19–#24."""
from __future__ import annotations

import asyncio
import pytest

from tests.conftest import CapturingRenderer


# ── Issue #19 ─────────────────────────────────────────────────────────────────

def test_console_renderer_importable_from_top_level():
    from runtime_narrative import ConsoleRenderer
    assert callable(ConsoleRenderer)
    r = ConsoleRenderer()
    assert hasattr(r, "handle")


# ── Issue #20 ─────────────────────────────────────────────────────────────────

def test_stage_events_carry_story_name():
    from runtime_narrative import story, stage

    cap = CapturingRenderer()
    with story("My Story", renderers=[cap]):
        with stage("Step A"):
            pass

    started = next(e for e in cap.events if type(e).__name__ == "StageStarted")
    completed = next(e for e in cap.events if type(e).__name__ == "StageCompleted")
    assert started.story_name == "My Story"
    assert completed.story_name == "My Story"


def test_stage_events_carry_story_name_async():
    from runtime_narrative import story, stage

    async def run():
        cap = CapturingRenderer()
        async with story("Async Story", renderers=[cap]):
            async with stage("Async Step"):
                pass
        started = next(e for e in cap.events if type(e).__name__ == "StageStarted")
        completed = next(e for e in cap.events if type(e).__name__ == "StageCompleted")
        assert started.story_name == "Async Story"
        assert completed.story_name == "Async Story"

    asyncio.run(run())


# ── Issue #21 ─────────────────────────────────────────────────────────────────

def test_all_event_classes_exported():
    import runtime_narrative as rn
    for name in ("StoryStarted", "StageStarted", "StageCompleted", "FailureOccurred", "StoryCompleted", "LLMAnalysisReady"):
        assert hasattr(rn, name), f"{name} missing from runtime_narrative"


def test_event_union_type_exported():
    from runtime_narrative import Event  # noqa: F401 — must not raise


def test_events_are_typed_dataclasses():
    from runtime_narrative import StageStarted, StageCompleted
    from dataclasses import fields
    field_names = {f.name for f in fields(StageStarted)}
    assert "story_id" in field_names
    assert "stage_name" in field_names
    assert "story_name" in field_names
    field_names_c = {f.name for f in fields(StageCompleted)}
    assert "story_name" in field_names_c


# ── Issue #22 ─────────────────────────────────────────────────────────────────

def test_has_active_story_false_outside_context():
    from runtime_narrative import has_active_story
    assert has_active_story() is False


def test_has_active_story_true_inside_context():
    from runtime_narrative import story, has_active_story

    with story("probe", renderers=[CapturingRenderer()]):
        assert has_active_story() is True

    assert has_active_story() is False


def test_stage_optional_noop_outside_story():
    from runtime_narrative.stage import stage

    with stage("Safe step", optional=True) as rec:
        pass  # must not raise
    assert rec.name == "Safe step"


def test_stage_optional_still_works_inside_story():
    from runtime_narrative import story
    from runtime_narrative.stage import stage

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Normal", optional=True) as rec:
            pass
    assert rec.completed is True
    assert any(type(e).__name__ == "StageCompleted" for e in cap.events)


def test_stage_without_optional_still_raises_outside_story():
    from runtime_narrative.stage import stage

    with pytest.raises(RuntimeError, match="story"):
        with stage("Bad"):
            pass


# ── Issue #23 ─────────────────────────────────────────────────────────────────

def test_record_failure_emits_failure_occurred_without_suppressing():
    from runtime_narrative import story, stage

    async def run():
        cap = CapturingRenderer()
        exc = ValueError("saga boom")
        try:
            raise exc
        except ValueError:
            pass  # exc.__traceback__ is now populated

        async with story("Saga", renderers=[cap]) as runtime:
            async with stage("Step"):
                pass
            await runtime.record_failure(exc, stage_name="Rollback")

        kinds = [type(e).__name__ for e in cap.events]
        assert "FailureOccurred" in kinds
        failure = next(e for e in cap.events if type(e).__name__ == "FailureOccurred")
        assert failure.error_type == "ValueError"
        assert failure.stage_name == "Rollback"
        assert failure.story_name == "Saga"
        completed = next(e for e in cap.events if type(e).__name__ == "StoryCompleted")
        assert completed.success is True

    asyncio.run(run())


# ── Issue #24 ─────────────────────────────────────────────────────────────────

def test_middleware_skip_if_bypasses_story():
    pytest.importorskip("starlette")

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from runtime_narrative import RuntimeNarrativeMiddleware, stage

    cap = CapturingRenderer()

    async def handler(request):
        with stage("Work", optional=True):
            pass
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[Route("/skipped", endpoint=handler, methods=["GET"])],
        middleware=[
            Middleware(
                RuntimeNarrativeMiddleware,
                renderers=[cap],
                skip_if=lambda req: req.url.path == "/skipped",
            )
        ],
    )

    client = TestClient(app)
    client.get("/skipped")
    assert len(cap.events) == 0, "no events should be emitted for skipped requests"


def test_middleware_skip_if_does_not_skip_other_paths():
    pytest.importorskip("starlette")

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from runtime_narrative import RuntimeNarrativeMiddleware

    cap = CapturingRenderer()

    async def handler(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[Route("/instrumented", endpoint=handler, methods=["GET"])],
        middleware=[
            Middleware(
                RuntimeNarrativeMiddleware,
                renderers=[cap],
                skip_if=lambda req: req.url.path == "/health",
            )
        ],
    )

    client = TestClient(app)
    client.get("/instrumented")
    kinds = [type(e).__name__ for e in cap.events]
    assert "StoryStarted" in kinds
    assert "StoryCompleted" in kinds
