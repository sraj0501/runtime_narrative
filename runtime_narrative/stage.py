from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .context import current_stage_stack, current_story


@dataclass
class StageRecord:
    name: str
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    completed: bool = False
    failed: bool = False
    stage_index: int = 0
    parent_stage_name: str | None = None


class stage:
    def __init__(self, name: str, *, optional: bool = False):
        self.name = name
        self.optional = optional
        self.record = StageRecord(name=name)

    def __enter__(self) -> StageRecord:
        story_runtime = current_story.get()
        if story_runtime is None:
            if self.optional:
                return self.record
            raise RuntimeError("stage() must run inside an active story() context")

        stack = list(current_stage_stack.get())
        self.record.parent_stage_name = stack[-1].name if stack else None
        story_runtime.register_stage(self.record)
        self.record.stage_index = len(story_runtime.stages) - 1
        stack.append(self.record)
        current_stage_stack.set(stack)
        story_runtime.on_stage_started(self.record)
        return self.record

    async def __aenter__(self) -> StageRecord:
        story_runtime = current_story.get()
        if story_runtime is None:
            if self.optional:
                return self.record
            raise RuntimeError("stage() must run inside an active story() context")

        stack = list(current_stage_stack.get())
        self.record.parent_stage_name = stack[-1].name if stack else None
        story_runtime.register_stage(self.record)
        self.record.stage_index = len(story_runtime.stages) - 1
        stack.append(self.record)
        current_stage_stack.set(stack)
        await story_runtime.on_stage_started_async(self.record)
        return self.record

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        ended_at = datetime.now()
        self.record.ended_at = ended_at
        self.record.duration_seconds = (ended_at - self.record.started_at).total_seconds()

        story_runtime = current_story.get()
        dry_run = story_runtime.dry_run if story_runtime is not None else False

        if story_runtime is not None and exc_type is not None and not dry_run:
            story_runtime.failed_stage_name = self.record.name

        stack = list(current_stage_stack.get())
        if stack:
            stack.pop()
        current_stage_stack.set(stack)

        if story_runtime is None:
            return False

        if exc_type is None or dry_run:
            self.record.completed = True
            await story_runtime.on_stage_completed_async(self.record)
            return dry_run and exc_type is not None
        else:
            self.record.failed = True
        return False

    def __exit__(self, exc_type, exc, tb) -> bool:
        ended_at = datetime.now()
        self.record.ended_at = ended_at
        self.record.duration_seconds = (ended_at - self.record.started_at).total_seconds()

        story_runtime = current_story.get()
        dry_run = story_runtime.dry_run if story_runtime is not None else False

        if story_runtime is not None and exc_type is not None and not dry_run:
            story_runtime.failed_stage_name = self.record.name

        stack = list(current_stage_stack.get())
        if stack:
            stack.pop()
        current_stage_stack.set(stack)

        if story_runtime is None:
            return False

        if exc_type is None or dry_run:
            self.record.completed = True
            story_runtime.on_stage_completed(self.record)
            return dry_run and exc_type is not None
        else:
            self.record.failed = True
        return False
