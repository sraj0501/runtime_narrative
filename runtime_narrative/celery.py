from __future__ import annotations

import sys
from typing import Any, Sequence

from .story import story

try:
    import celery as _celery
    _CELERY_AVAILABLE = True
    _TaskBase: type = _celery.Task
except ImportError:
    _celery = None  # type: ignore[assignment]
    _CELERY_AVAILABLE = False
    _TaskBase = object


def _default_renderers() -> tuple:
    if getattr(sys.stdout, "isatty", lambda: False)():
        from .renderer.console import ConsoleRenderer
        return (ConsoleRenderer(),)
    from .renderer.json_renderer import JsonRenderer
    return (JsonRenderer(),)


class NarrativeTask(_TaskBase):  # type: ignore[valid-type,misc]
    abstract = True

    narrative_renderers: Sequence[object] | None = None
    narrative_failure_analyzer: Any | None = None
    narrative_diagnostics_config: Any | None = None
    narrative_runtime_environment: str | None = None
    narrative_failure_diagnostics: str | None = None
    narrative_allow_rich_in_production: bool | None = None
    narrative_app_roots: Sequence[str] | None = None
    narrative_redact_extra: Sequence[str] | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        if not _CELERY_AVAILABLE:
            raise ImportError(
                "celery package is required for NarrativeTask. "
                "Install it with: pip install 'runtime-narrative[celery]'"
            )
        super().__init__(*args, **kwargs)

    def __call__(self, *args: object, **kwargs: object) -> object:
        request = getattr(self, "request", None)
        task_id = getattr(request, "id", None) or "unknown"
        story_name = f"{self.name} [task_id={task_id}]"
        renderers = self.narrative_renderers if self.narrative_renderers is not None else _default_renderers()
        with story(
            story_name,
            renderers=renderers,
            failure_analyzer=self.narrative_failure_analyzer,
            diagnostics_config=self.narrative_diagnostics_config,
            runtime_environment=self.narrative_runtime_environment,
            failure_diagnostics=self.narrative_failure_diagnostics,
            allow_rich_in_production=self.narrative_allow_rich_in_production,
            app_roots=self.narrative_app_roots,
            redact_extra=self.narrative_redact_extra,
        ):
            return super().__call__(*args, **kwargs)


def connect_narrative(
    celery_app: Any,
    *,
    renderers: Sequence[object] | None = None,
    failure_analyzer: Any | None = None,
    diagnostics_config: Any | None = None,
    runtime_environment: str | None = None,
    failure_diagnostics: str | None = None,
    allow_rich_in_production: bool | None = None,
    app_roots: Sequence[str] | None = None,
    redact_extra: Sequence[str] | None = None,
) -> None:
    NarrativeTask.narrative_renderers = renderers
    NarrativeTask.narrative_failure_analyzer = failure_analyzer
    NarrativeTask.narrative_diagnostics_config = diagnostics_config
    NarrativeTask.narrative_runtime_environment = runtime_environment
    NarrativeTask.narrative_failure_diagnostics = failure_diagnostics
    NarrativeTask.narrative_allow_rich_in_production = allow_rich_in_production
    NarrativeTask.narrative_app_roots = app_roots
    NarrativeTask.narrative_redact_extra = redact_extra


__all__ = ["NarrativeTask", "connect_narrative"]
