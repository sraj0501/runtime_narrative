from __future__ import annotations

import asyncio

import pytest

import runtime_narrative.middleware_django as _django_mod
from tests.conftest import CapturingRenderer


class _FakeDjangoRequest:
    method = "GET"
    path_info = "/customers"


async def _ok(request):
    return "response-ok"


async def _fail(request):
    raise ValueError("handler failed")


def _sync_ok(request):
    return "response-ok"


def _sync_fail(request):
    raise ValueError("handler failed")


@pytest.fixture(autouse=True)
def _force_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_django_mod, "_DJANGO_AVAILABLE", True)


def test_async_raises_import_error_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_django_mod, "_DJANGO_AVAILABLE", False)
    with pytest.raises(ImportError):
        _django_mod.RuntimeNarrativeDjangoMiddleware(lambda r: r)


def test_sync_raises_import_error_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_django_mod, "_DJANGO_AVAILABLE", False)
    with pytest.raises(ImportError):
        _django_mod.RuntimeNarrativeDjangoSyncMiddleware(lambda r: r)


def test_async_emits_story_events() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_ok, renderers=[renderer])
    asyncio.run(mw(_FakeDjangoRequest()))
    event_types = [type(e).__name__ for e in renderer.events]
    assert "StoryStarted" in event_types
    assert "StoryCompleted" in event_types


def test_async_story_name() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_ok, renderers=[renderer])
    asyncio.run(mw(_FakeDjangoRequest()))
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert started.story_name == "GET /customers"


def test_async_failure_emits_failure_occurred() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_fail, renderers=[renderer])
    with pytest.raises(ValueError):
        asyncio.run(mw(_FakeDjangoRequest()))
    event_types = [type(e).__name__ for e in renderer.events]
    assert "FailureOccurred" in event_types


def test_async_failure_reraises() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_fail, renderers=[renderer])
    with pytest.raises(ValueError, match="handler failed"):
        asyncio.run(mw(_FakeDjangoRequest()))


class _FakeDjangoResponse:
    status_code = 200


async def _ok_with_status(request):
    return _FakeDjangoResponse()


def _sync_ok_with_status(request):
    return _FakeDjangoResponse()


def test_async_records_status_outcome() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_ok_with_status, renderers=[renderer])
    asyncio.run(mw(_FakeDjangoRequest()))
    completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert completed.outcome == "200 OK"


def test_sync_records_status_outcome() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoSyncMiddleware(_sync_ok_with_status, renderers=[renderer])
    mw(_FakeDjangoRequest())
    completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert completed.outcome == "200 OK"


def test_async_response_without_status_leaves_outcome_empty() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoMiddleware(_ok, renderers=[renderer])
    asyncio.run(mw(_FakeDjangoRequest()))
    completed = next(e for e in renderer.events if type(e).__name__ == "StoryCompleted")
    assert completed.outcome == ""


def test_sync_emits_story_events() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoSyncMiddleware(_sync_ok, renderers=[renderer])
    mw(_FakeDjangoRequest())
    event_types = [type(e).__name__ for e in renderer.events]
    assert "StoryStarted" in event_types
    assert "StoryCompleted" in event_types


def test_sync_story_name() -> None:
    renderer = CapturingRenderer()

    class _PostReq:
        method = "POST"
        path_info = "/orders"

    mw = _django_mod.RuntimeNarrativeDjangoSyncMiddleware(_sync_ok, renderers=[renderer])
    mw(_PostReq())
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert started.story_name == "POST /orders"


def test_sync_failure_emits_failure_occurred() -> None:
    renderer = CapturingRenderer()
    mw = _django_mod.RuntimeNarrativeDjangoSyncMiddleware(_sync_fail, renderers=[renderer])
    with pytest.raises(ValueError):
        mw(_FakeDjangoRequest())
    event_types = [type(e).__name__ for e in renderer.events]
    assert "FailureOccurred" in event_types
