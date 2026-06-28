from __future__ import annotations

import sys
from typing import Any, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .diagnostics import FailureDiagnosticsConfig
from .story import story

try:
    from opentelemetry import propagate as _otel_propagate
    from opentelemetry import context as _otel_context
    _OTEL_PROPAGATION_AVAILABLE = True
except ImportError:
    _OTEL_PROPAGATION_AVAILABLE = False


def _default_middleware_renderers() -> tuple:
    """Return ConsoleRenderer when attached to a real terminal, JsonRenderer otherwise."""
    if getattr(sys.stdout, "isatty", lambda: False)():
        from .renderer.console import ConsoleRenderer
        return (ConsoleRenderer(),)
    from .renderer.json_renderer import JsonRenderer
    return (JsonRenderer(),)


class RuntimeNarrativeMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that wraps every HTTP request in a runtime_narrative story.

    Each request gets a story named "<METHOD> <path>" (e.g. "POST /customers").
    The story context is available to all stages declared inside route handlers.

    When no ``renderers`` are passed, the middleware auto-selects:
    - ``ConsoleRenderer`` if ``sys.stdout`` is a real TTY (local dev server)
    - ``JsonRenderer`` otherwise (production, Docker, CI — any non-interactive environment)

    Usage::

        from runtime_narrative.middleware import RuntimeNarrativeMiddleware
        from runtime_narrative.renderer.json_renderer import JsonRenderer

        app.add_middleware(
            RuntimeNarrativeMiddleware,
            renderers=[JsonRenderer()],   # explicit override
            failure_analyzer=None,        # optional OllamaFailureAnalyzer
        )

    Once added, individual route handlers no longer need to create their own
    ``story()`` context — they can use ``stage()`` directly::

        @app.post("/orders")
        async def create_order(payload: OrderIn):
            with stage("Validate Input"):
                ...
            with stage("Persist Order"):
                ...
    """

    def __init__(
        self,
        app,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        *,
        diagnostics_config: FailureDiagnosticsConfig | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
        propagate_trace_context: bool = True,
    ):
        super().__init__(app)
        self._renderers = tuple(renderers) if renderers is not None else _default_middleware_renderers()
        self._failure_analyzer = failure_analyzer
        self._diagnostics_config = diagnostics_config
        self._runtime_environment = runtime_environment
        self._failure_diagnostics = failure_diagnostics
        self._allow_rich_in_production = allow_rich_in_production
        self._app_roots = app_roots
        self._redact_extra = redact_extra
        self._propagate_trace_context = propagate_trace_context

    async def dispatch(self, request: Request, call_next) -> Response:
        token = None
        if _OTEL_PROPAGATION_AVAILABLE and self._propagate_trace_context:
            ctx = _otel_propagate.extract(dict(request.headers))
            token = _otel_context.attach(ctx)
        try:
            story_name = f"{request.method} {request.url.path}"
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
                response = await call_next(request)
            return response
        finally:
            if token is not None:
                _otel_context.detach(token)


__all__ = ["RuntimeNarrativeMiddleware"]
