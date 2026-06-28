from __future__ import annotations

try:
    from opentelemetry import metrics as _otel_metrics
    _OTEL_METRICS_AVAILABLE = True
except ImportError:
    _OTEL_METRICS_AVAILABLE = False


class OtelMetricsRenderer:
    def __init__(
        self,
        *,
        meter_provider=None,
        meter_name: str = "runtime_narrative",
    ) -> None:
        if not _OTEL_METRICS_AVAILABLE:
            raise ImportError(
                "opentelemetry-api and opentelemetry-sdk are required for OtelMetricsRenderer. "
                "Install them with: pip install 'runtime-narrative[otel]'"
            )
        mp = meter_provider or _otel_metrics.get_meter_provider()
        meter = mp.get_meter(meter_name)

        self._stage_duration = meter.create_histogram(
            "narrative.stage.duration",
            unit="s",
            description="Stage execution duration in seconds",
        )
        self._story_duration = meter.create_histogram(
            "narrative.story.duration",
            unit="s",
            description="Story execution duration in seconds",
        )
        self._story_failures = meter.create_counter(
            "narrative.story.failures",
            unit="1",
            description="Number of story failures by story and error type",
        )
        self._llm_latency = meter.create_histogram(
            "narrative.llm.analysis_latency",
            unit="s",
            description="Time from failure to LLM analysis completion in seconds",
        )

        self._story_starts: dict = {}
        self._failure_times: dict = {}

    def handle(self, event: object) -> None:
        name = event.__class__.__name__

        if name == "StoryStarted":
            self._story_starts[event.story_id] = (event.story_name, event.timestamp)
            return

        if name == "StageCompleted":
            entry = self._story_starts.get(event.story_id)
            story_name = entry[0] if entry else "unknown"
            self._stage_duration.record(
                event.duration_seconds,
                {"story_name": story_name, "stage_name": event.stage_name},
            )
            return

        if name == "FailureOccurred":
            entry = self._story_starts.get(event.story_id)
            story_name = entry[0] if entry else "unknown"
            self._failure_times[event.story_id] = event.timestamp
            self._story_failures.add(1, {"story_name": story_name, "error_type": event.error_type})
            return

        if name == "LLMAnalysisReady":
            failure_time = self._failure_times.pop(event.story_id, None)
            if failure_time is not None:
                latency = (event.timestamp - failure_time).total_seconds()
                entry = self._story_starts.get(event.story_id)
                story_name = entry[0] if entry else "unknown"
                self._llm_latency.record(latency, {"story_name": story_name})
            return

        if name == "StoryCompleted":
            entry = self._story_starts.pop(event.story_id, None)
            self._failure_times.pop(event.story_id, None)
            if entry is not None:
                story_name, started_at = entry
                duration = (event.timestamp - started_at).total_seconds()
                self._story_duration.record(
                    duration,
                    {"story_name": story_name, "success": str(event.success).lower()},
                )


__all__ = ["OtelMetricsRenderer"]
