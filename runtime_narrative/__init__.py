__version__ = "0.8.0"

from .analyzers import FailureAnalyzer, LLMFailureAnalyzer, OllamaFailureAnalyzer, DeduplicatingAnalyzer
from .decorators import runtime_narrative_stage, runtime_narrative_story
from .diagnostics import FailureDiagnosticsConfig, build_enriched_failure, effective_diagnostics_mode
from .events import LLMAnalysisReady
from .instrumentation import auto_instrument, instrument_module, narrative_class, narrative_stage, no_stage
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
    "FailureAnalyzer",
    "LLMFailureAnalyzer",
    "OllamaFailureAnalyzer",
    "AnthropicFailureAnalyzer",
    "DeduplicatingAnalyzer",
    "RuntimeNarrativeMiddleware",
    "JsonRenderer",
    "RotatingJsonRenderer",
    "OtelRenderer",
    "OtelLogRenderer",
    "OtelMetricsRenderer",
    "PrometheusRenderer",
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
]
