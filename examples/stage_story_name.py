"""Demonstrates story_name on StageStarted/StageCompleted.

Stage events now carry the enclosing story's name directly, so a renderer
that only cares about specific stories (e.g. an audit trail for "ADO" sagas)
can filter with `event.story_name` instead of tracking story_id -> story_name
in a side table populated from StoryStarted/StoryCompleted.

Run:
    uv run python examples/stage_story_name.py
"""
import asyncio

from runtime_narrative import stage, story


class AuditTrailRenderer:
    """Only records stage events for stories whose name it cares about."""

    def __init__(self, tracked_story_names: set[str]):
        self._tracked_story_names = tracked_story_names
        self.audit_log: list[str] = []

    async def handle(self, event: object) -> None:
        kind = type(event).__name__
        if kind not in ("StageStarted", "StageCompleted"):
            return
        if event.story_name not in self._tracked_story_names:
            return
        self.audit_log.append(f"[{event.story_name}] {kind}: {event.stage_name}")


async def main() -> None:
    renderer = AuditTrailRenderer(tracked_story_names={"ADO Transaction"})

    async with story("ADO Transaction", renderers=[renderer]):
        async with stage("Reserve Work Item"):
            await asyncio.sleep(0.01)
        async with stage("Commit Change"):
            await asyncio.sleep(0.01)

    # A story the renderer isn't tracking produces no audit entries.
    async with story("Unrelated Background Job", renderers=[renderer]):
        async with stage("Cleanup"):
            await asyncio.sleep(0.01)

    print("Audit log (ADO Transaction only, no story_id bookkeeping needed):")
    for line in renderer.audit_log:
        print(f"  {line}")


asyncio.run(main())
