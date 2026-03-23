from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StoryStarted:
    story_id: str
    story_name: str
    timestamp: datetime


@dataclass
class StageStarted:
    story_id: str
    stage_name: str
    timestamp: datetime


@dataclass
class StageCompleted:
    story_id: str
    stage_name: str
    timestamp: datetime
    duration_seconds: float


@dataclass
class FailureOccurred:
    story_id: str
    story_name: str
    stage_name: str
    error_type: str
    error_message: str
    filename: str
    lineno: int
    function: str
    source_line: str
    exception_chain: str
    exact_cause: str
    llm_analysis: str | None
    stage_timeline: str
    progress_percent: int
    completed_stages: int
    total_stages: int
    timestamp: datetime
    traceback_text: str
    diagnostics_mode: str = "lean"
    primary_frame_reason: str = "leaf"
    stack_frames: list[dict[str, Any]] = field(default_factory=list)
    source_snippet: str | None = None
    compressed_stack_summary: str = ""
    hidden_frame_count: int = 0
    traceback_truncated: bool = False
    locals_by_frame: dict[str, Any] | None = None
    redaction_removed_keys: int = 0


@dataclass
class StoryCompleted:
    story_id: str
    story_name: str
    success: bool
    progress_percent: int
    completed_stages: int
    total_stages: int
    timestamp: datetime


@dataclass
class LLMAnalysisReady:
    story_id: str
    story_name: str
    stage_name: str
    llm_analysis: str
    timestamp: datetime


from typing import Union

Event = Union[StoryStarted, StageStarted, StageCompleted, FailureOccurred, StoryCompleted, LLMAnalysisReady]
Renderer = Any
