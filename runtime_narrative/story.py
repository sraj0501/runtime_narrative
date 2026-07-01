from __future__ import annotations

import asyncio
import inspect
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from .context import current_stage_stack, current_story
from .diagnostics import FailureDiagnosticsConfig, build_enriched_failure
from .events import FailureOccurred, LLMAnalysisReady, StoryCompleted, StoryStarted, StageCompleted, StageStarted
from .failure import FailureSummary
from .stage import StageRecord


@dataclass
class StoryRuntime:
    name: str
    story_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.now)
    stages: list[StageRecord] = field(default_factory=list)
    renderers: Sequence[object] = field(default_factory=tuple)
    failed_stage_name: str | None = None
    declared_total_stages: int | None = field(default=None, repr=False)
    dry_run: bool = False
    _diag_config: Any = field(default=None, repr=False)
    parent_story_id: str | None = None
    root_story_id: str = ""
    failure_analyzer: Any = field(default=None, repr=False)

    def set_total_stages(self, n: int) -> None:
        self.declared_total_stages = n

    def emit(self, event: object) -> None:
        for renderer in self.renderers:
            try:
                renderer.handle(event)
            except Exception as exc:
                print(
                    f"[runtime-narrative] renderer {renderer.__class__.__name__!r} "
                    f"raised {exc.__class__.__name__} on {event.__class__.__name__}: {exc}",
                    file=sys.stderr,
                )

    async def emit_async(self, event: object) -> None:
        for renderer in self.renderers:
            handle = getattr(renderer, "handle", None)
            if handle is None:
                continue
            try:
                if inspect.iscoroutinefunction(handle):
                    await handle(event)
                else:
                    handle(event)
            except Exception as exc:
                print(
                    f"[runtime-narrative] renderer {renderer.__class__.__name__!r} "
                    f"raised {exc.__class__.__name__} on {event.__class__.__name__}: {exc}",
                    file=sys.stderr,
                )

    def register_stage(self, stage: StageRecord) -> None:
        self.stages.append(stage)

    def on_stage_started(self, stage: StageRecord) -> None:
        self.emit(StageStarted(
            story_id=self.story_id,
            stage_name=stage.name,
            timestamp=datetime.now(),
            stage_index=stage.stage_index,
            parent_stage_name=stage.parent_stage_name,
            story_name=self.name,
            root_story_id=self.root_story_id,
        ))

    async def on_stage_started_async(self, stage: StageRecord) -> None:
        await self.emit_async(StageStarted(
            story_id=self.story_id,
            stage_name=stage.name,
            timestamp=datetime.now(),
            stage_index=stage.stage_index,
            parent_stage_name=stage.parent_stage_name,
            story_name=self.name,
            root_story_id=self.root_story_id,
        ))

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
                stage_index=stage.stage_index,
                parent_stage_name=stage.parent_stage_name,
                story_name=self.name,
                root_story_id=self.root_story_id,
            )
        )

    async def on_stage_completed_async(self, stage: StageRecord) -> None:
        completed_at = datetime.now()
        duration_seconds = stage.duration_seconds
        if duration_seconds is None:
            duration_seconds = (completed_at - stage.started_at).total_seconds()
        await self.emit_async(
            StageCompleted(
                story_id=self.story_id,
                stage_name=stage.name,
                timestamp=completed_at,
                duration_seconds=duration_seconds,
                stage_index=stage.stage_index,
                parent_stage_name=stage.parent_stage_name,
                story_name=self.name,
                root_story_id=self.root_story_id,
            )
        )

    async def record_failure(
        self,
        exc: BaseException,
        *,
        stage_name: str | None = None,
    ) -> None:
        """Emit FailureOccurred for *exc* without affecting exception propagation.

        Use this in saga rollback handlers or other contexts where you drive the
        story context manager manually and need to record a failure without relying
        on ``__aexit__`` owning the exception lifecycle.
        """
        from .diagnostics import FailureDiagnosticsConfig
        exc_type = type(exc)
        tb = exc.__traceback__
        config = self._diag_config if self._diag_config is not None else FailureDiagnosticsConfig.from_env()
        enriched = await asyncio.to_thread(build_enriched_failure, exc_type, exc, tb, config=config)
        failed_stage = stage_name or self.failed_stage_name or (
            current_stage_stack.get()[-1].name if current_stage_stack.get() else "<unknown>"
        )
        timeline = self.build_stage_timeline()
        await self.emit_async(FailureOccurred(
            story_id=self.story_id,
            story_name=self.name,
            stage_name=failed_stage,
            error_type=enriched.summary.error_type,
            error_message=enriched.summary.error_message,
            filename=enriched.summary.filename,
            lineno=enriched.summary.lineno,
            function=enriched.summary.function,
            source_line=enriched.summary.source_line,
            exception_chain=enriched.summary.exception_chain,
            exact_cause=enriched.summary.exact_cause,
            llm_analysis=None,
            stage_timeline=timeline,
            progress_percent=self.progress_percent,
            completed_stages=self.completed_stages,
            total_stages=self.total_stages,
            timestamp=datetime.now(),
            traceback_text=enriched.summary.traceback_text,
            diagnostics_mode=enriched.diagnostics_mode,
            primary_frame_reason=enriched.primary_frame_reason,
            stack_frames=list(enriched.stack_frames),
            source_snippet=enriched.source_snippet,
            compressed_stack_summary=enriched.compressed_stack_summary,
            hidden_frame_count=enriched.hidden_frame_count,
            traceback_truncated=enriched.traceback_truncated,
            locals_by_frame=enriched.locals_by_frame,
            redaction_removed_keys=enriched.redaction_removed_keys,
            parent_story_id=self.parent_story_id,
            root_story_id=self.root_story_id,
        ))

    def build_stage_timeline(self) -> str:
        if not self.stages:
            return "<no stages>"

        rendered: list[str] = []
        for stage in self.stages:
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
        if self.declared_total_stages is not None:
            return self.declared_total_stages
        return len(self.stages)

    @property
    def progress_percent(self) -> int:
        total = self.declared_total_stages if self.declared_total_stages is not None else len(self.stages)
        if not total:
            return 0
        return int((self.completed_stages / total) * 100)


