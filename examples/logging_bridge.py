"""Demonstrates NarrativeLogHandler: fold existing logging calls into a story.

Attach NarrativeLogHandler to any logger and its warning()/error() calls stop
being a second, disconnected log stream -- they become LogRecorded events
routed through the same renderers as story()/stage(), tagged with the
active story_id/stage_name so you know which call a log line belongs to.

Run:
    uv run python examples/logging_bridge.py
"""
import asyncio
import logging

from runtime_narrative import ConsoleRenderer, NarrativeLogHandler, stage, story

logger = logging.getLogger("orders")
logger.setLevel(logging.DEBUG)
logger.addHandler(NarrativeLogHandler(level=logging.WARNING, fallback=logging.StreamHandler()))
logger.propagate = False


async def charge_card(order_id: str) -> None:
    await asyncio.sleep(0.01)
    logger.warning("card network responded slowly for order %s", order_id)


async def reserve_inventory(order_id: str) -> None:
    await asyncio.sleep(0.01)
    try:
        raise ValueError(f"no stock for {order_id}")
    except ValueError:
        logger.error("inventory reservation failed for order %s", order_id, exc_info=True)


async def main() -> None:
    print("-- log emitted with no active story (goes to fallback StreamHandler) --")
    logger.warning("startup check: no story active yet")

    print("\n-- logs emitted inside a story (captured as LogRecorded) --")
    async with story("POST /orders", renderers=[ConsoleRenderer()]):
        async with stage("Charge Card"):
            await charge_card("ORD-42")
        async with stage("Reserve Inventory"):
            await reserve_inventory("ORD-42")


asyncio.run(main())
