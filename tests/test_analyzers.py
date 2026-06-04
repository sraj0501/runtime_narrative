from __future__ import annotations

# T4: Malformed LLM response — empty choices, null content, invalid JSON, URL errors.
# Tests the silent-fallback contract of LLMFailureAnalyzer and OllamaFailureAnalyzer.

import json
from unittest.mock import MagicMock, patch

from runtime_narrative.analyzers.ollama import LLMFailureAnalyzer, OllamaFailureAnalyzer
from runtime_narrative.failure import FailureSummary


def _make_summary() -> FailureSummary:
    return FailureSummary(
        error_type="ValueError",
        error_message="bad",
        filename="app.py",
        lineno=10,
        function="do_it",
        source_line="raise ValueError('bad')",
        exception_chain="ValueError: bad",
        exact_cause="bad",
        traceback_text="Traceback (most recent call last):\n  File app.py, line 10\nValueError: bad",
    )


def _mock_http_response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_KWARGS = dict(
    story_name="S",
    stage_name="St",
    failure=_make_summary(),
    stage_timeline="St=failed",
    progress_percent=50,
)


# ── LLMFailureAnalyzer (OpenAI-compatible) ────────────────────────────────────

def test_llm_analyzer_returns_text_on_valid_response():
    body = json.dumps({"choices": [{"message": {"content": "fix the bug"}}]}).encode()
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result == "fix the bug"


def test_llm_analyzer_returns_none_on_empty_choices():
    body = json.dumps({"choices": []}).encode()
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_llm_analyzer_returns_none_on_null_content():
    body = json.dumps({"choices": [{"message": {"content": None}}]}).encode()
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_llm_analyzer_returns_none_on_invalid_json():
    body = b"not json at all"
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_llm_analyzer_returns_none_on_url_error():
    from urllib.error import URLError
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", side_effect=URLError("connection refused")):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_llm_analyzer_returns_none_on_missing_choices_key():
    body = json.dumps({"model": "gpt-4", "usage": {}}).encode()
    analyzer = LLMFailureAnalyzer(model="gpt-4", endpoint="http://localhost/v1/chat/completions")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


# ── OllamaFailureAnalyzer ─────────────────────────────────────────────────────

def test_ollama_analyzer_returns_text_on_valid_response():
    body = json.dumps({"response": "use try/except"}).encode()
    analyzer = OllamaFailureAnalyzer(model="llama3")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result == "use try/except"


def test_ollama_analyzer_returns_none_on_missing_response_key():
    body = json.dumps({"model": "llama3", "done": True}).encode()
    analyzer = OllamaFailureAnalyzer(model="llama3")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_ollama_analyzer_returns_none_on_empty_response_value():
    body = json.dumps({"response": "   "}).encode()
    analyzer = OllamaFailureAnalyzer(model="llama3")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_ollama_analyzer_returns_none_on_invalid_json():
    body = b"{bad json"
    analyzer = OllamaFailureAnalyzer(model="llama3")
    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=_mock_http_response(body)):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None


def test_ollama_analyzer_returns_none_on_url_error():
    from urllib.error import URLError
    analyzer = OllamaFailureAnalyzer(model="llama3")
    with patch("runtime_narrative.analyzers.ollama.urlopen", side_effect=URLError("no route")):
        result = analyzer.analyze_failure(**_KWARGS)
    assert result is None
