from __future__ import annotations

import asyncio
import hashlib
import threading
from collections import OrderedDict
from typing import Optional

from ..failure import FailureSummary


def _failure_key(failure: FailureSummary) -> str:
    return hashlib.sha256(
        f"{failure.error_type}:{failure.filename}:{failure.lineno}:{failure.exception_chain}".encode()
    ).hexdigest()


class DeduplicatingAnalyzer:
    def __init__(self, inner, *, max_cache_size: int = 256) -> None:
        self._inner = inner
        self._max_cache_size = max_cache_size
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def analyze_failure(
        self,
        *,
        story_name,
        stage_name,
        failure,
        stage_timeline,
        progress_percent,
    ) -> Optional[str]:
        key = _failure_key(failure)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]

        result = self._inner.analyze_failure(
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
        )

        if result is not None:
            with self._lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                if len(self._cache) > self._max_cache_size:
                    self._cache.popitem(last=False)

        return result

    async def analyze_failure_async(
        self,
        *,
        story_name,
        stage_name,
        failure,
        stage_timeline,
        progress_percent,
    ) -> Optional[str]:
        key = _failure_key(failure)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]

        if hasattr(self._inner, "analyze_failure_async"):
            result = await self._inner.analyze_failure_async(
                story_name=story_name,
                stage_name=stage_name,
                failure=failure,
                stage_timeline=stage_timeline,
                progress_percent=progress_percent,
            )
        else:
            result = await asyncio.to_thread(
                self._inner.analyze_failure,
                story_name=story_name,
                stage_name=stage_name,
                failure=failure,
                stage_timeline=stage_timeline,
                progress_percent=progress_percent,
            )

        if result is not None:
            with self._lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                if len(self._cache) > self._max_cache_size:
                    self._cache.popitem(last=False)

        return result


__all__ = ["DeduplicatingAnalyzer"]
