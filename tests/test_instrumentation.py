from __future__ import annotations

import asyncio
import sys
import types

import pytest

from runtime_narrative import narrative_class, no_stage, instrument_module, auto_instrument, stage, story
from runtime_narrative.instrumentation import _NarrativeLoader

from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


# ── no_stage ──────────────────────────────────────────────────────────────────

def test_no_stage_marks_function() -> None:
    @no_stage
    def helper(): pass
    assert getattr(helper, "_narrative_skip", False) is True


def test_no_stage_preserves_callable() -> None:
    @no_stage
    def add(a, b): return a + b
    assert add(1, 2) == 3


# ── narrative_class — basic wrapping ─────────────────────────────────────────

def test_narrative_class_public_method_creates_stage() -> None:
    @narrative_class
    class Calc:
        def add(self, a, b): return a + b

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = Calc().add(2, 3)

    assert result == 5
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Calc.add" in stage_names


def test_narrative_class_stage_name_includes_class_name() -> None:
    @narrative_class
    class OrderService:
        def validate(self): pass
        def charge(self): pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        svc = OrderService()
        svc.validate()
        svc.charge()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "OrderService.validate" in stage_names
    assert "OrderService.charge" in stage_names


def test_narrative_class_preserves_return_value() -> None:
    @narrative_class
    class Svc:
        def compute(self, x): return x * 10

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        assert Svc().compute(7) == 70


# ── narrative_class — exclusion rules ────────────────────────────────────────

def test_narrative_class_skips_private_methods() -> None:
    @narrative_class
    class Svc:
        def public(self): return "pub"
        def _private(self): return "priv"

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        svc = Svc()
        svc.public()
        svc._private()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Svc.public" in stage_names
    assert not any("_private" in n for n in stage_names)


def test_narrative_class_skips_no_stage_methods() -> None:
    @narrative_class
    class Svc:
        def instrumented(self): return 1

        @no_stage
        def excluded(self): return 2

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        svc = Svc()
        svc.instrumented()
        svc.excluded()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Svc.instrumented" in stage_names
    assert "Svc.excluded" not in stage_names


def test_narrative_class_skips_staticmethod() -> None:
    @narrative_class
    class Svc:
        def instance_method(self): pass

        @staticmethod
        def helper(): pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Svc().instance_method()
        Svc.helper()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Svc.instance_method" in stage_names
    assert "Svc.helper" not in stage_names


def test_narrative_class_skips_classmethod() -> None:
    @narrative_class
    class Factory:
        def build(self): pass

        @classmethod
        def create(cls): pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Factory().build()
        Factory.create()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Factory.build" in stage_names
    assert "Factory.create" not in stage_names


def test_narrative_class_skips_property() -> None:
    @narrative_class
    class Model:
        def process(self): pass

        @property
        def value(self): return 42

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        m = Model()
        m.process()
        _ = m.value

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Model.process" in stage_names
    assert "Model.value" not in stage_names


def test_narrative_class_does_not_wrap_inherited_methods() -> None:
    class Base:
        def inherited(self): pass

    @narrative_class
    class Child(Base):
        def own(self): pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        c = Child()
        c.own()
        c.inherited()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Child.own" in stage_names
    assert "Child.inherited" not in stage_names


# ── narrative_class — async methods ──────────────────────────────────────────

def test_narrative_class_wraps_async_method() -> None:
    @narrative_class
    class AsyncSvc:
        async def fetch(self): return "data"

    cap = AsyncCapturingRenderer()

    async def run():
        async with story("S", renderers=[cap]):
            return await AsyncSvc().fetch()

    result = asyncio.run(run())
    assert result == "data"
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "AsyncSvc.fetch" in stage_names


# ── narrative_class — outside-story guard ────────────────────────────────────

def test_narrative_class_method_outside_story_raises() -> None:
    @narrative_class
    class Svc:
        def do(self): pass

    with pytest.raises(RuntimeError, match="must run inside an active story"):
        Svc().do()


# ── instrument_module ─────────────────────────────────────────────────────────

def _make_module(name: str = "testmod") -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__name__ = name
    return mod


def test_instrument_module_wraps_functions() -> None:
    mod = _make_module()

    def greet(who: str) -> str:
        return f"hello {who}"
    greet.__module__ = mod.__name__
    mod.greet = greet

    instrument_module(mod)

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = mod.greet("world")

    assert result == "hello world"
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "greet" in stage_names


def test_instrument_module_applies_narrative_class_to_classes() -> None:
    mod = _make_module()

    class Service:
        def run(self): return "running"
    Service.__module__ = mod.__name__
    mod.Service = Service

    instrument_module(mod)

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        mod.Service().run()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Service.run" in stage_names


def test_instrument_module_skips_imported_symbols() -> None:
    import json
    mod = _make_module()
    mod.loads = json.loads  # imported, has __module__ == "json"

    instrument_module(mod)

    assert mod.loads is json.loads  # unchanged


def test_instrument_module_skips_private_names() -> None:
    mod = _make_module()

    def _helper(): return "priv"
    _helper.__module__ = mod.__name__
    mod._helper = _helper

    instrument_module(mod)

    assert mod._helper is _helper  # unchanged


def test_instrument_module_preserves_no_stage_functions() -> None:
    mod = _make_module()

    @no_stage
    def excluded(): return 1
    excluded.__module__ = mod.__name__
    mod.excluded = excluded

    instrument_module(mod)

    # Function not wrapped: calling outside a story must NOT raise RuntimeError
    assert mod.excluded() == 1


# ── auto_instrument ───────────────────────────────────────────────────────────

def test_auto_instrument_inserts_finder_into_meta_path() -> None:
    finder = auto_instrument(app_roots=["/nonexistent"])
    try:
        assert finder in sys.meta_path
    finally:
        sys.meta_path.remove(finder)


def test_auto_instrument_returns_removable_finder() -> None:
    finder = auto_instrument(app_roots=["/nonexistent"])
    sys.meta_path.remove(finder)
    assert finder not in sys.meta_path


def test_narrative_loader_instruments_module_on_exec(tmp_path) -> None:
    """_NarrativeLoader.exec_module must call instrument_module after loading."""
    import importlib.util

    src = tmp_path / "auto_test_mod.py"
    src.write_text("def process(x):\n    return x + 1\n")

    spec = importlib.util.spec_from_file_location("auto_test_mod", str(src))
    mod = importlib.util.module_from_spec(spec)

    loader = _NarrativeLoader(spec.loader)
    loader.exec_module(mod)

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = mod.process(3)

    assert result == 4
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "process" in stage_names
