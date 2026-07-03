from __future__ import annotations

import inspect
from typing import Any

from ..events import LogRecorded


class CoalescingRenderer:
    """Wraps another renderer, collapsing a run of identical back-to-back stages --
    e.g. a "poll status every 2s until done" loop -- into a single summary line
    instead of flooding the log with one StageStarted/StageCompleted pair per
    iteration.

    The wrapped renderer still sees the first `threshold` occurrences of a
    repeated (story_id, stage_name) pair in full, so the pattern is visible as
    it starts. From the next occurrence on, StageStarted/StageCompleted for
    that stage are suppressed and accumulated instead of forwarded. As soon as
    a different event arrives for that story (a different stage, a failure, or
    the story completing), the run is flushed as one LogRecorded summary line
    -- reporting the total call count and total time spent in that stage --
    forwarded through the wrapped renderer before the triggering event.

    Only wrap the human-facing renderer(s) with this (typically ConsoleRenderer).
    Renderers meant for full-fidelity machine consumption -- JsonRenderer,
    SqliteStoryRenderer, OtelRenderer, and friends -- should keep receiving
    every real event and should NOT be wrapped.

    Example -- a status-polling loop inside one long-running story::

        with story("Process Upload", renderers=[CoalescingRenderer(ConsoleRenderer())]):
            with stage("Upload File"):
                ...
            while not done:
                with stage("Check Pipeline Status"):
                    done = check_status()
                time.sleep(2)

    Only the first two (default `threshold`) status checks print a
    StageStarted/StageCompleted pair; the rest are folded into one line like::

        'Check Pipeline Status' repeated 41 more times (43 total) over 84.200s (avg 1.958s/call)

    Limitations: a run is keyed on (story_id, stage_name) alone, without regard
    to nesting -- a differently named stage nested *inside* the repeated one
    (e.g. a "Parse Response" sub-stage on every poll) counts as "a different
    stage" and ends the run early. Keep the polling loop's stage as a single,
    unnested stage per iteration to get full coalescing. Also, if the stage
    that's mid-run raises before completing, that final in-flight call's
    duration is not included in the summary total (though it is still counted).
    """

    def __init__(self, renderer: Any, *, threshold: int = 2) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self._renderer = renderer
        self._threshold = threshold
        self._runs: dict[str, dict[str, Any]] = {}
        if inspect.iscoroutinefunction(getattr(renderer, "handle", None)):
            self.handle = self._handle_async
        else:
            self.handle = self._handle_sync

    # ------------------------------------------------------------------
    # Shared run-tracking logic (pure, no I/O).
    # ------------------------------------------------------------------

    def _track_stage_started(self, event: Any) -> tuple[Any | None, bool]:
        """Returns (summary_event_to_flush_first_or_None, should_forward_this_event)."""
        story_id = event.story_id
        stage_name = event.stage_name
        run = self._runs.get(story_id)

        if run is not None and run["stage_name"] == stage_name:
            run["count"] += 1
            return None, run["count"] <= self._threshold

        summary = self._pop_summary(story_id)
        self._runs[story_id] = {
            "stage_name": stage_name,
            "count": 1,
            "total_duration": 0.0,
            "first_started_at": event.timestamp,
            "story_name": event.story_name,
            "root_story_id": event.root_story_id or story_id,
        }
        return summary, True

    def _track_stage_completed(self, event: Any) -> tuple[Any | None, bool]:
        story_id = event.story_id
        run = self._runs.get(story_id)
        if run is None or run["stage_name"] != event.stage_name:
            # Unbalanced (shouldn't normally happen) -- forward as-is.
            return None, True
        run["total_duration"] += event.duration_seconds
        return None, run["count"] <= self._threshold

    def _pop_summary(self, story_id: str) -> Any | None:
        run = self._runs.pop(story_id, None)
        if run is None or run["count"] <= self._threshold:
            return None
        suppressed = run["count"] - self._threshold
        avg = run["total_duration"] / run["count"] if run["count"] else 0.0
        return LogRecorded(
            story_id=story_id,
            story_name=run["story_name"],
            root_story_id=run["root_story_id"],
            stage_name=run["stage_name"],
            level="INFO",
            logger_name="runtime_narrative.coalesce",
            message=(
                f"{run['stage_name']!r} repeated {suppressed} more time"
                f"{'s' if suppressed != 1 else ''} ({run['count']} total) "
                f"over {run['total_duration']:.3f}s (avg {avg:.3f}s/call)"
            ),
            timestamp=run["first_started_at"],
        )

    def _flush(self, story_id: str) -> Any | None:
        return self._pop_summary(story_id)

    # ------------------------------------------------------------------
    # Sync / async dispatch
    # ------------------------------------------------------------------

    def _handle_sync(self, event: object) -> None:
        event_name = event.__class__.__name__
        story_id = getattr(event, "story_id", None)

        if event_name == "StageStarted":
            summary, forward = self._track_stage_started(event)
            if summary is not None:
                self._renderer.handle(summary)
            if forward:
                self._renderer.handle(event)
            return

        if event_name == "StageCompleted":
            summary, forward = self._track_stage_completed(event)
            if summary is not None:
                self._renderer.handle(summary)
            if forward:
                self._renderer.handle(event)
            return

        if story_id is not None:
            summary = self._flush(story_id)
            if summary is not None:
                self._renderer.handle(summary)
        self._renderer.handle(event)

    async def _handle_async(self, event: object) -> None:
        event_name = event.__class__.__name__
        story_id = getattr(event, "story_id", None)

        if event_name == "StageStarted":
            summary, forward = self._track_stage_started(event)
            if summary is not None:
                await self._renderer.handle(summary)
            if forward:
                await self._renderer.handle(event)
            return

        if event_name == "StageCompleted":
            summary, forward = self._track_stage_completed(event)
            if summary is not None:
                await self._renderer.handle(summary)
            if forward:
                await self._renderer.handle(event)
            return

        if story_id is not None:
            summary = self._flush(story_id)
            if summary is not None:
                await self._renderer.handle(summary)
        await self._renderer.handle(event)


__all__ = ["CoalescingRenderer"]
