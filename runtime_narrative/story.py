from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from .context import current_stage_stack, current_story
from .events import FailureOccurred, StoryCompleted, StoryStarted, StageCompleted, StageStarted
from .failure import summarize_exception
from .stage import StageRecord


@dataclass
class StoryRuntime:
    name: str
    story_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.now)
    stages: list[StageRecord] = field(default_factory=list)
    renderers: Sequence[object] = field(default_factory=tuple)
    failed_stage_name: str | None = None

    def emit(self, event: object) -> None:
        for renderer in self.renderers:
            renderer.handle(event)

    def register_stage(self, stage: StageRecord) -> None:
        self.stages.append(stage)

    def on_stage_started(self, stage: StageRecord) -> None:
        self.emit(StageStarted(story_id=self.story_id, stage_name=stage.name, timestamp=datetime.now()))

    def on_stage_completed(self, stage: StageRecord) -> None:
        completed_at = datetime.now()
        duration_seconds = stage.duration_seconds
        if duration_seconds is None:
            duration_seconds = (completed_at - stage.started_at).total_seconds()
        self.emit(
            StageCompleted(
                story_id=self.story_id,
                stage_name=stage.name,
                timestamp=completed_at,
                duration_seconds=duration_seconds,
            )
        )

    def build_stage_timeline(self) -> str:
        if not self.stages:
            return "<no stages>"

        rendered: list[str] = []
        for stage in self.stages[-5:]:
            if stage.completed:
                duration = f"{stage.duration_seconds:.3f}s" if stage.duration_seconds is not None else "n/a"
                rendered.append(f"{stage.name}=completed ({duration})")
            elif stage.failed:
                duration = f"{stage.duration_seconds:.3f}s" if stage.duration_seconds is not None else "n/a"
                rendered.append(f"{stage.name}=failed ({duration})")
            else:
                rendered.append(f"{stage.name}=in-progress")
        return " | ".join(rendered)

    @property
    def completed_stages(self) -> int:
        return sum(1 for s in self.stages if s.completed)

    @property
    def total_stages(self) -> int:
        return len(self.stages)

    @property
    def progress_percent(self) -> int:
        if not self.total_stages:
            return 0
        return int((self.completed_stages / self.total_stages) * 100)


class story:
    def __init__(
        self,
        name: str,
        *,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
    ):
        from .renderer.console import ConsoleRenderer

        self.runtime = StoryRuntime(name=name, renderers=renderers or (ConsoleRenderer(),))
        self.failure_analyzer = failure_analyzer
        self._story_token = None
        self._stack_token = None

    def __enter__(self) -> StoryRuntime:
        self._story_token = current_story.set(self.runtime)
        self._stack_token = current_stage_stack.set([])
        self.runtime.emit(
            StoryStarted(
                story_id=self.runtime.story_id,
                story_name=self.runtime.name,
                timestamp=datetime.now(),
            )
        )
        return self.runtime

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and exc is not None:
            failure = summarize_exception(exc_type, exc, tb)
            failed_stage_name = self.runtime.failed_stage_name or (
                current_stage_stack.get()[-1].name if current_stage_stack.get() else "<unknown>"
            )
            stage_timeline = self.runtime.build_stage_timeline()
            llm_analysis = None
            if self.failure_analyzer is not None:
                analyze_fn = getattr(self.failure_analyzer, "analyze_failure", None)
                if callable(analyze_fn):
                    llm_analysis = analyze_fn(
                        story_name=self.runtime.name,
                        stage_name=failed_stage_name,
                        failure=failure,
                        stage_timeline=stage_timeline,
                        progress_percent=self.runtime.progress_percent,
                    )
            self.runtime.emit(
                FailureOccurred(
                    story_id=self.runtime.story_id,
                    story_name=self.runtime.name,
                    stage_name=failed_stage_name,
                    error_type=failure.error_type,
                    error_message=failure.error_message,
                    filename=failure.filename,
                    lineno=failure.lineno,
                    function=failure.function,
                    source_line=failure.source_line,
                    exception_chain=failure.exception_chain,
                    exact_cause=failure.exact_cause,
                    llm_analysis=llm_analysis,
                    stage_timeline=stage_timeline,
                    progress_percent=self.runtime.progress_percent,
                    completed_stages=self.runtime.completed_stages,
                    total_stages=self.runtime.total_stages,
                    timestamp=datetime.now(),
                    traceback_text=failure.traceback_text,
                )
            )

        self.runtime.emit(
            StoryCompleted(
                story_id=self.runtime.story_id,
                story_name=self.runtime.name,
                success=exc_type is None,
                progress_percent=self.runtime.progress_percent,
                completed_stages=self.runtime.completed_stages,
                total_stages=self.runtime.total_stages,
                timestamp=datetime.now(),
            )
        )

        if self._stack_token is not None:
            current_stage_stack.reset(self._stack_token)
        if self._story_token is not None:
            current_story.reset(self._story_token)
        return False
