"""Failure example with Ollama LLM analysis using @runtime_narrative_story / @runtime_narrative_stage.

Run:
    RUNTIME_NARRATIVE_MODEL=llama3 uv run python examples/basic_ollama.py
    # Custom endpoint (vLLM, llama.cpp, etc.):
    RUNTIME_NARRATIVE_MODEL=llama3 RUNTIME_NARRATIVE_ENDPOINT=http://localhost:8000/api/generate uv run python examples/basic_ollama.py
"""
import os
from dotenv import load_dotenv

from runtime_narrative import OllamaFailureAnalyzer, runtime_narrative_stage, runtime_narrative_story


load_dotenv(".env")
_model = os.environ["RUNTIME_NARRATIVE_MODEL"]
_endpoint = os.getenv("RUNTIME_NARRATIVE_ENDPOINT", "http://127.0.0.1:11434/api/generate")
_analyzer = OllamaFailureAnalyzer(model=_model, endpoint=_endpoint)


@runtime_narrative_stage("Load CSV")
def load_csv() -> list[str]:
    return ["alice", "bob"]


@runtime_narrative_stage("Validate Data")
def validate(rows: list[str]) -> None:
    if not rows:
        raise ValueError("No rows found")


@runtime_narrative_stage("Insert Records")
def insert(rows: list[str]) -> None:
    raise ValueError("duplicate customer id")


@runtime_narrative_story("Import Customers", failure_analyzer=_analyzer)
def run() -> None:
    rows = load_csv()
    validate(rows)
    insert(rows)


try:
    run()
except Exception:
    pass
