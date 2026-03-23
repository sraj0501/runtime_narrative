from __future__ import annotations

from typing import Any, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .diagnostics import FailureDiagnosticsConfig
from .story import story


class RuntimeNarrativeMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that wraps every HTTP request in a runtime_narrative story.

    Each request gets a story named "<METHOD> <path>" (e.g. "POST /customers").
    The story context is available to all stages declared inside route handlers.

    Usage::

        from runtime_narrative.middleware import RuntimeNarrativeMiddleware
        from runtime_narrative.renderer.json_renderer import JsonRenderer

        app.add_middleware(
            RuntimeNarrativeMiddleware,
            renderers=[JsonRenderer()],   # optional, defaults to ConsoleRenderer
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
    ):
        super().__init__(app)
        self._renderers = renderers
        self._failure_analyzer = failure_analyzer
        self._diagnostics_config = diagnostics_config
        self._runtime_environment = runtime_environment
        self._failure_diagnostics = failure_diagnostics
        self._allow_rich_in_production = allow_rich_in_production
        self._app_roots = app_roots

    async def dispatch(self, request: Request, call_next) -> Response:
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
        ):
            response = await call_next(request)
        return response


__all__ = ["RuntimeNarrativeMiddleware"]
