from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import story, stage
from runtime_narrative.task_group import NarrativeTaskGroup, NarrativeTaskGroupError
from tests.conftest import CapturingRenderer


async def _ok(value: str = "done") -> str:
    return value


async def _fail(msg: str = "boom") -> None:
    raise ValueError(msg)


async def _with_stage(stage_name: str) -> None:
    async with stage(stage_name):
        await asyncio.sleep(0)


def test_empty_group_exits_cleanly() -> None:
    async def run() -> None:
        async with story("s", renderers=[CapturingRenderer()]):
            async with NarrativeTaskGroup():
                pass

    asyncio.run(run())


def test_all_tasks_succeed() -> None:
    renderer = CapturingRenderer()

    async def run() -> None:
        async with story("s", renderers=[renderer]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_ok("a"), name="A")
                tg.create_task(_ok("b"), name="B")

    asyncio.run(run())
    completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert completed.success is True


def test_single_task_failure_raises_narrative_error() -> None:
    renderer = CapturingRenderer()

    async def run() -> None:
        async with story("s", renderers=[renderer]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_fail("oops"), name="Worker")

    with pytest.raises(NarrativeTaskGroupError) as exc_info:
        asyncio.run(run())

    assert "Worker" in exc_info.value.failed_tasks
    assert isinstance(exc_info.value.failed_tasks["Worker"], ValueError)


def test_multiple_task_failures_all_reported() -> None:
    async def run() -> None:
        async with story("s", renderers=[CapturingRenderer()]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_fail("err1"), name="T1")
                tg.create_task(_fail("err2"), name="T2")

    with pytest.raises(NarrativeTaskGroupError) as exc_info:
        asyncio.run(run())

    assert "T1" in exc_info.value.failed_tasks
    assert "T2" in exc_info.value.failed_tasks


def test_error_message_lists_task_names() -> None:
    async def run() -> None:
        async with story("s", renderers=[CapturingRenderer()]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_fail(), name="MyTask")

    with pytest.raises(NarrativeTaskGroupError) as exc_info:
        asyncio.run(run())

    assert "MyTask" in str(exc_info.value)


def test_default_task_names_generated() -> None:
    async def run() -> list[str]:
        async with story("s", renderers=[CapturingRenderer()]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_ok())
                tg.create_task(_ok())
            return [name for name, _ in tg._pending]

    names = asyncio.run(run())
    assert names == ["task-0", "task-1"]


def test_stages_inside_tasks_visible_in_story() -> None:
    renderer = CapturingRenderer()

    async def run() -> None:
        async with story("s", renderers=[renderer]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_with_stage("Load"), name="Loader")
                tg.create_task(_with_stage("Transform"), name="Transformer")

    asyncio.run(run())
    stage_names = {
        e.stage_name
        for e in renderer.events
        if type(e).__name__ == "StageCompleted"
    }
    assert "Load" in stage_names
    assert "Transform" in stage_names


def test_group_without_story_does_not_crash() -> None:
    async def run() -> None:
        async with NarrativeTaskGroup() as tg:
            tg.create_task(_ok())

    asyncio.run(run())


def test_partial_failure_still_reports_correct_tasks() -> None:
    renderer = CapturingRenderer()

    async def run() -> None:
        async with story("s", renderers=[renderer]):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(_ok("fine"), name="Good")
                tg.create_task(_fail("bad"), name="Bad")

    with pytest.raises(NarrativeTaskGroupError) as exc_info:
        asyncio.run(run())

    assert "Bad" in exc_info.value.failed_tasks
    assert "Good" not in exc_info.value.failed_tasks
