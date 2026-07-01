"""Demonstrates structured log fields, custom level icons, and FilteredRenderer.

Three things layered on top of NarrativeLogHandler + ConsoleRenderer:

1. extra={...} passed to logging calls is captured as LogRecorded.fields and
   rendered as key=value pairs (via structlog's default console style when the
   optional `structlog` extra is installed; a plain fallback otherwise).
2. ConsoleRenderer(level_icons={...}) prepends a marker per log level.
3. FilteredRenderer routes stories matching a predicate to their own renderer
   instance -- e.g. every "GET ..." story gets a different style/destination
   than the rest, without any special-cased "GET" concept in the library.

Requires the "structlog" extra for the richer console style:
    uv sync --extra structlog

Run:
    uv run python examples/structured_log_routing.py
"""
import asyncio
import logging

from runtime_narrative import ConsoleRenderer, FilteredRenderer, NarrativeLogHandler, stage, story

logger = logging.getLogger("orders")
logger.setLevel(logging.DEBUG)
logger.addHandler(NarrativeLogHandler(level=logging.WARNING))
logger.propagate = False

# GET requests get a quieter style (no icons); everything else gets icons.
renderers = [
    FilteredRenderer(
        lambda e: getattr(e, "story_name", "").startswith("GET "),
        ConsoleRenderer(),
    ),
    FilteredRenderer(
        lambda e: not getattr(e, "story_name", "").startswith("GET "),
        ConsoleRenderer(level_icons={"warning": "! ", "error": "X "}),
    ),
]


async def get_order(order_id: str) -> None:
    async with story(f"GET /orders/{order_id}", renderers=renderers):
        async with stage("Fetch"):
            await asyncio.sleep(0.005)
            logger.warning("cache miss", extra={"order_id": order_id})


async def create_order(order_id: str) -> None:
    async with story("POST /orders", renderers=renderers):
        async with stage("Persist"):
            await asyncio.sleep(0.005)
            logger.error("write conflict, retrying", extra={"order_id": order_id, "attempt": 2})


async def main() -> None:
    print("-- GET story (no icons, plain FilteredRenderer branch) --")
    await get_order("ORD-1")
    print("\n-- POST story (icons via level_icons) --")
    await create_order("ORD-2")


asyncio.run(main())
