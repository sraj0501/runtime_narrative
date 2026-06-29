from __future__ import annotations

import sys
from typing import Any, Callable, Sequence

from .story import story

try:
    import grpc as _grpc
    _GRPC_AVAILABLE = True
    _SyncBase: type = _grpc.ServerInterceptor
except ImportError:
    _grpc = None  # type: ignore[assignment]
    _GRPC_AVAILABLE = False
    _SyncBase = object

try:
    import grpc.aio as _grpc_aio
    _GRPC_AIO_AVAILABLE = True
    _AsyncBase: type = _grpc_aio.ServerInterceptor
except ImportError:
    _grpc_aio = None  # type: ignore[assignment]
    _GRPC_AIO_AVAILABLE = False
    _AsyncBase = object


def _default_renderers() -> tuple:
    if getattr(sys.stdout, "isatty", lambda: False)():
        from .renderer.console import ConsoleRenderer
        return (ConsoleRenderer(),)
    from .renderer.json_renderer import JsonRenderer
    return (JsonRenderer(),)


def _story_kwargs(interceptor: Any) -> dict:
    return {
        "renderers": interceptor._renderers or _default_renderers(),
        "failure_analyzer": interceptor._failure_analyzer,
        "diagnostics_config": interceptor._diagnostics_config,
        "runtime_environment": interceptor._runtime_environment,
        "failure_diagnostics": interceptor._failure_diagnostics,
        "allow_rich_in_production": interceptor._allow_rich_in_production,
        "app_roots": interceptor._app_roots,
        "redact_extra": interceptor._redact_extra,
    }


def _init_fields(
    self: Any,
    renderers: Sequence[object] | None,
    failure_analyzer: Any,
    diagnostics_config: Any,
    runtime_environment: str | None,
    failure_diagnostics: str | None,
    allow_rich_in_production: bool | None,
    app_roots: Sequence[str] | None,
    redact_extra: Sequence[str] | None,
) -> None:
    self._renderers = tuple(renderers) if renderers is not None else None
    self._failure_analyzer = failure_analyzer
    self._diagnostics_config = diagnostics_config
    self._runtime_environment = runtime_environment
    self._failure_diagnostics = failure_diagnostics
    self._allow_rich_in_production = allow_rich_in_production
    self._app_roots = app_roots
    self._redact_extra = redact_extra


class RuntimeNarrativeInterceptor(_SyncBase):  # type: ignore[misc,valid-type]
    def __init__(
        self,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        *,
        diagnostics_config: Any | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
    ) -> None:
        if not _GRPC_AVAILABLE:
            raise ImportError(
                "grpcio is required for RuntimeNarrativeInterceptor. "
                "Install it with: pip install 'runtime-narrative[grpc]'"
            )
        _init_fields(
            self, renderers, failure_analyzer, diagnostics_config,
            runtime_environment, failure_diagnostics, allow_rich_in_production,
            app_roots, redact_extra,
        )

    def intercept_service(self, continuation: Callable, handler_call_details: Any) -> Any:
        method_name = handler_call_details.method
        original_handler = continuation(handler_call_details)
        if original_handler is None:
            return None

        unary_fn = getattr(original_handler, "unary_unary", None)
        if unary_fn is None:
            return original_handler

        kwargs = _story_kwargs(self)

        def wrapped(request: Any, context: Any) -> Any:
            with story(method_name, **kwargs):
                return unary_fn(request, context)

        return original_handler._replace(unary_unary=wrapped)


class RuntimeNarrativeAsyncInterceptor(_AsyncBase):  # type: ignore[misc,valid-type]
    def __init__(
        self,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        *,
        diagnostics_config: Any | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
    ) -> None:
        if not _GRPC_AIO_AVAILABLE:
            raise ImportError(
                "grpcio is required for RuntimeNarrativeAsyncInterceptor. "
                "Install it with: pip install 'runtime-narrative[grpc]'"
            )
        _init_fields(
            self, renderers, failure_analyzer, diagnostics_config,
            runtime_environment, failure_diagnostics, allow_rich_in_production,
            app_roots, redact_extra,
        )

    async def intercept(
        self,
        method: Callable,
        request_or_iterator: Any,
        context: Any,
        method_name: str,
    ) -> Any:
        async with story(method_name, **_story_kwargs(self)):
            return await method(request_or_iterator, context)


__all__ = ["RuntimeNarrativeInterceptor", "RuntimeNarrativeAsyncInterceptor"]
