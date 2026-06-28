from __future__ import annotations

import asyncio
import threading

import pytest

from runtime_narrative.analyzers.deduplication import DeduplicatingAnalyzer, _failure_key
from runtime_narrative.failure import FailureSummary


def _make_failure(*, error_type="ValueError", lineno=42, exception_chain="ValueError: bad"):
    return FailureSummary(
        error_type=error_type,
        error_message="bad",
        filename="/app/main.py",
        lineno=lineno,
        function="process",
        source_line="x = int(v)",
        exception_chain=exception_chain,
        exact_cause="...",
        traceback_text="Traceback:\n  ValueError: bad",
    )


class _FakeAnalyzer:
    def __init__(self, return_value="cached result"):
        self.call_count = 0
        self.return_value = return_value

    def analyze_failure(self, *, story_name, stage_name, failure, stage_timeline, progress_percent):
        self.call_count += 1
        return self.return_value


class _FakeAsyncAnalyzer(_FakeAnalyzer):
    async def analyze_failure_async(self, *, story_name, stage_name, failure, stage_timeline, progress_percent):
        self.call_count += 1
        return self.return_value


def _call(wrapper, failure):
    return wrapper.analyze_failure(
        story_name="s",
        stage_name="st",
        failure=failure,
        stage_timeline=[],
        progress_percent=50,
    )


async def _call_async(wrapper, failure):
    return await wrapper.analyze_failure_async(
        story_name="s",
        stage_name="st",
        failure=failure,
        stage_timeline=[],
        progress_percent=50,
    )


def test_cache_hit_skips_inner_call():
    inner = _FakeAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner)
    f = _make_failure()
    r1 = _call(wrapper, f)
    r2 = _call(wrapper, f)
    assert inner.call_count == 1
    assert r1 == r2 == "cached result"


def test_cache_miss_on_different_error():
    inner = _FakeAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner)
    _call(wrapper, _make_failure(lineno=1))
    _call(wrapper, _make_failure(lineno=99))
    assert inner.call_count == 2


def test_none_result_not_cached():
    inner = _FakeAnalyzer(return_value=None)
    wrapper = DeduplicatingAnalyzer(inner)
    f = _make_failure()
    _call(wrapper, f)
    _call(wrapper, f)
    assert inner.call_count == 2


def test_lru_eviction():
    inner = _FakeAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner, max_cache_size=2)
    _call(wrapper, _make_failure(lineno=1))  # cache: {1}
    _call(wrapper, _make_failure(lineno=2))  # cache: {1, 2}
    _call(wrapper, _make_failure(lineno=3))  # cache: {2, 3}, lineno=1 evicted
    _call(wrapper, _make_failure(lineno=1))  # miss — lineno=1 was evicted
    assert inner.call_count == 4


def test_failure_key_same_for_identical_failures():
    f1 = _make_failure()
    f2 = _make_failure()
    assert _failure_key(f1) == _failure_key(f2)


def test_failure_key_differs_for_different_lineno():
    assert _failure_key(_make_failure(lineno=1)) != _failure_key(_make_failure(lineno=2))


def test_async_delegates_to_inner_async():
    inner = _FakeAsyncAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner)
    f = _make_failure()
    result = asyncio.run(_call_async(wrapper, f))
    assert result == "cached result"
    assert inner.call_count == 1
    asyncio.run(_call_async(wrapper, f))
    assert inner.call_count == 1


def test_async_falls_back_to_sync_when_no_async_method():
    inner = _FakeAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner)
    f = _make_failure()
    result = asyncio.run(_call_async(wrapper, f))
    assert result == "cached result"
    assert inner.call_count == 1


def test_thread_safety_basic():
    inner = _FakeAnalyzer()
    wrapper = DeduplicatingAnalyzer(inner)
    f = _make_failure()
    results = []

    def worker():
        results.append(_call(wrapper, f))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r == "cached result" for r in results)
    assert inner.call_count in (1, 2)
