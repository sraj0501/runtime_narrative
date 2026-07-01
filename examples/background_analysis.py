"""Demonstrates background_analysis=True — non-blocking LLM failure analysis.

With background_analysis=True, FailureOccurred is emitted immediately (llm_analysis=None)
and the LLM call runs as an asyncio.Task. When it completes, LLMAnalysisReady is
emitted with the result. The story exit does not block waiting for the LLM.

Requires: RUNTIME_NARRATIVE_MODEL set to an Ollama model name, or swap in
AnthropicFailureAnalyzer with ANTHROPIC_API_KEY.

Run (Ollama):
    RUNTIME_NARRATIVE_MODEL=llama3 uv run python examples/background_analysis.py

Run (Anthropic):
    ANTHROPIC_API_KEY=sk-ant-... uv run python examples/background_analysis.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from runtime_narrative import OllamaFailureAnalyzer, stage, story

load_dotenv(Path(__file__).resolve().parent / ".env")

_model = os.getenv("RUNTIME_NARRATIVE_MODEL")
_endpoint = os.getenv("RUNTIME_NARRATIVE_ENDPOINT", "http://127.0.0.1:11434/api/generate")

if _model:
    analyzer = OllamaFailureAnalyzer(model=_model, endpoint=_endpoint, timeout_seconds=60.0)
else:
    print("Set RUNTIME_NARRATIVE_MODEL to enable LLM analysis. Running without analyzer.\n")
    analyzer = None


async def main() -> None:
    try:
        async with story(
            "Batch Import",
            failure_analyzer=analyzer,
            background_analysis=True,  # FailureOccurred fires immediately; LLMAnalysisReady follows
            total_stages=3,
        ):
            async with stage("Read Source File"):
                await asyncio.sleep(0.01)
                rows = list(range(1000))

            async with stage("Validate Schema"):
                await asyncio.sleep(0.01)

            async with stage("Bulk Insert"):
                raise ValueError(
                    "unique constraint failed: events.external_id — "
                    "batch contains 37 duplicate keys"
                )
    except ValueError:
        pass

    # Give the background task a moment to complete and emit LLMAnalysisReady.
    await asyncio.sleep(0.1)


asyncio.run(main())
