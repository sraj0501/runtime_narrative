"""Demonstrates AlertRoutingRenderer — async fan-out to webhook destinations.

AlertRoutingRenderer fires only on FailureOccurred. Each destination is called
concurrently via asyncio.gather; failures in one destination never crash the story.

Run (without credentials — posts to a local echo server or httpbin):
    uv run python examples/alert_routing.py

With a real Slack webhook:
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... uv run python examples/alert_routing.py
"""
import asyncio
import os

from runtime_narrative import (
    AlertRoutingRenderer,
    HttpWebhookDestination,
    SlackWebhookDestination,
    stage,
    story,
)

# Generic HTTP destination — replace with your webhook URL.
# httpbin.org/post echoes the payload back, useful for local testing.
http_dest = HttpWebhookDestination(
    url="https://httpbin.org/post",
    headers={"X-Source": "runtime-narrative", "X-Environment": "demo"},
    timeout=10.0,
)

# Slack destination — reads webhook URL from env var, falls back to httpbin.
slack_url = os.getenv("SLACK_WEBHOOK_URL", "https://httpbin.org/post")
slack_dest = SlackWebhookDestination(webhook_url=slack_url, timeout=10.0)

alert_renderer = AlertRoutingRenderer(
    destinations=[http_dest, slack_dest],
    only_error_types={"ConnectionError", "TimeoutError"},  # filter by error class name
)


async def main() -> None:
    try:
        async with story("Payment Processing", renderers=[alert_renderer], total_stages=3):
            async with stage("Validate Cart"):
                items = [{"sku": "BOOT-42", "qty": 1, "price": 149.00}]

            async with stage("Charge Card"):
                total = sum(i["price"] * i["qty"] for i in items)

            async with stage("Notify Merchant"):
                raise ConnectionError("payment gateway timeout after 30s")
    except ConnectionError:
        pass


asyncio.run(main())
