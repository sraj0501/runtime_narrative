from __future__ import annotations

import asyncio
from datetime import datetime

from runtime_narrative.events import StoryStarted
from runtime_narrative.renderer.filter_renderer import FilteredRenderer

from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


def _story_started(name: str) -> StoryStarted:
    return StoryStarted(story_id="s1", story_name=name, timestamp=datetime(2024, 6, 1))


def test_matching_event_is_forwarded() -> None:
    cap = CapturingRenderer()
    r = FilteredRenderer(lambda e: e.story_name.startswith("GET "), cap)
    r.handle(_story_started("GET /orders"))
    assert len(cap.events) == 1


def test_non_matching_event_is_dropped() -> None:
    cap = CapturingRenderer()
    r = FilteredRenderer(lambda e: e.story_name.startswith("GET "), cap)
    r.handle(_story_started("POST /orders"))
    assert cap.events == []


def test_two_filtered_renderers_split_by_predicate() -> None:
    get_cap = CapturingRenderer()
    other_cap = CapturingRenderer()
    renderers = [
        FilteredRenderer(lambda e: e.story_name.startswith("GET "), get_cap),
        FilteredRenderer(lambda e: not e.story_name.startswith("GET "), other_cap),
    ]
    for r in renderers:
        r.handle(_story_started("GET /orders"))
        r.handle(_story_started("POST /orders"))

    assert [e.story_name for e in get_cap.events] == ["GET /orders"]
    assert [e.story_name for e in other_cap.events] == ["POST /orders"]


def test_wraps_async_renderer_and_mirrors_coroutine_handle() -> None:
    cap = AsyncCapturingRenderer()
    r = FilteredRenderer(lambda e: True, cap)

    import inspect
    assert inspect.iscoroutinefunction(r.handle)

    asyncio.run(r.handle(_story_started("Any")))
    assert len(cap.events) == 1


def test_async_wrapped_renderer_respects_predicate() -> None:
    cap = AsyncCapturingRenderer()
    r = FilteredRenderer(lambda e: e.story_name == "Match", cap)

    asyncio.run(r.handle(_story_started("No Match")))
    assert cap.events == []
    asyncio.run(r.handle(_story_started("Match")))
    assert len(cap.events) == 1
