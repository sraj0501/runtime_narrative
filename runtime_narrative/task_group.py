from __future__ import annotations

import asyncio
from typing import Any, Coroutine

__all__ = ["NarrativeTaskGroup", "NarrativeTaskGroupError"]


class NarrativeTaskGroupError(Exception):
    def __init__(self, failed_tasks: dict[str, BaseException]) -> None:
        self.failed_tasks = failed_tasks
        names = ", ".join(failed_tasks)
        super().__init__(f"Tasks failed: {names}")


class NarrativeTaskGroup:
    """Async context manager that runs concurrent tasks under a shared story.

    Must be used inside an existing ``async with story(...)`` block. Each task
    created via :meth:`create_task` inherits the parent story context
    automatically (asyncio copies ContextVars to child tasks).

    On exit, waits for all tasks. If any fail, raises
    :class:`NarrativeTaskGroupError` with a mapping of task name → exception.
    """

    def __init__(self) -> None:
        self._pending: list[tuple[str, asyncio.Task[Any]]] = []

    async def __aenter__(self) -> "NarrativeTaskGroup":
        return self

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        name: str | None = None,
    ) -> asyncio.Task[Any]:
        task_name = name or f"task-{len(self._pending)}"
        task = asyncio.create_task(coro, name=task_name)
        self._pending.append((task_name, task))
        return task

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if not self._pending:
            return False

        if exc_type is not None:
            for _, task in self._pending:
                task.cancel()
            await asyncio.gather(*[t for _, t in self._pending], return_exceptions=True)
            return False

        results = await asyncio.gather(
            *[t for _, t in self._pending], return_exceptions=True
        )
        failures: dict[str, BaseException] = {
            name: exc
            for (name, _), exc in zip(self._pending, results)
            if isinstance(exc, BaseException)
            and not isinstance(exc, asyncio.CancelledError)
        }
        if failures:
            raise NarrativeTaskGroupError(failures)
        return False
