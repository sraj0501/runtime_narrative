from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from datetime import datetime
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request

from runtime_narrative.events import FailureOccurred


class HttpWebhookDestination:
    """
    Generic HTTP webhook destination.

    POSTs a JSON payload describing the failure to *url*.  Network and HTTP
    errors are logged to stderr and never re-raised — alert failures must not
    crash the running story.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._url = url
        self._headers: dict[str, str] = headers or {}
        self._timeout = timeout

    async def send(self, event: FailureOccurred) -> None:
        """Build and POST the standard JSON payload for *event*."""
        payload: dict[str, Any] = {
            "story_id": event.story_id,
            "story_name": event.story_name,
            "stage_name": event.stage_name,
            "error_type": event.error_type,
            "error_message": event.error_message,
            "filename": event.filename,
            "lineno": event.lineno,
            "function": event.function,
            "llm_analysis": event.llm_analysis,
            "timestamp": (
                event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp)
            ),
        }
        await self._post(payload)

    async def _post(self, payload: dict[str, Any]) -> None:
        """Serialise *payload* to JSON and POST it to ``self._url`` in a thread."""
        data = json.dumps(payload).encode("utf-8")
        # Content-Type is always set; caller-supplied headers are merged on top.
        merged_headers = {"Content-Type": "application/json", **self._headers}
        req = Request(self._url, data=data, headers=merged_headers, method="POST")
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=self._timeout)
        except HTTPError as exc:
            print(
                f"[AlertRenderer] HTTP {exc.code} from {self._url}: {exc.reason}",
                file=sys.stderr,
            )
        except URLError as exc:
            print(
                f"[AlertRenderer] URL error posting to {self._url}: {exc.reason}",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover — catch-all safety net
            print(
                f"[AlertRenderer] Unexpected error posting to {self._url}: {exc}",
                file=sys.stderr,
            )


class SlackWebhookDestination(HttpWebhookDestination):
    """
    Slack Incoming Webhook — sends a formatted Slack message.

    Builds a *blocks* payload suited to Slack's Block Kit API and POSTs it to
    the incoming-webhook URL provided by Slack.
    """

    def __init__(self, webhook_url: str, *, timeout: float = 10.0) -> None:
        # Slack incoming webhooks do not require extra headers beyond Content-Type.
        super().__init__(webhook_url, timeout=timeout)

    async def send(self, event: FailureOccurred) -> None:
        """Build and POST a Slack Block Kit payload for *event*."""
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Story failed: {event.story_name}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Stage:* {event.stage_name}\n"
                        f"*Error:* `{event.error_type}: {event.error_message}`\n"
                        f"*Location:* `{event.filename}:{event.lineno}`"
                    ),
                },
            },
        ]
        if event.llm_analysis is not None:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Analysis:* {event.llm_analysis}",
                    },
                }
            )
        payload: dict[str, Any] = {
            "text": f"Story failed: {event.story_name}",
            "blocks": blocks,
        }
        await self._post(payload)


class AlertRoutingRenderer:
    """
    Async renderer that routes ``FailureOccurred`` events to configured
    webhook destinations.

    Filtering rules (each is optional):

    - *only_stories*     — skip events whose ``story_name`` is not in this set.
    - *only_error_types* — skip events whose ``error_type`` is not in this set.

    All matching destinations are called concurrently via ``asyncio.gather``.
    Exceptions from individual destinations are logged to stderr and swallowed;
    they never propagate to the story runtime.
    """

    def __init__(
        self,
        destinations: Sequence[HttpWebhookDestination],
        *,
        only_stories: set[str] | None = None,
        only_error_types: set[str] | None = None,
        include_llm_analysis: bool = True,
    ) -> None:
        self._destinations = list(destinations)
        self._only_stories = only_stories
        self._only_error_types = only_error_types
        self._include_llm_analysis = include_llm_analysis

    async def handle(self, event: object) -> None:
        """Dispatch *event* to all matching destinations (async)."""
        if type(event).__name__ != "FailureOccurred":
            return

        # Narrow the type for the filter checks below.
        failure: FailureOccurred = event  # type: ignore[assignment]

        if self._only_stories is not None and failure.story_name not in self._only_stories:
            return
        if self._only_error_types is not None and failure.error_type not in self._only_error_types:
            return

        results = await asyncio.gather(
            *[d.send(failure) for d in self._destinations],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                print(
                    f"[AlertRenderer] Destination raised: {result}",
                    file=sys.stderr,
                )


__all__ = ["AlertRoutingRenderer", "HttpWebhookDestination", "SlackWebhookDestination"]
