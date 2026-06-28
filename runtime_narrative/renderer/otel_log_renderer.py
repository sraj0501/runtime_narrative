from __future__ import annotations

from datetime import datetime

try:
    from opentelemetry._logs import get_logger_provider, SeverityNumber, LogRecord as OtelLogRecord
    from opentelemetry import trace as _otel_trace
    _OTEL_LOGS_AVAILABLE = True
except ImportError:
    _OTEL_LOGS_AVAILABLE = False


def _to_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1e9)


class OtelLogRenderer:

    def __init__(self, *, logger_provider=None, logger_name: str = "runtime_narrative") -> None:
        if not _OTEL_LOGS_AVAILABLE:
            raise ImportError(
                "opentelemetry-api and opentelemetry-sdk are required for OtelLogRenderer. "
                "Install them with: pip install 'runtime-narrative[otel]'"
            )
        provider = logger_provider or get_logger_provider()
        self._logger = provider.get_logger(logger_name)

    def _emit(self, timestamp: datetime, severity, body: str, attributes: dict) -> None:
        span = _otel_trace.get_current_span()
        ctx = span.get_span_context()
        record = OtelLogRecord(
            timestamp=_to_ns(timestamp),
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            trace_flags=ctx.trace_flags,
            severity_number=severity,
            body=body,
            attributes=attributes,
        )
        self._logger.emit(record)

    def handle(self, event: object) -> None:
        name = event.__class__.__name__

        if name == "StoryStarted":
            self._emit(
                event.timestamp,
                SeverityNumber.INFO,
                f"Story started: {event.story_name}",
                {
                    "narrative.story_id": event.story_id,
                    "narrative.story_name": event.story_name,
                },
            )
            return

        if name == "StageStarted":
            self._emit(
                event.timestamp,
                SeverityNumber.DEBUG,
                f"Stage started: {event.stage_name}",
                {
                    "narrative.story_id": event.story_id,
                    "narrative.stage_name": event.stage_name,
                    "narrative.stage_index": event.stage_index,
                },
            )
            return

        if name == "StageCompleted":
            self._emit(
                event.timestamp,
                SeverityNumber.DEBUG,
                f"Stage completed: {event.stage_name} ({event.duration_seconds:.3f}s)",
                {
                    "narrative.story_id": event.story_id,
                    "narrative.stage_name": event.stage_name,
                    "narrative.duration_seconds": event.duration_seconds,
                },
            )
            return

        if name == "FailureOccurred":
            attrs = {
                "narrative.story_id": event.story_id,
                "narrative.story_name": event.story_name,
                "narrative.stage_name": event.stage_name,
                "error.type": event.error_type,
                "error.message": event.error_message,
                "code.filepath": event.filename,
                "code.lineno": event.lineno,
                "code.function": event.function,
                "narrative.diagnostics_mode": event.diagnostics_mode,
            }
            if event.exception_chain:
                attrs["narrative.exception_chain"] = event.exception_chain
            if event.exact_cause:
                attrs["narrative.exact_cause"] = event.exact_cause
            tb = getattr(event, "traceback_text", None)
            if tb:
                attrs["error.stack_trace"] = tb
            self._emit(event.timestamp, SeverityNumber.ERROR, event.error_message, attrs)
            return

        if name == "LLMAnalysisReady":
            self._emit(
                event.timestamp,
                SeverityNumber.INFO,
                f"LLM analysis ready for {event.story_name}",
                {
                    "narrative.story_id": event.story_id,
                    "narrative.story_name": event.story_name,
                    "narrative.stage_name": event.stage_name,
                    "narrative.llm_analysis": event.llm_analysis or "",
                },
            )
            return

        if name == "StoryCompleted":
            self._emit(
                event.timestamp,
                SeverityNumber.INFO,
                f"Story completed: {event.story_name}",
                {
                    "narrative.story_id": event.story_id,
                    "narrative.story_name": event.story_name,
                    "narrative.success": event.success,
                    "narrative.completed_stages": event.completed_stages,
                    "narrative.total_stages": event.total_stages,
                },
            )


__all__ = ["OtelLogRenderer"]
