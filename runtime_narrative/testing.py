from __future__ import annotations

from typing import Any, Sequence

from .story import story

__all__ = ["StoryRecorder"]


class _RecordingRenderer:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def handle(self, event: object) -> None:
        self.events.append(event)


class StoryRecorder:
    """Dual sync/async context manager that records story events for test assertions.

    Usage::

        with StoryRecorder("My Pipeline") as recorder:
            my_function()   # uses stage() internally

        recorder.assert_stages_completed(["Load", "Validate", "Insert"])
        recorder.assert_no_failure()

    Pass ``dry_run=True`` to run without executing stage body side-effects::

        with StoryRecorder("My Pipeline", dry_run=True) as recorder:
            my_pipeline()

        recorder.assert_stages_completed(["Load", "Validate", "Insert"])
    """

    def __init__(
        self,
        name: str = "test",
        *,
        renderers: Sequence[object] | None = None,
        **story_kwargs: Any,
    ) -> None:
        self._name = name
        self._extra_renderers: list[object] = list(renderers) if renderers else []
        self._story_kwargs = story_kwargs
        self._renderer = _RecordingRenderer()
        self._story_ctx: Any = None

    def _build_story(self) -> Any:
        return story(
            self._name,
            renderers=[self._renderer] + self._extra_renderers,
            **self._story_kwargs,
        )

    @property
    def events(self) -> list[Any]:
        return self._renderer.events

    def __enter__(self) -> "StoryRecorder":
        self._story_ctx = self._build_story()
        self._story_ctx.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        return self._story_ctx.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self) -> "StoryRecorder":
        self._story_ctx = self._build_story()
        await self._story_ctx.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        return await self._story_ctx.__aexit__(exc_type, exc_val, exc_tb)

    def _failure_events(self) -> list[Any]:
        return [e for e in self.events if type(e).__name__ == "FailureOccurred"]

    def _completed_stage_names(self) -> set[str]:
        return {e.stage_name for e in self.events if type(e).__name__ == "StageCompleted"}

    def assert_stages_completed(self, stage_names: Sequence[str]) -> None:
        completed = self._completed_stage_names()
        missing = [n for n in stage_names if n not in completed]
        if missing:
            raise AssertionError(
                f"Expected stages not completed: {missing}. "
                f"Completed stages were: {sorted(completed)}"
            )

    def assert_no_failure(self) -> None:
        failures = self._failure_events()
        if failures:
            f = failures[0]
            raise AssertionError(
                f"Expected no failure but got: {f.error_type}: {f.error_message} "
                f"at {f.filename}:{f.lineno}"
            )

    def assert_stage_failed(
        self,
        stage_name: str,
        *,
        error_type: str | None = None,
    ) -> None:
        failures = self._failure_events()
        if not failures:
            raise AssertionError(
                f"Expected failure at stage '{stage_name}' but no failure occurred"
            )
        match = next((f for f in failures if f.stage_name == stage_name), None)
        if match is None:
            actual = failures[0].stage_name
            raise AssertionError(
                f"Expected failure at stage '{stage_name}', "
                f"but failure occurred at '{actual}'"
            )
        if error_type is not None and match.error_type != error_type:
            raise AssertionError(
                f"Expected error type '{error_type}' at stage '{stage_name}' "
                f"but got '{match.error_type}'"
            )

    def assert_story_completed(self, *, success: bool | None = None) -> None:
        completed_evts = [e for e in self.events if type(e).__name__ == "StoryCompleted"]
        if not completed_evts:
            raise AssertionError("Expected StoryCompleted event but none was emitted")
        if success is not None and completed_evts[0].success != success:
            raise AssertionError(
                f"Expected story success={success} but got success={completed_evts[0].success}"
            )
