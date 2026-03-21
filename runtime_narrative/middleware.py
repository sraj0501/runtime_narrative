from __future__ import annotations

from typing import Any, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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
    ):
        super().__init__(app)
        self._renderers = renderers
        self._failure_analyzer = failure_analyzer

    async def dispatch(self, request: Request, call_next) -> Response:
        story_name = f"{request.method} {request.url.path}"
        with story(story_name, renderers=self._renderers, failure_analyzer=self._failure_analyzer):
            response = await call_next(request)
        return response


__all__ = ["RuntimeNarrativeMiddleware"]
