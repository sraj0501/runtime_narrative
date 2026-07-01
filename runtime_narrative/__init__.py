__version__ = "1.0.1"

from .analyzers import FailureAnalyzer, LLMFailureAnalyzer, OllamaFailureAnalyzer, DeduplicatingAnalyzer
from .context import has_active_story
from .decorators import runtime_narrative_stage, runtime_narrative_story
from .diagnostics import FailureDiagnosticsConfig, build_enriched_failure, effective_diagnostics_mode
from .events import (
    Event,
    FailureOccurred,
    LLMAnalysisReady,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from .instrumentation import auto_instrument, instrument_module, narrative_class, narrative_stage, no_stage
from .renderer.console import ConsoleRenderer
from .renderer.json_renderer import JsonRenderer, RotatingJsonRenderer
from .stage import stage
from .story import story, StoryRuntime

try:
    from .middleware import RuntimeNarrativeMiddleware
except ImportError:
    pass

try:
    from .renderer.otel_renderer import OtelRenderer
except ImportError:
    pass

try:
    from .renderer.otel_log_renderer import OtelLogRenderer
except ImportError:
    pass

try:
    from .renderer.otel_metrics_renderer import OtelMetricsRenderer
except ImportError:
    pass

try:
    from .renderer.prometheus_renderer import PrometheusRenderer
except ImportError:
    pass

try:
    from .analyzers.anthropic import AnthropicFailureAnalyzer
except ImportError:
    pass

try:
    from .middleware_django import RuntimeNarrativeDjangoMiddleware, RuntimeNarrativeDjangoSyncMiddleware
except ImportError:
    pass

try:
    from .celery import NarrativeTask, connect_narrative
except ImportError:
    pass

try:
    from .grpc_interceptor import RuntimeNarrativeInterceptor, RuntimeNarrativeAsyncInterceptor
except ImportError:
    pass

from .task_group import NarrativeTaskGroup, NarrativeTaskGroupError
from .testing import StoryRecorder

try:
    from .renderer.html_renderer import HtmlReportRenderer
except ImportError:
    pass

try:
    from .renderer.persistence_renderer import SqliteStoryRenderer
except ImportError:
    pass

try:
    from .renderer.alert_renderer import AlertRoutingRenderer, HttpWebhookDestination, SlackWebhookDestination
except ImportError:
    pass

__all__ = [
    "story",
    "StoryRuntime",
    "stage",
    "runtime_narrative_story",
    "runtime_narrative_stage",
    "narrative_class",
    "narrative_stage",
    "no_stage",
    "instrument_module",
    "auto_instrument",
    "has_active_story",
    "FailureAnalyzer",
    "LLMFailureAnalyzer",
    "OllamaFailureAnalyzer",
    "AnthropicFailureAnalyzer",
    "DeduplicatingAnalyzer",
    "RuntimeNarrativeMiddleware",
    "ConsoleRenderer",
    "JsonRenderer",
    "RotatingJsonRenderer",
    "OtelRenderer",
    "OtelLogRenderer",
    "OtelMetricsRenderer",
    "PrometheusRenderer",
    "Event",
    "StoryStarted",
    "StageStarted",
    "StageCompleted",
    "FailureOccurred",
    "StoryCompleted",
    "LLMAnalysisReady",
    "FailureDiagnosticsConfig",
    "build_enriched_failure",
    "effective_diagnostics_mode",
    "RuntimeNarrativeDjangoMiddleware",
    "RuntimeNarrativeDjangoSyncMiddleware",
    "NarrativeTask",
    "connect_narrative",
    "NarrativeTaskGroup",
    "NarrativeTaskGroupError",
    "RuntimeNarrativeInterceptor",
    "RuntimeNarrativeAsyncInterceptor",
    "StoryRecorder",
    "HtmlReportRenderer",
    "SqliteStoryRenderer",
    "AlertRoutingRenderer",
    "HttpWebhookDestination",
    "SlackWebhookDestination",
]
