from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pytest

from runtime_narrative.events import FailureOccurred, StoryStarted
from runtime_narrative.renderer.alert_renderer import (
    AlertRoutingRenderer,
    HttpWebhookDestination,
    SlackWebhookDestination,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


class FakeDestination(HttpWebhookDestination):
    """Records every event passed to ``send`` without touching the network."""

    def __init__(self) -> None:
        # Intentionally skips HttpWebhookDestination.__init__ — no URL needed.
        self.calls: list[Any] = []

    async def send(self, event: FailureOccurred) -> None:
        self.calls.append(event)


class RaisingDestination(HttpWebhookDestination):
    """Always raises from ``send``; used to verify exception isolation."""

    def __init__(self) -> None:
        self.send_called = False

    async def send(self, event: FailureOccurred) -> None:
        self.send_called = True
        raise RuntimeError("deliberate failure from RaisingDestination")


def _make_failure(**overrides: Any) -> FailureOccurred:
    defaults: dict[str, Any] = dict(
        story_id="s1",
        story_name="ETL",
        stage_name="Load",
        error_type="ValueError",
        error_message="bad input",
        filename="etl.py",
        lineno=42,
        function="load",
        source_line="x = int(val)",
        exception_chain="ValueError: bad input",
        exact_cause="bad input",
        llm_analysis=None,
        stage_timeline="Load",
        progress_percent=50,
        completed_stages=1,
        total_stages=2,
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
        traceback_text="Traceback (most recent call last):\n  ...",
    )
    return FailureOccurred(**{**defaults, **overrides})


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_matching_failure_calls_destination() -> None:
    """AlertRoutingRenderer calls send() on a matching FailureOccurred event."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest])
    event = _make_failure()

    asyncio.run(renderer.handle(event))

    assert len(dest.calls) == 1
    assert dest.calls[0] is event


def test_only_stories_filter_blocks_non_matching_story() -> None:
    """When only_stories is set, events from other stories are not forwarded."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest], only_stories={"AllowedStory"})
    event = _make_failure(story_name="ETL")  # "ETL" not in {"AllowedStory"}

    asyncio.run(renderer.handle(event))

    assert dest.calls == []


def test_only_stories_filter_passes_matching_story() -> None:
    """Events whose story_name is in only_stories are forwarded."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest], only_stories={"ETL"})
    event = _make_failure(story_name="ETL")

    asyncio.run(renderer.handle(event))

    assert len(dest.calls) == 1


def test_only_error_types_filter_blocks_non_matching_type() -> None:
    """When only_error_types is set, non-matching error types are skipped."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest], only_error_types={"KeyError"})
    event = _make_failure(error_type="ValueError")

    asyncio.run(renderer.handle(event))

    assert dest.calls == []


def test_only_error_types_filter_passes_matching_type() -> None:
    """Events whose error_type is in only_error_types are forwarded."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest], only_error_types={"ValueError"})
    event = _make_failure(error_type="ValueError")

    asyncio.run(renderer.handle(event))

    assert len(dest.calls) == 1


def test_multiple_destinations_all_called() -> None:
    """All configured destinations receive the event."""
    dest_a = FakeDestination()
    dest_b = FakeDestination()
    dest_c = FakeDestination()
    renderer = AlertRoutingRenderer([dest_a, dest_b, dest_c])
    event = _make_failure()

    asyncio.run(renderer.handle(event))

    assert len(dest_a.calls) == 1
    assert len(dest_b.calls) == 1
    assert len(dest_c.calls) == 1
    # All three received the same event object.
    assert dest_a.calls[0] is event
    assert dest_b.calls[0] is event
    assert dest_c.calls[0] is event


def test_raising_destination_does_not_propagate(capsys: pytest.CaptureFixture[str]) -> None:
    """An exception from one destination is swallowed; other destinations still run."""
    bad = RaisingDestination()
    good = FakeDestination()
    renderer = AlertRoutingRenderer([bad, good])
    event = _make_failure()

    # Must not raise.
    asyncio.run(renderer.handle(event))

    # The bad destination was attempted.
    assert bad.send_called

    # The good destination still received the event.
    assert len(good.calls) == 1

    # The error was logged to stderr.
    captured = capsys.readouterr()
    assert "deliberate failure" in captured.err


def test_non_failure_events_are_ignored() -> None:
    """Non-FailureOccurred events are silently dropped."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer([dest])

    story_started = StoryStarted(
        story_id="s1",
        story_name="ETL",
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
    )

    asyncio.run(renderer.handle(story_started))
    asyncio.run(renderer.handle("bare string event"))
    asyncio.run(renderer.handle(None))

    assert dest.calls == []


def test_both_filters_applied_together() -> None:
    """only_stories AND only_error_types must both match for the event to be routed."""
    dest = FakeDestination()
    renderer = AlertRoutingRenderer(
        [dest],
        only_stories={"ETL"},
        only_error_types={"ValueError"},
    )

    # Matches story but not error type.
    asyncio.run(renderer.handle(_make_failure(story_name="ETL", error_type="KeyError")))
    assert dest.calls == []

    # Matches error type but not story.
    asyncio.run(renderer.handle(_make_failure(story_name="Other", error_type="ValueError")))
    assert dest.calls == []

    # Matches both.
    asyncio.run(renderer.handle(_make_failure(story_name="ETL", error_type="ValueError")))
    assert len(dest.calls) == 1


def test_slack_destination_includes_llm_analysis_block_when_present() -> None:
    """
    SlackWebhookDestination builds a blocks payload; when llm_analysis is not
    None it includes an analysis block.  We verify the payload structure
    without making a real HTTP call by subclassing and capturing _post calls.
    """
    posted_payloads: list[Any] = []

    class CapturingSlack(SlackWebhookDestination):
        async def _post(self, payload: dict[str, Any]) -> None:  # type: ignore[override]
            posted_payloads.append(payload)

    dest = CapturingSlack("https://hooks.slack.com/services/FAKE")
    event = _make_failure(llm_analysis="Check line 42 — int() received a str.")

    asyncio.run(dest.send(event))

    assert len(posted_payloads) == 1
    payload = posted_payloads[0]
    assert payload["text"] == "Story failed: ETL"
    block_types = [b["type"] for b in payload["blocks"]]
    assert block_types == ["header", "section", "section"]
    # Third block carries the analysis.
    analysis_block = payload["blocks"][2]
    assert "Analysis" in analysis_block["text"]["text"]
    assert "Check line 42" in analysis_block["text"]["text"]


def test_slack_destination_omits_analysis_block_when_none() -> None:
    """When llm_analysis is None, the analysis block is absent."""
    posted_payloads: list[Any] = []

    class CapturingSlack(SlackWebhookDestination):
        async def _post(self, payload: dict[str, Any]) -> None:  # type: ignore[override]
            posted_payloads.append(payload)

    dest = CapturingSlack("https://hooks.slack.com/services/FAKE")
    event = _make_failure(llm_analysis=None)

    asyncio.run(dest.send(event))

    assert len(posted_payloads) == 1
    block_types = [b["type"] for b in posted_payloads[0]["blocks"]]
    # Only header + detail section; no analysis block.
    assert block_types == ["header", "section"]


def test_http_destination_payload_structure() -> None:
    """HttpWebhookDestination.send builds the expected JSON payload keys."""
    posted_payloads: list[Any] = []

    class CapturingHttp(HttpWebhookDestination):
        async def _post(self, payload: dict[str, Any]) -> None:  # type: ignore[override]
            posted_payloads.append(payload)

    dest = CapturingHttp("https://example.com/webhook")
    event = _make_failure(llm_analysis="analysis text")

    asyncio.run(dest.send(event))

    assert len(posted_payloads) == 1
    payload = posted_payloads[0]
    expected_keys = {
        "story_id", "story_name", "stage_name", "error_type",
        "error_message", "filename", "lineno", "function",
        "llm_analysis", "timestamp",
    }
    assert expected_keys == set(payload.keys())
    assert payload["story_id"] == "s1"
    assert payload["story_name"] == "ETL"
    assert payload["error_type"] == "ValueError"
    assert payload["lineno"] == 42
    assert payload["llm_analysis"] == "analysis text"
    # Timestamp must be an ISO-8601 string.
    assert "2024-06-01" in payload["timestamp"]
