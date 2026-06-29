from __future__ import annotations

import sys
from typing import Any, Sequence

from .diagnostics import FailureDiagnosticsConfig
from .story import story

try:
    import django  # noqa: F401
    _DJANGO_AVAILABLE = True
except ImportError:
    _DJANGO_AVAILABLE = False


def _default_renderers() -> tuple:
    if getattr(sys.stdout, "isatty", lambda: False)():
        from .renderer.console import ConsoleRenderer
        return (ConsoleRenderer(),)
    from .renderer.json_renderer import JsonRenderer
    return (JsonRenderer(),)


class RuntimeNarrativeDjangoMiddleware:
    async_capable = True
    sync_capable = False

    def __init__(
        self,
        get_response,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        *,
        diagnostics_config: FailureDiagnosticsConfig | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
    ):
        if not _DJANGO_AVAILABLE:
            raise ImportError(
                "Django is required for RuntimeNarrativeDjangoMiddleware. "
                "Install it with: pip install django"
            )
        self.get_response = get_response
        self._renderers = tuple(renderers) if renderers is not None else _default_renderers()
        self._failure_analyzer = failure_analyzer
        self._diagnostics_config = diagnostics_config
        self._runtime_environment = runtime_environment
        self._failure_diagnostics = failure_diagnostics
        self._allow_rich_in_production = allow_rich_in_production
        self._app_roots = app_roots
        self._redact_extra = redact_extra

    async def __call__(self, request):
        story_name = f"{request.method} {request.path_info}"
        async with story(
            story_name,
            renderers=self._renderers,
            failure_analyzer=self._failure_analyzer,
            diagnostics_config=self._diagnostics_config,
            runtime_environment=self._runtime_environment,
            failure_diagnostics=self._failure_diagnostics,
            allow_rich_in_production=self._allow_rich_in_production,
            app_roots=self._app_roots,
            redact_extra=self._redact_extra,
        ):
            response = await self.get_response(request)
        return response


class RuntimeNarrativeDjangoSyncMiddleware:
    async_capable = False
    sync_capable = True

    def __init__(
        self,
        get_response,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        *,
        diagnostics_config: FailureDiagnosticsConfig | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
    ):
        if not _DJANGO_AVAILABLE:
            raise ImportError(
                "Django is required for RuntimeNarrativeDjangoSyncMiddleware. "
                "Install it with: pip install django"
            )
        self.get_response = get_response
        self._renderers = tuple(renderers) if renderers is not None else _default_renderers()
        self._failure_analyzer = failure_analyzer
        self._diagnostics_config = diagnostics_config
        self._runtime_environment = runtime_environment
        self._failure_diagnostics = failure_diagnostics
        self._allow_rich_in_production = allow_rich_in_production
        self._app_roots = app_roots
        self._redact_extra = redact_extra

    def __call__(self, request):
        story_name = f"{request.method} {request.path_info}"
        with story(
            story_name,
            renderers=self._renderers,
            failure_analyzer=self._failure_analyzer,
            diagnostics_config=self._diagnostics_config,
            runtime_environment=self._runtime_environment,
            failure_diagnostics=self._failure_diagnostics,
            allow_rich_in_production=self._allow_rich_in_production,
            app_roots=self._app_roots,
            redact_extra=self._redact_extra,
        ):
            response = self.get_response(request)
        return response


__all__ = ["RuntimeNarrativeDjangoMiddleware", "RuntimeNarrativeDjangoSyncMiddleware"]