def _optional_normalized_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    return stripped or None


class story:
    def __init__(
        self,
        name: str,
        *,
        renderers: Sequence[object] | None = None,
        failure_analyzer: Any | None = None,
        background_analysis: bool = False,
        diagnostics_config: FailureDiagnosticsConfig | None = None,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: Sequence[str] | None = None,
        redact_extra: Sequence[str] | None = None,
        total_stages: int | None = None,
        dry_run: bool = False,
    ):
        from .renderer.console import ConsoleRenderer

        parent_runtime = current_story.get()

        if failure_analyzer is None and parent_runtime is not None:
            failure_analyzer = parent_runtime.failure_analyzer
        self.failure_analyzer = failure_analyzer
        self.background_analysis = background_analysis

        override_given = any(
            v is not None
            for v in (runtime_environment, failure_diagnostics, allow_rich_in_production, app_roots, redact_extra)
        )
        if diagnostics_config is not None:
            self._diag_config = diagnostics_config
        elif parent_runtime is not None and not override_given:
            self._diag_config = parent_runtime._diag_config
        else:
            base = parent_runtime._diag_config if parent_runtime is not None else FailureDiagnosticsConfig.from_env()
            roots: tuple[str, ...] | None = None
            if app_roots is not None:
                roots = tuple(os.path.abspath(os.path.expanduser(str(p))) for p in app_roots)
            extra: tuple[str, ...] | None = None
            if redact_extra is not None:
                extra = tuple(str(s).lower() for s in redact_extra)
            self._diag_config = FailureDiagnosticsConfig.merge(
                base,
                runtime_environment=_optional_normalized_str(runtime_environment),
                failure_diagnostics=_optional_normalized_str(failure_diagnostics),
                allow_rich_in_production=allow_rich_in_production,
                app_roots=roots,
                redact_extra=extra,
            )

        if renderers is None and parent_runtime is not None:
            renderers = parent_runtime.renderers

        self.runtime = StoryRuntime(
            name=name,
            renderers=renderers or (ConsoleRenderer(),),
            declared_total_stages=total_stages,
            dry_run=dry_run,
            _diag_config=self._diag_config,
            failure_analyzer=failure_analyzer,
            parent_story_id=parent_runtime.story_id if parent_runtime is not None else None,
            root_story_id=parent_runtime.root_story_id if parent_runtime is not None else "",
        )
        if not self.runtime.root_story_id:
            self.runtime.root_story_id = self.runtime.story_id
        self._story_token = None
        self._stack_token = None

    def _make_failure_occurred(
        self,
        *,
        summary: FailureSummary,
        failed_stage_name: str,
        stage_timeline: str,
        llm_analysis: str | None,
        diagnostics_mode: str,
        primary_frame_reason: str,
        stack_frames: list,
        source_snippet: str | None,
        compressed_stack_summary: str,
        hidden_frame_count: int,
        traceback_truncated: bool,
        locals_by_frame: dict | None,
        redaction_removed_keys: int,
    ) -> FailureOccurred:
        return FailureOccurred(
            story_id=self.runtime.story_id,
            story_name=self.runtime.name,
            stage_name=failed_stage_name,
            error_type=summary.error_type,
            error_message=summary.error_message,
            filename=summary.filename,
            lineno=summary.lineno,
            function=summary.function,
            source_line=summary.source_line,
            exception_chain=summary.exception_chain,
            exact_cause=summary.exact_cause,
            llm_analysis=llm_analysis,
            stage_timeline=stage_timeline,
            progress_percent=self.runtime.progress_percent,
            completed_stages=self.runtime.completed_stages,
            total_stages=self.runtime.total_stages,
            timestamp=datetime.now(),
            traceback_text=summary.traceback_text,
            diagnostics_mode=diagnostics_mode,
            primary_frame_reason=primary_frame_reason,
            stack_frames=list(stack_frames),
            source_snippet=source_snippet,
            compressed_stack_summary=compressed_stack_summary,
            hidden_frame_count=hidden_frame_count,
            traceback_truncated=traceback_truncated,
            locals_by_frame=locals_by_frame,
            redaction_removed_keys=redaction_removed_keys,
            parent_story_id=self.runtime.parent_story_id,
            root_story_id=self.runtime.root_story_id,
        )

    def __enter__(self) -> StoryRuntime:
        self._story_token = current_story.set(self.runtime)
        self._stack_token = current_stage_stack.set([])
        self.runtime.emit(
            StoryStarted(
                story_id=self.runtime.story_id,
                story_name=self.runtime.name,
                timestamp=datetime.now(),
                parent_story_id=self.runtime.parent_story_id,
                root_story_id=self.runtime.root_story_id,
            )
        )
        return self.runtime

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and exc is not None:
            enriched = build_enriched_failure(exc_type, exc, tb, config=self._diag_config)
            failed_stage_name = self.runtime.failed_stage_name or (
                current_stage_stack.get()[-1].name if current_stage_stack.get() else "<unknown>"
            )
            stage_timeline = self.runtime.build_stage_timeline()
            failure = enriched.summary
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
                self._make_failure_occurred(
                    summary=failure,
                    failed_stage_name=failed_stage_name,
                    stage_timeline=stage_timeline,
                    llm_analysis=llm_analysis,
                    diagnostics_mode=enriched.diagnostics_mode,
                    primary_frame_reason=enriched.primary_frame_reason,
                    stack_frames=enriched.stack_frames,
                    source_snippet=enriched.source_snippet,
                    compressed_stack_summary=enriched.compressed_stack_summary,
                    hidden_frame_count=enriched.hidden_frame_count,
                    traceback_truncated=enriched.traceback_truncated,
                    locals_by_frame=enriched.locals_by_frame,
                    redaction_removed_keys=enriched.redaction_removed_keys,
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
                duration_seconds=(datetime.now() - self.runtime.started_at).total_seconds(),
                parent_story_id=self.runtime.parent_story_id,
                root_story_id=self.runtime.root_story_id,
            )
        )

        if self._stack_token is not None:
            current_stage_stack.reset(self._stack_token)
        if self._story_token is not None:
            current_story.reset(self._story_token)
        return False

    async def __aenter__(self) -> StoryRuntime:
        self._story_token = current_story.set(self.runtime)
        self._stack_token = current_stage_stack.set([])
        await self.runtime.emit_async(
            StoryStarted(
                story_id=self.runtime.story_id,
                story_name=self.runtime.name,
                timestamp=datetime.now(),
                parent_story_id=self.runtime.parent_story_id,
                root_story_id=self.runtime.root_story_id,
            )
        )
        return self.runtime

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and exc is not None:
            enriched = await asyncio.to_thread(
                build_enriched_failure, exc_type, exc, tb, config=self._diag_config
            )
            failed_stage_name = self.runtime.failed_stage_name or (
                current_stage_stack.get()[-1].name if current_stage_stack.get() else "<unknown>"
            )
            stage_timeline = self.runtime.build_stage_timeline()
            failure = enriched.summary

            if self.background_analysis and self.failure_analyzer is not None:
                await self.runtime.emit_async(
                    self._make_failure_occurred(
                        summary=failure,
                        failed_stage_name=failed_stage_name,
                        stage_timeline=stage_timeline,
                        llm_analysis=None,
                        diagnostics_mode=enriched.diagnostics_mode,
                        primary_frame_reason=enriched.primary_frame_reason,
                        stack_frames=enriched.stack_frames,
                        source_snippet=enriched.source_snippet,
                        compressed_stack_summary=enriched.compressed_stack_summary,
                        hidden_frame_count=enriched.hidden_frame_count,
                        traceback_truncated=enriched.traceback_truncated,
                        locals_by_frame=enriched.locals_by_frame,
                        redaction_removed_keys=enriched.redaction_removed_keys,
                    )
                )
                asyncio.create_task(
                    self._run_background_analysis(failure, failed_stage_name, stage_timeline)
                )
            else:
                llm_analysis = await self._call_analyzer_async(
                    failure=failure,
                    failed_stage_name=failed_stage_name,
                    stage_timeline=stage_timeline,
                )
                await self.runtime.emit_async(
                    self._make_failure_occurred(
                        summary=failure,
                        failed_stage_name=failed_stage_name,
                        stage_timeline=stage_timeline,
                        llm_analysis=llm_analysis,
                        diagnostics_mode=enriched.diagnostics_mode,
                        primary_frame_reason=enriched.primary_frame_reason,
                        stack_frames=enriched.stack_frames,
                        source_snippet=enriched.source_snippet,
                        compressed_stack_summary=enriched.compressed_stack_summary,
                        hidden_frame_count=enriched.hidden_frame_count,
                        traceback_truncated=enriched.traceback_truncated,
                        locals_by_frame=enriched.locals_by_frame,
                        redaction_removed_keys=enriched.redaction_removed_keys,
                    )
                )

        await self.runtime.emit_async(
            StoryCompleted(
                story_id=self.runtime.story_id,
                story_name=self.runtime.name,
                success=exc_type is None,
                progress_percent=self.runtime.progress_percent,
                completed_stages=self.runtime.completed_stages,
                total_stages=self.runtime.total_stages,
                timestamp=datetime.now(),
                duration_seconds=(datetime.now() - self.runtime.started_at).total_seconds(),
                parent_story_id=self.runtime.parent_story_id,
                root_story_id=self.runtime.root_story_id,
            )
        )

        if self._stack_token is not None:
            current_stage_stack.reset(self._stack_token)
        if self._story_token is not None:
            current_story.reset(self._story_token)
        return False

    async def _call_analyzer_async(
        self,
        *,
        failure: Any,
        failed_stage_name: str,
        stage_timeline: str,
    ) -> str | None:
        if self.failure_analyzer is None:
            return None
        analyze_async = getattr(self.failure_analyzer, "analyze_failure_async", None)
        if callable(analyze_async):
            return await analyze_async(
                story_name=self.runtime.name,
                stage_name=failed_stage_name,
                failure=failure,
                stage_timeline=stage_timeline,
                progress_percent=self.runtime.progress_percent,
            )
        analyze_sync = getattr(self.failure_analyzer, "analyze_failure", None)
        if callable(analyze_sync):
            from functools import partial
            fn = partial(
                analyze_sync,
                story_name=self.runtime.name,
                stage_name=failed_stage_name,
                failure=failure,
                stage_timeline=stage_timeline,
                progress_percent=self.runtime.progress_percent,
            )
            return await asyncio.to_thread(fn)
        return None

    async def _run_background_analysis(
        self,
        failure: Any,
        failed_stage_name: str,
        stage_timeline: str,
    ) -> None:
        llm_analysis = await self._call_analyzer_async(
            failure=failure,
            failed_stage_name=failed_stage_name,
            stage_timeline=stage_timeline,
        )
        if llm_analysis:
            await self.runtime.emit_async(
                LLMAnalysisReady(
                    story_id=self.runtime.story_id,
                    story_name=self.runtime.name,
                    stage_name=failed_stage_name,
                    llm_analysis=llm_analysis,
                    timestamp=datetime.now(),
                )
            )
