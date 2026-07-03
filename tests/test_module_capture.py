from __future__ import annotations

import asyncio

from runtime_narrative import runtime_narrative_stage, runtime_narrative_story, stage, story
from runtime_narrative.events import StageStarted, StoryStarted

from tests.conftest import CapturingRenderer

# This module's own __name__, used to assert on caller-frame auto-detection.
_THIS_MODULE = __name__


def test_story_auto_detects_caller_module() -> None:
    cap = CapturingRenderer()
    with story("Direct Story", renderers=[cap]):
        pass
    started = next(e for e in cap.events if isinstance(e, StoryStarted))
    assert started.module == _THIS_MODULE


def test_story_explicit_module_overrides_auto_detection() -> None:
    cap = CapturingRenderer()
    with story("Overridden Story", renderers=[cap], module="some.other.module"):
        pass
    started = next(e for e in cap.events if isinstance(e, StoryStarted))
    assert started.module == "some.other.module"


def test_stage_auto_detects_caller_module() -> None:
    cap = CapturingRenderer()
    with story("Story With Stage", renderers=[cap]):
        with stage("Direct Stage"):
            pass
    started = next(e for e in cap.events if isinstance(e, StageStarted))
    assert started.module == _THIS_MODULE


def test_stage_explicit_module_overrides_auto_detection() -> None:
    cap = CapturingRenderer()
    with story("Story With Overridden Stage", renderers=[cap]):
        with stage("Overridden Stage", module="some.other.module"):
            pass
    started = next(e for e in cap.events if isinstance(e, StageStarted))
    assert started.module == "some.other.module"


def test_decorated_story_reports_decorated_functions_module_not_decorators_module() -> None:
    cap = CapturingRenderer()

    @runtime_narrative_story("Decorated Story", renderers=[cap])
    def run() -> None:
        pass

    run()
    started = next(e for e in cap.events if isinstance(e, StoryStarted))
    # Must be *this test file's* module, not runtime_narrative.decorators --
    # otherwise every decorated story would show the same useless value.
    assert started.module == _THIS_MODULE
    assert started.module != "runtime_narrative.decorators"


def test_decorated_async_story_reports_decorated_functions_module() -> None:
    cap = CapturingRenderer()

    @runtime_narrative_story("Decorated Async Story", renderers=[cap])
    async def run() -> int:
        return 1

    assert asyncio.run(run()) == 1
    started = next(e for e in cap.events if isinstance(e, StoryStarted))
    assert started.module == _THIS_MODULE


def test_decorated_stage_reports_decorated_functions_module() -> None:
    cap = CapturingRenderer()

    @runtime_narrative_stage("Decorated Stage")
    def do_thing() -> None:
        pass

    with story("Wrapper Story", renderers=[cap]):
        do_thing()

    started = next(e for e in cap.events if isinstance(e, StageStarted))
    assert started.module == _THIS_MODULE
    assert started.module != "runtime_narrative.decorators"


def test_decorated_async_stage_reports_decorated_functions_module() -> None:
    cap = CapturingRenderer()

    @runtime_narrative_stage("Decorated Async Stage")
    async def do_thing() -> None:
        pass

    async def run() -> None:
        async with story("Async Wrapper Story", renderers=[cap]):
            await do_thing()

    asyncio.run(run())
    started = next(e for e in cap.events if isinstance(e, StageStarted))
    assert started.module == _THIS_MODULE
