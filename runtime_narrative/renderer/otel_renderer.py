from __future__ import annotations

from datetime import datetime

try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def _to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1e9)


class OtelRenderer:
    """
    Renderer that maps runtime-narrative events to OpenTelemetry spans.

    Requires the `otel` extra: pip install 'runtime-narrative[otel]'

    Each story becomes a root span; each stage becomes a child span. If the
    same stage name is used twice within one story (e.g. a retry loop), the
    first open span is ended before the second is started.
    """

    def __init__(
        self,
        *,
        tracer_provider=None,
        tracer_name: str = "runtime_narrative",
        max_attribute_length: int = 8192,
        min_duration_ms: float = 0.0,
        exclude_stages: set[str] | frozenset[str] | None = None,
    ) -> None:
        if not _OTEL_AVAILABLE:
            raise ImportError(
                "opentelemetry-api and opentelemetry-sdk are required for OtelRenderer. "
                "Install them with: pip install 'runtime-narrative[otel]'"
            )
        provider = tracer_provider or trace.get_tracer_provider()
        self._tracer = provider.get_tracer(tracer_name)
        self._max_attr = max_attribute_length
        self._min_duration_ns = int(min_duration_ms * 1_000_000)
        self._exclude_stages: frozenset[str] = frozenset(exclude_stages or ())
        # keyed by story_id
        self._story_spans: dict = {}
        # keyed by (story_id, stage_name)
        self._stage_spans: dict = {}

    def _trunc(self, value: str | None) -> str:
        if value is None:
            return ""
        if len(value) <= self._max_attr:
            return value
        return value[: self._max_attr] + "[truncated]"

    def handle(self, event: object) -> None:
        name = event.__class__.__name__

        if name == "StoryStarted":
            span = self._tracer.start_span(
                event.story_name,
                start_time=_to_ns(event.timestamp),
            )
            self._story_spans[event.story_id] = span
            return

        if name == "StageStarted":
            if event.stage_name in self._exclude_stages:
                return
            story_span = self._story_spans.get(event.story_id)
            ctx = trace.set_span_in_context(story_span) if story_span else None
            key = (event.story_id, event.stage_name)
            existing = self._stage_spans.pop(key, None)
            if existing is not None:
                existing.end(end_time=_to_ns(event.timestamp))
            span = self._tracer.start_span(
                event.stage_name,
                context=ctx,
                start_time=_to_ns(event.timestamp),
            )
            self._stage_spans[key] = span
            return

        if name == "StageCompleted":
            key = (event.story_id, event.stage_name)
            span = self._stage_spans.pop(key, None)
            if span is not None:
                duration_ns = int(event.duration_seconds * 1_000_000_000)
                if self._min_duration_ns > 0 and duration_ns < self._min_duration_ns:
                    # abandon span — never call end(), so it is never exported
                    return
                span.end(end_time=_to_ns(event.timestamp))
            return

        if name == "FailureOccurred":
            story_span = self._story_spans.get(event.story_id)
            if story_span is not None:
                story_span.set_status(StatusCode.ERROR, event.error_message)
                story_span.set_attribute("error.type", event.error_type)
                story_span.set_attribute("error.message", self._trunc(event.error_message))
                story_span.set_attribute("code.filepath", event.filename)
                story_span.set_attribute("code.lineno", event.lineno)
                story_span.set_attribute("code.function", event.function)
                story_span.set_attribute("narrative.stage_name", event.stage_name)
                story_span.set_attribute("narrative.diagnostics_mode", event.diagnostics_mode)
                story_span.set_attribute("narrative.exception_chain", self._trunc(event.exception_chain))
                story_span.set_attribute("narrative.exact_cause", self._trunc(event.exact_cause))
                story_span.set_attribute("narrative.stage_timeline", self._trunc(event.stage_timeline))
                tb = getattr(event, "traceback_text", None)
                if tb:
                    story_span.set_attribute("error.stack_trace", self._trunc(tb))
            # FailureOccurred is emitted instead of StageCompleted for the failing stage,
            # so we must explicitly end and mark the open stage span as ERROR.
            key = (event.story_id, event.stage_name)
            stage_span = self._stage_spans.pop(key, None)
            if stage_span is not None:
                stage_span.set_status(StatusCode.ERROR, event.error_message)
                stage_span.end(end_time=_to_ns(event.timestamp))
            return

        if name == "LLMAnalysisReady":
            story_span = self._story_spans.get(event.story_id)
            if story_span is not None:
                story_span.add_event(
                    "llm_analysis_ready",
                    attributes={
                        "narrative.llm_analysis": self._trunc(event.llm_analysis),
                        "narrative.stage_name": event.stage_name,
                    },
                    timestamp=_to_ns(event.timestamp),
                )
            return

        if name == "StoryCompleted":
            span = self._story_spans.pop(event.story_id, None)
            if span is not None:
                if event.success:
                    span.set_status(StatusCode.OK)
                span.set_attribute("narrative.progress_percent", event.progress_percent)
                span.set_attribute("narrative.completed_stages", event.completed_stages)
                span.set_attribute("narrative.total_stages", event.total_stages)
                span.end(end_time=_to_ns(event.timestamp))


__all__ = ["OtelRenderer"]
