from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import stage, story

from tests.conftest import CapturingRenderer


# ── T9: stage() outside story() raises RuntimeError (sync + async) ───────────

def test_stage_outside_story_raises() -> None:
    with pytest.raises(RuntimeError, match="must run inside an active story"):
        with stage("Orphan"):
            pass


def test_async_stage_outside_story_raises() -> None:
    async def run() -> None:
        async with stage("Orphan"):
            pass

    with pytest.raises(RuntimeError, match="must run inside an active story"):
        asyncio.run(run())


def test_nested_stages() -> None:
    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        with stage("Outer"):
            with stage("Inner"):
                pass
    names = [e.__class__.__name__ for e in cap.events]
    assert names.count("StageStarted") == 2
    assert names.count("StageCompleted") == 2
