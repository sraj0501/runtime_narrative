from __future__ import annotations

import asyncio
import sys
import unittest.mock as mock

import pytest

# Inject a fake anthropic into sys.modules so the guarded try/import can
# succeed on future reloads. If the module was already cached (e.g. because
# runtime_narrative.__init__ imported it first with _ANTHROPIC_AVAILABLE=False),
# the autouse fixture below patches the flag directly on the cached module.
_fake_anthropic = mock.MagicMock()
_fake_anthropic.Anthropic = mock.MagicMock
_fake_anthropic.AsyncAnthropic = mock.MagicMock
sys.modules.setdefault("anthropic", _fake_anthropic)

from runtime_narrative.failure import FailureSummary
from runtime_narrative.analyzers.anthropic import AnthropicFailureAnalyzer
import runtime_narrative.analyzers.anthropic as _anthropic_mod


@pytest.fixture(autouse=True)
def _force_available(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure every test sees _ANTHROPIC_AVAILABLE=True and the fake module,
    # regardless of import order. test_missing_package_raises_import_error
    # overrides _ANTHROPIC_AVAILABLE back to False inside its own body.
    monkeypatch.setattr(_anthropic_mod, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(_anthropic_mod, "_anthropic", _fake_anthropic)


def _make_failure() -> FailureSummary:
    return FailureSummary(
        error_type="ValueError",
        error_message="bad input",
        filename="/app/main.py",
        lineno=42,
        function="process",
        source_line="result = int(value)",
        exception_chain="ValueError: bad input",
        exact_cause="...",
        traceback_text="Traceback:\n  File main.py line 42\nValueError: bad input",
    )


def _make_analyzer(**kwargs) -> AnthropicFailureAnalyzer:
    defaults: dict = dict(api_key="test-key", model="claude-haiku-4-5-20251001")
    defaults.update(kwargs)
    return AnthropicFailureAnalyzer(**defaults)


_CALL_KWARGS: dict = dict(
    story_name="S",
    stage_name="St",
    failure=_make_failure(),
    stage_timeline="St=ok",
    progress_percent=50,
)


def test_analyze_failure_returns_formatted_string() -> None:
    json_str = '{"exact_why":"x","evidence":"e","targeted_fix":"f","code_changes":"c"}'

    content_item = mock.MagicMock()
    content_item.text = json_str

    response = mock.MagicMock()
    response.content = [content_item]

    mock_client = mock.MagicMock()
    mock_client.messages.create.return_value = response

    with mock.patch.object(_anthropic_mod, "_anthropic") as patched:
        patched.Anthropic.return_value = mock_client
        result = _make_analyzer().analyze_failure(**_CALL_KWARGS)

    assert result is not None
    assert "## Exact Why" in result


def test_analyze_failure_returns_none_on_exception() -> None:
    mock_client = mock.MagicMock()
    mock_client.messages.create.side_effect = Exception("network error")

    with mock.patch.object(_anthropic_mod, "_anthropic") as patched:
        patched.Anthropic.return_value = mock_client
        result = _make_analyzer().analyze_failure(**_CALL_KWARGS)

    assert result is None


def test_analyze_failure_async_returns_formatted_string() -> None:
    json_str = '{"exact_why":"x","evidence":"e","targeted_fix":"f","code_changes":"c"}'

    content_item = mock.MagicMock()
    content_item.text = json_str

    response = mock.MagicMock()
    response.content = [content_item]

    mock_client = mock.AsyncMock()
    mock_client.messages.create = mock.AsyncMock(return_value=response)

    async def run() -> str | None:
        with mock.patch.object(_anthropic_mod, "_anthropic") as patched:
            patched.AsyncAnthropic.return_value = mock_client
            return await _make_analyzer().analyze_failure_async(**_CALL_KWARGS)

    result = asyncio.run(run())
    assert result is not None
    assert "## Exact Why" in result


def test_missing_api_key_raises_value_error() -> None:
    with pytest.raises(ValueError):
        AnthropicFailureAnalyzer(api_key="")


def test_missing_package_raises_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_anthropic_mod, "_ANTHROPIC_AVAILABLE", False)
    with pytest.raises(ImportError):
        AnthropicFailureAnalyzer(api_key="test-key")


def test_parse_response_valid_json() -> None:
    result = _make_analyzer()._parse_response(
        '{"exact_why":"x","evidence":"e","targeted_fix":"f","code_changes":"c"}'
    )
    assert "## Exact Why" in result


def test_parse_response_fallback() -> None:
    result = _make_analyzer()._parse_response("plain text")
    assert result == "plain text"
