from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class StoryCompleted:
    story_id: str
    story_name: str
    success: bool
    progress_percent: int
    completed_stages: int
    total_stages: int
    timestamp: datetime


from typing import Union

Event = Union[StoryStarted, StageStarted, StageCompleted, FailureOccurred, StoryCompleted]
Renderer = Any
