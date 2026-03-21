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


class stage:
    def __init__(self, name: str):
        self.name = name
        self.record = StageRecord(name=name)

    def __enter__(self) -> StageRecord:
        story_runtime = current_story.get()
        if story_runtime is None:
            raise RuntimeError("stage() must run inside an active story() context")

        story_runtime.register_stage(self.record)
        stack = list(current_stage_stack.get())
        stack.append(self.record)
        current_stage_stack.set(stack)
        story_runtime.on_stage_started(self.record)
        return self.record

    def __exit__(self, exc_type, exc, tb) -> bool:
        ended_at = datetime.now()
        self.record.ended_at = ended_at
        self.record.duration_seconds = (ended_at - self.record.started_at).total_seconds()

        story_runtime = current_story.get()
        if story_runtime is not None and exc_type is not None:
            story_runtime.failed_stage_name = self.record.name

        stack = list(current_stage_stack.get())
        if stack:
            stack.pop()
        current_stage_stack.set(stack)

        if story_runtime is None:
            return False

        if exc_type is None:
            self.record.completed = True
            story_runtime.on_stage_completed(self.record)
        else:
            self.record.failed = True
        return False
