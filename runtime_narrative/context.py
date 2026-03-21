from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stage import StageRecord
    from .story import StoryRuntime

current_story: ContextVar[StoryRuntime | None] = ContextVar("current_story", default=None)
current_stage_stack: ContextVar[list[StageRecord]] = ContextVar("current_stage_stack", default=[])
