from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..failure import FailureSummary

__all__ = ["FailureAnalyzer"]


@runtime_checkable
class FailureAnalyzer(Protocol):
    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]: ...
