from __future__ import annotations

import sys
import types

import pytest

# Inject fake celery before module import so _TaskBase = _FakeTask at class-definition time.
_fake_celery = types.ModuleType("celery")


class _FakeTask:
    abstract = False
    name = "myapp.tasks.test_task"

    class request:
        id = "abc-123"
        delivery_info = {"routing_key": "default"}

    def run(self, *args: object, **kwargs: object) -> str:
        return "ok"

    def __call__(self, *args: object, **kwargs: object) -> str:
        return self.run(*args, **kwargs)


_fake_celery.Task = _FakeTask
sys.modules.setdefault("celery", _fake_celery)

import runtime_narrative.celery as _celery_mod
from tests.conftest import CapturingRenderer


@pytest.fixture(autouse=True)
def _force_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_celery_mod, "_CELERY_AVAILABLE", True)
    monkeypatch.setattr(_celery_mod, "_celery", _fake_celery)


def _make_task(**kwargs: object) -> _celery_mod.NarrativeTask:
    class _Task(_celery_mod.NarrativeTask, _FakeTask):  # type: ignore[misc]
        pass

    for k, v in kwargs.items():
        setattr(_Task, k, v)
    return _Task()


def test_narrative_task_raises_import_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_celery_mod, "_CELERY_AVAILABLE", False)
    with pytest.raises(ImportError):
        _celery_mod.NarrativeTask()


def test_task_call_emits_story_started_and_completed() -> None:
    renderer = CapturingRenderer()
    t = _make_task(narrative_renderers=[renderer])
    t()
    event_types = [type(e).__name__ for e in renderer.events]
    assert "StoryStarted" in event_types
    assert "StoryCompleted" in event_types


def test_story_name_includes_task_name() -> None:
    renderer = CapturingRenderer()
    t = _make_task(narrative_renderers=[renderer])
    t()
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert "myapp.tasks.test_task" in started.story_name


def test_story_name_includes_task_id() -> None:
    renderer = CapturingRenderer()
    t = _make_task(narrative_renderers=[renderer])
    t()
    started = next(e for e in renderer.events if type(e).__name__ == "StoryStarted")
    assert "abc-123" in started.story_name


def test_task_failure_emits_failure_occurred_and_reraises() -> None:
    renderer = CapturingRenderer()

    class _FailTask(_celery_mod.NarrativeTask, _FakeTask):  # type: ignore[misc]
        narrative_renderers = [renderer]

        def run(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("task exploded")

    t = _FailTask()
    with pytest.raises(RuntimeError, match="task exploded"):
        t()
    event_types = [type(e).__name__ for e in renderer.events]
    assert "FailureOccurred" in event_types


def test_connect_narrative_sets_class_attributes() -> None:
    renderer = CapturingRenderer()
    _celery_mod.connect_narrative(
        None,
        renderers=[renderer],
        runtime_environment="production",
    )
    assert _celery_mod.NarrativeTask.narrative_renderers == [renderer]
    assert _celery_mod.NarrativeTask.narrative_runtime_environment == "production"
    _celery_mod.NarrativeTask.narrative_renderers = None
    _celery_mod.NarrativeTask.narrative_runtime_environment = None


def test_connect_narrative_sets_all_kwargs() -> None:
    _celery_mod.connect_narrative(
        None,
        failure_diagnostics="rich",
        allow_rich_in_production=True,
    )
    assert _celery_mod.NarrativeTask.narrative_failure_diagnostics == "rich"
    assert _celery_mod.NarrativeTask.narrative_allow_rich_in_production is True
    _celery_mod.NarrativeTask.narrative_failure_diagnostics = None
    _celery_mod.NarrativeTask.narrative_allow_rich_in_production = None
