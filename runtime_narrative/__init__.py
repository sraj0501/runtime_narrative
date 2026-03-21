__version__ = "0.1.0"

from .analyzers import LLMFailureAnalyzer, OllamaFailureAnalyzer
from .decorators import runtime_narrative_stage, runtime_narrative_story
from .renderer.json_renderer import JsonRenderer
from .stage import stage
from .story import story

try:
    from .middleware import RuntimeNarrativeMiddleware
except ImportError:
    pass

__all__ = [
    "story",
    "stage",
    "runtime_narrative_story",
    "runtime_narrative_stage",
    "LLMFailureAnalyzer",
    "OllamaFailureAnalyzer",
    "RuntimeNarrativeMiddleware",
    "JsonRenderer",
]
