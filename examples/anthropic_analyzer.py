"""Demonstrates AnthropicFailureAnalyzer + DeduplicatingAnalyzer.

AnthropicFailureAnalyzer calls the Anthropic API to explain failures and suggest
targeted fixes. DeduplicatingAnalyzer wraps any analyzer to skip repeat API calls
for the same error site (keyed by error type + file + line number).

Requires:
    uv sync --group dev --extra anthropic
    ANTHROPIC_API_KEY=sk-ant-...

Run:
    ANTHROPIC_API_KEY=sk-ant-... uv run python examples/anthropic_analyzer.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from runtime_narrative import (
    AnthropicFailureAnalyzer,
    DeduplicatingAnalyzer,
    stage,
    story,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

if not os.getenv("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY not set — running without LLM analysis.\n")
    analyzer = None
else:
    _inner = AnthropicFailureAnalyzer(
        # claude-haiku is fast and cheap; override via RUNTIME_NARRATIVE_MODEL env var.
        model="claude-haiku-4-5-20251001",
        timeout_seconds=30.0,
        max_tokens=1024,
    )
    # Wrapping with DeduplicatingAnalyzer avoids repeat API calls when the same
    # error fires multiple times in a hot path (e.g., in a retry loop).
    analyzer = DeduplicatingAnalyzer(_inner, max_cache_size=128)


async def main() -> None:
    try:
        async with story(
            "Data Ingest Pipeline",
            failure_analyzer=analyzer,
            total_stages=3,
        ):
            async with stage("Fetch Remote Data"):
                data = [{"user_id": i, "score": i * 1.5} for i in range(100)]

            async with stage("Transform Records"):
                data = [{"uid": r["user_id"], "val": round(r["score"], 2)} for r in data]

            async with stage("Write to Database"):
                raise RuntimeError(
                    "column 'uid' does not exist in table 'events' — "
                    "did you forget to run the latest migration?"
                )
    except RuntimeError:
        pass


asyncio.run(main())
