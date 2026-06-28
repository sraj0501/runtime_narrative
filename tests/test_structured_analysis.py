from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from runtime_narrative.analyzers.ollama import (
    LLMFailureAnalyzer,
    OllamaFailureAnalyzer,
    _build_prompt,
    _parse_structured_response,
)
from runtime_narrative.failure import FailureSummary


def _make_failure(traceback_text: str = "") -> FailureSummary:
    if not traceback_text:
        traceback_text = (
            "Traceback (most recent call last):\n"
            "  File 'foo.py', line 1, in bar\n"
            "    raise ValueError('oops')\n"
            "ValueError: oops\n"
        )
    return FailureSummary(
        error_type="ValueError",
        error_message="oops",
        filename="foo.py",
        lineno=1,
        function="bar",
        source_line="raise ValueError('oops')",
        exception_chain="ValueError: oops",
        exact_cause="The code explicitly raises ValueError here with message: oops",
        traceback_text=traceback_text,
    )


def test_parse_structured_response_valid_json():
    data = {
        "exact_why": "division by zero at line 42",
        "evidence": "ZeroDivisionError raised in calc()",
        "targeted_fix": "add a guard for denominator == 0",
        "code_changes": "old: return a/b\nnew: return a/b if b else 0",
    }
    result = _parse_structured_response(json.dumps(data))
    assert "## Exact Why" in result
    assert "## Evidence" in result
    assert "## Targeted Fix" in result
    assert "## Code Changes" in result
    assert "division by zero at line 42" in result
    assert "ZeroDivisionError raised in calc()" in result


def test_parse_structured_response_json_in_code_fence():
    data = {"exact_why": "bad index", "evidence": "IndexError", "targeted_fix": "bounds check", "code_changes": "n/a"}
    fenced = f"```json\n{json.dumps(data)}\n```"
    result = _parse_structured_response(fenced)
    assert "## Exact Why" in result
    assert "bad index" in result
    assert "## Code Changes" in result


def test_parse_structured_response_fallback():
    raw = "This is not JSON at all."
    result = _parse_structured_response(raw)
    assert result == raw


def test_parse_structured_response_partial_keys():
    data = {"exact_why": "null pointer", "targeted_fix": "add None check"}
    result = _parse_structured_response(json.dumps(data))
    assert "## Exact Why" in result
    assert "## Targeted Fix" in result
    assert "## Evidence" not in result
    assert "## Code Changes" not in result
    assert "null pointer" in result


def test_llm_analyzer_returns_structured_text():
    inner_json = json.dumps({
        "exact_why": "x",
        "evidence": "e",
        "targeted_fix": "f",
        "code_changes": "c",
    })
    body = json.dumps({"choices": [{"message": {"content": inner_json}}]}).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=mock_resp):
        analyzer = LLMFailureAnalyzer(model="test-model", endpoint="http://localhost:8000/v1/chat/completions")
        result = analyzer.analyze_failure(
            story_name="my-story",
            stage_name="my-stage",
            failure=_make_failure(),
            stage_timeline="step1 -> step2",
            progress_percent=75,
        )

    assert result is not None
    assert "## Exact Why" in result
    assert "## Evidence" in result
    assert "## Targeted Fix" in result
    assert "## Code Changes" in result


def test_ollama_analyzer_returns_structured_text():
    inner_json = json.dumps({
        "exact_why": "x",
        "evidence": "e",
        "targeted_fix": "f",
        "code_changes": "c",
    })
    body = json.dumps({"response": inner_json}).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("runtime_narrative.analyzers.ollama.urlopen", return_value=mock_resp):
        analyzer = OllamaFailureAnalyzer(model="llama3")
        result = analyzer.analyze_failure(
            story_name="my-story",
            stage_name="my-stage",
            failure=_make_failure(),
            stage_timeline="step1 -> step2",
            progress_percent=50,
        )

    assert result is not None
    assert "## Exact Why" in result
    assert "## Evidence" in result
    assert "## Targeted Fix" in result
    assert "## Code Changes" in result


def test_context_budget_trims_long_traceback():
    lines = [f"  line {i}: something went wrong here in function_name()" for i in range(200)]
    long_tb = "Traceback (most recent call last):\n" + "\n".join(lines) + "\nValueError: oops\n"
    failure = _make_failure(traceback_text=long_tb)

    max_context_chars = 2000
    result = _build_prompt(
        story_name="s",
        stage_name="st",
        failure=failure,
        stage_timeline="a -> b",
        progress_percent=10,
        include_traceback_lines=30,
        max_context_chars=max_context_chars,
    )

    assert len(result) <= max_context_chars + 300
    assert long_tb.strip() not in result


def test_context_budget_no_trim_when_within_limit():
    short_tb = (
        "Traceback (most recent call last):\n"
        "  File 'app.py', line 5, in run\n"
        "    do_thing()\n"
        "ValueError: oops\n"
    )
    failure = _make_failure(traceback_text=short_tb)

    result = _build_prompt(
        story_name="s",
        stage_name="st",
        failure=failure,
        stage_timeline="a -> b",
        progress_percent=10,
        include_traceback_lines=30,
        max_context_chars=8000,
    )

    assert "File 'app.py', line 5, in run" in result
    assert "do_thing()" in result


def test_max_context_chars_default_on_analyzer():
    analyzer = LLMFailureAnalyzer(model="test-model", endpoint="http://localhost:8000/v1/chat/completions")
    assert analyzer.max_context_chars == 8000
