from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, Sequence, TypeVar

from .stage import stage
from .story import story

F = TypeVar("F", bound=Callable[..., Any])


def _default_name(func: Callable[..., Any]) -> str:
    return func.__name__.replace("_", " ").strip().title()


def runtime_narrative_story(
    name: str | None = None,
    *,
    renderers: Sequence[object] | None = None,
    failure_analyzer: Any | None = None,
) -> Callable[[F], F]:
    """Decorator to wrap a function in a story context (sync or async)."""

    def decorator(func: F) -> F:
        story_name = name or _default_name(func)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                with story(story_name, renderers=renderers, failure_analyzer=failure_analyzer):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with story(story_name, renderers=renderers, failure_analyzer=failure_analyzer):
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def runtime_narrative_stage(name: str | None = None) -> Callable[[F], F]:
    """Decorator to wrap a function in a stage context (sync or async)."""

    def decorator(func: F) -> F:
        stage_name = name or _default_name(func)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                with stage(stage_name):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with stage(stage_name):
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
