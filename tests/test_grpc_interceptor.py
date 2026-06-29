from __future__ import annotations

import asyncio
import copy
import sys
import types
import unittest.mock as mock

import pytest

# Inject fake grpc modules before importing the interceptor module.
_fake_grpc = types.ModuleType("grpc")
_fake_grpc_aio = types.ModuleType("grpc.aio")


class _FakeServerInterceptor:
    pass


class _FakeAioServerInterceptor:
    pass


class _FakeRpcMethodHandler:
    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _replace(self, **kwargs: object) -> "_FakeRpcMethodHandler":
        new = copy.copy(self)
        for k, v in kwargs.items():
            setattr(new, k, v)
        return new


class _FakeHandlerCallDetails:
    def __init__(self, method: str) -> None:
        self.method = method


_fake_grpc.ServerInterceptor = _FakeServerInterceptor
_fake_grpc.aio = _fake_grpc_aio
_fake_grpc_aio.ServerInterceptor = _FakeAioServerInterceptor
sys.modules.setdefault("grpc", _fake_grpc)
sys.modules.setdefault("grpc.aio", _fake_grpc_aio)

import runtime_narrative.grpc_interceptor as _grpc_mod
from tests.conftest import CapturingRenderer


@pytest.fixture(autouse=True)
def _force_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_grpc_mod, "_GRPC_AVAILABLE", True)
    monkeypatch.setattr(_grpc_mod, "_grpc", _fake_grpc)
    monkeypatch.setattr(_grpc_mod, "_GRPC_AIO_AVAILABLE", True)
    monkeypatch.setattr(_grpc_mod, "_grpc_aio", _fake_grpc_aio)


def test_sync_interceptor_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_grpc_mod, "_GRPC_AVAILABLE", False)
    with pytest.raises(ImportError):
        _grpc_mod.RuntimeNarrativeInterceptor()


def test_async_interceptor_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_grpc_mod, "_GRPC_AIO_AVAILABLE", False)
    with pytest.raises(ImportError):
        _grpc_mod.RuntimeNarrativeAsyncInterceptor()


def test_sync_interceptor_wraps_unary_handler() -> None:
    renderer = CapturingRenderer()
    interceptor = _grpc_mod.RuntimeNarrativeInterceptor(renderers=[renderer])

    def _handler(request: object, context: object) -> str:
        return "result"

    original = _FakeRpcMethodHandler(unary_unary=_handler)
    details = _FakeHandlerCallDetails("/pkg.Service/Method")
    wrapped = interceptor.intercept_service(lambda d: original, details)

    result = wrapped.unary_unary("req", "ctx")
    assert result == "result"
    event_types = [type(e).__name__ for e in renderer.events]
    assert "StoryStarted" in event_types
    assert "StoryCompleted" in event_types


def test_sync_interceptor_story_name() -> None:
    renderer = CapturingRenderer()
    interceptor = _grpc_mod.RuntimeNarrativeInterceptor(renderers=[renderer])
    original = _FakeRpcMethodHandler(unary_unary=lambda req, ctx: "ok")
    details = _FakeHandlerCallDetails("/mypackage.MyService/DoThing")
    wrapped = interceptor.intercept_service(lambda d: original, details)
    wrapped.unary_unary("req", "ctx")
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert "/mypackage.MyService/DoThing" in started.story_name


def test_sync_interceptor_failure_emits_failure_occurred() -> None:
    renderer = CapturingRenderer()
    interceptor = _grpc_mod.RuntimeNarrativeInterceptor(renderers=[renderer])

    def _bad_handler(request: object, context: object) -> None:
        raise RuntimeError("rpc failed")

    original = _FakeRpcMethodHandler(unary_unary=_bad_handler)
    details = _FakeHandlerCallDetails("/pkg.Service/Bad")
    wrapped = interceptor.intercept_service(lambda d: original, details)

    with pytest.raises(RuntimeError):
        wrapped.unary_unary("req", "ctx")

    event_types = [type(e).__name__ for e in renderer.events]
    assert "FailureOccurred" in event_types


def test_sync_interceptor_returns_none_when_continuation_returns_none() -> None:
    interceptor = _grpc_mod.RuntimeNarrativeInterceptor(renderers=[CapturingRenderer()])
    details = _FakeHandlerCallDetails("/pkg.Service/Missing")
    result = interceptor.intercept_service(lambda d: None, details)
    assert result is None


def test_async_interceptor_wraps_method() -> None:
    renderer = CapturingRenderer()
    interceptor = _grpc_mod.RuntimeNarrativeAsyncInterceptor(renderers=[renderer])

    async def _method(request: object, context: object) -> str:
        return "async-result"

    async def run() -> str:
        return await interceptor.intercept(
            _method, "req", "ctx", "/pkg.Service/AsyncMethod"
        )

    result = asyncio.run(run())
    assert result == "async-result"
    event_types = [type(e).__name__ for e in renderer.events]
    assert "StoryStarted" in event_types
    assert "StoryCompleted" in event_types


def test_async_interceptor_story_name() -> None:
    renderer = CapturingRenderer()
    interceptor = _grpc_mod.RuntimeNarrativeAsyncInterceptor(renderers=[renderer])

    async def _method(request: object, context: object) -> str:
        return "ok"

    asyncio.run(
        interceptor.intercept(_method, "req", "ctx", "/svc.MyService/MyRPC")
    )
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert "/svc.MyService/MyRPC" in started.story_name
