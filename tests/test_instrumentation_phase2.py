from __future__ import annotations

import asyncio

import pytest

from runtime_narrative import narrative_class, narrative_stage, no_stage, stage, story
from tests.conftest import AsyncCapturingRenderer, CapturingRenderer


# ── narrative_stage standalone ────────────────────────────────────────────────

def test_narrative_stage_wraps_with_given_name() -> None:
    @narrative_stage("Process Order")
    def process(order):
        return order * 2

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = process(3)

    assert result == 6
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Process Order" in stage_names


def test_narrative_stage_no_name_uses_titlecased_function_name() -> None:
    @narrative_stage()
    def validate_order(order):
        return True

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        validate_order("x")

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Validate Order" in stage_names


def test_narrative_stage_standalone_preserves_return_value() -> None:
    @narrative_stage("Compute")
    def compute(x):
        return x ** 2

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        assert compute(5) == 25


def test_narrative_stage_standalone_async() -> None:
    @narrative_stage("Fetch Data")
    async def fetch():
        return "payload"

    cap = AsyncCapturingRenderer()

    async def run():
        async with story("S", renderers=[cap]):
            return await fetch()

    result = asyncio.run(run())
    assert result == "payload"
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Fetch Data" in stage_names


def test_narrative_stage_outside_story_raises() -> None:
    @narrative_stage("Work")
    def work():
        pass

    with pytest.raises(RuntimeError, match="must run inside an active story"):
        work()


# ── narrative_stage inside @narrative_class ───────────────────────────────────

def test_narrative_stage_overrides_default_name_in_narrative_class() -> None:
    @narrative_class
    class OrderService:
        @narrative_stage("Validate Order")
        def validate(self, order):
            return True

        def charge(self, order):
            return "charged"

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        svc = OrderService()
        svc.validate("ord-1")
        svc.charge("ord-1")

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Validate Order" in stage_names
    assert "OrderService.validate" not in stage_names
    assert "OrderService.charge" in stage_names


def test_narrative_stage_in_narrative_class_not_double_wrapped() -> None:
    call_count = 0

    @narrative_class
    class Svc:
        @narrative_stage("Step")
        def step(self):
            nonlocal call_count
            call_count += 1

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Svc().step()

    # Exactly one StageStarted for "Step"
    started = [e for e in cap.events if e.__class__.__name__ == "StageStarted" and e.stage_name == "Step"]
    assert len(started) == 1
    assert call_count == 1


def test_narrative_stage_in_narrative_class_async_override() -> None:
    @narrative_class
    class AsyncSvc:
        @narrative_stage("Load Records")
        async def load(self):
            return [1, 2, 3]

    cap = AsyncCapturingRenderer()

    async def run():
        async with story("S", renderers=[cap]):
            return await AsyncSvc().load()

    result = asyncio.run(run())
    assert result == [1, 2, 3]
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Load Records" in stage_names
    assert "AsyncSvc.load" not in stage_names


# ── narrative_class(instrument_classmethods=True) ─────────────────────────────

def test_instrument_classmethods_wraps_classmethod() -> None:
    @narrative_class(instrument_classmethods=True)
    class Factory:
        @classmethod
        def create(cls):
            return cls()

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Factory.create()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Factory.create" in stage_names


def test_instrument_classmethods_preserves_cls_arg() -> None:
    @narrative_class(instrument_classmethods=True)
    class Factory:
        @classmethod
        def create(cls):
            return cls.__name__

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = Factory.create()

    assert result == "Factory"


def test_instrument_classmethods_default_false_skips() -> None:
    @narrative_class
    class Factory:
        def build(self):
            pass

        @classmethod
        def create(cls):
            pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Factory().build()
        Factory.create()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Factory.build" in stage_names
    assert "Factory.create" not in stage_names


def test_instrument_classmethods_respects_no_stage() -> None:
    @narrative_class(instrument_classmethods=True)
    class Factory:
        @classmethod
        def create(cls):
            pass

        @classmethod
        @no_stage
        def internal(cls):
            return "raw"

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Factory.create()
        Factory.internal()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Factory.create" in stage_names
    assert "Factory.internal" not in stage_names


def test_instrument_classmethods_respects_narrative_stage_override() -> None:
    @narrative_class(instrument_classmethods=True)
    class Factory:
        @classmethod
        @narrative_stage("Build Widget")
        def create(cls):
            pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Factory.create()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Build Widget" in stage_names
    assert "Factory.create" not in stage_names


# ── narrative_class(instrument_staticmethods=True) ───────────────────────────

def test_instrument_staticmethods_wraps_staticmethod() -> None:
    @narrative_class(instrument_staticmethods=True)
    class Validator:
        @staticmethod
        def check(value):
            return value > 0

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        result = Validator.check(5)

    assert result is True
    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Validator.check" in stage_names


def test_instrument_staticmethods_default_false_skips() -> None:
    @narrative_class
    class Util:
        def run(self):
            pass

        @staticmethod
        def helper():
            pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Util().run()
        Util.helper()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Util.run" in stage_names
    assert "Util.helper" not in stage_names


def test_instrument_staticmethods_respects_no_stage() -> None:
    @narrative_class(instrument_staticmethods=True)
    class Util:
        @staticmethod
        def active():
            pass

        @staticmethod
        @no_stage
        def excluded():
            return 42

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Util.active()
        Util.excluded()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Util.active" in stage_names
    assert "Util.excluded" not in stage_names


def test_instrument_staticmethods_respects_narrative_stage_override() -> None:
    @narrative_class(instrument_staticmethods=True)
    class Util:
        @staticmethod
        @narrative_stage("Run Validation")
        def validate(data):
            return data

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        Util.validate("x")

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Run Validation" in stage_names
    assert "Util.validate" not in stage_names


# ── both flags together ───────────────────────────────────────────────────────

def test_instrument_both_classmethods_and_staticmethods() -> None:
    @narrative_class(instrument_classmethods=True, instrument_staticmethods=True)
    class Service:
        def instance_method(self):
            pass

        @classmethod
        def class_method(cls):
            pass

        @staticmethod
        def static_method():
            pass

    cap = CapturingRenderer()
    with story("S", renderers=[cap]):
        svc = Service()
        svc.instance_method()
        Service.class_method()
        Service.static_method()

    stage_names = [e.stage_name for e in cap.events if hasattr(e, "stage_name")]
    assert "Service.instance_method" in stage_names
    assert "Service.class_method" in stage_names
    assert "Service.static_method" in stage_names
