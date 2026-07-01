from __future__ import annotations

import inspect
from typing import Any, Callable


class FilteredRenderer:
    """Wraps another renderer, only forwarding events where predicate(event) is True.

    Every event type in this library (StoryStarted, StageStarted, StageCompleted,
    FailureOccurred, StoryCompleted, LLMAnalysisReady, LogRecorded) carries
    `story_name`, so predicates commonly match on that -- e.g. give every
    "GET ..." request story its own style and destination:

        renderers=[
            FilteredRenderer(
                lambda e: getattr(e, "story_name", "").startswith("GET "),
                ConsoleRenderer(level_icons={"warning": "note: ", "error": "err: "}),
            ),
            FilteredRenderer(
                lambda e: not getattr(e, "story_name", "").startswith("GET "),
                ConsoleRenderer(),
            ),
        ]

    Any predicate works -- by stage_name, error_type, level, story_id, etc.
    Mirrors the wrapped renderer's sync/async `handle` so it can wrap either
    kind and still dispatch correctly through `emit`/`emit_async`.
    """

    def __init__(self, predicate: Callable[[Any], bool], renderer: Any) -> None:
        self._predicate = predicate
        self._renderer = renderer
        if inspect.iscoroutinefunction(getattr(renderer, "handle", None)):
            self.handle = self._handle_async
        else:
            self.handle = self._handle_sync

    def _handle_sync(self, event: object) -> None:
        if self._predicate(event):
            self._renderer.handle(event)

    async def _handle_async(self, event: object) -> None:
        if self._predicate(event):
            await self._renderer.handle(event)


__all__ = ["FilteredRenderer"]
