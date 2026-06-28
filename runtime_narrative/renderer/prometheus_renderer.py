from __future__ import annotations

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class PrometheusRenderer:
    """
    Renderer that emits runtime-narrative metrics to Prometheus.

    Requires the `prometheus` extra: pip install 'runtime-narrative[prometheus]'

    Metrics exported:
      narrative_story_duration_seconds  — Histogram (labels: story_name, success)
      narrative_stage_duration_seconds  — Histogram (labels: story_name, stage_name)
      narrative_story_failures_total    — Counter   (labels: story_name, error_type)
      narrative_story_total             — Counter   (labels: story_name, success)

    Pass a custom ``registry`` to isolate metrics in tests or multi-tenant setups.
    """

    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        if not _PROMETHEUS_AVAILABLE:
            raise ImportError(
                "prometheus-client is required for PrometheusRenderer. "
                "Install it with: pip install 'runtime-narrative[prometheus]'"
            )
        kw = {"registry": registry} if registry is not None else {}

        self._story_duration = Histogram(
            "narrative_story_duration_seconds",
            "Duration of narrative stories in seconds",
            ["story_name", "success"],
            **kw,
        )
        self._stage_duration = Histogram(
            "narrative_stage_duration_seconds",
            "Duration of narrative stages in seconds",
            ["story_name", "stage_name"],
            **kw,
        )
        self._story_failures = Counter(
            "narrative_story_failures_total",
            "Total narrative story failures",
            ["story_name", "error_type"],
            **kw,
        )
        self._story_total = Counter(
            "narrative_story_total",
            "Total narrative stories completed",
            ["story_name", "success"],
            **kw,
        )

        # story_id → (story_name, started_at timestamp)
        self._active: dict = {}

    def handle(self, event: object) -> None:
        name = event.__class__.__name__

        if name == "StoryStarted":
            self._active[event.story_id] = (event.story_name, event.timestamp)
            return

        if name == "StageCompleted":
            story_entry = self._active.get(event.story_id)
            story_name = story_entry[0] if story_entry else "unknown"
            self._stage_duration.labels(
                story_name=story_name,
                stage_name=event.stage_name,
            ).observe(event.duration_seconds)
            return

        if name == "FailureOccurred":
            self._story_failures.labels(
                story_name=event.story_name,
                error_type=event.error_type,
            ).inc()
            return

        if name == "StoryCompleted":
            entry = self._active.pop(event.story_id, None)
            if entry is not None:
                story_name, started_at = entry
                duration = (event.timestamp - started_at).total_seconds()
                success_label = "true" if event.success else "false"
                self._story_duration.labels(
                    story_name=story_name,
                    success=success_label,
                ).observe(duration)
                self._story_total.labels(
                    story_name=story_name,
                    success=success_label,
                ).inc()


__all__ = ["PrometheusRenderer"]
