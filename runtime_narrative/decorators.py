from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, Sequence, TypeVar

from .diagnostics import FailureDiagnosticsConfig
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
    background_analysis: bool = False,
    diagnostics_config: FailureDiagnosticsConfig | None = None,
    runtime_environment: str | None = None,
    failure_diagnostics: str | None = None,
    allow_rich_in_production: bool | None = None,
    app_roots: Sequence[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to wrap a function in a story context (sync or async)."""

    def decorator(func: F) -> F:
        story_name = name or _default_name(func)

        story_kw: dict[str, Any] = {
            "renderers": renderers,
            "failure_analyzer": failure_analyzer,
            "background_analysis": background_analysis,
            "diagnostics_config": diagnostics_config,
            "runtime_environment": runtime_environment,
            "failure_diagnostics": failure_diagnostics,
            "allow_rich_in_production": allow_rich_in_production,
            "app_roots": app_roots,
        }

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                async with story(story_name, **story_kw):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with story(story_name, **story_kw):
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
                async with stage(stage_name):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with stage(stage_name):
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
