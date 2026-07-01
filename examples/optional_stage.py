"""Demonstrates has_active_story() and stage(optional=True).

Shared library code often can't know whether it's being called from inside an
instrumented request/job or from a background task or unit test where no
story() is active. `stage(optional=True)` degrades to a no-op instead of
raising when there's no active story, and has_active_story() lets callers
branch explicitly when that's clearer.

Run:
    uv run python examples/optional_stage.py
"""
import asyncio

from runtime_narrative import has_active_story, stage, story


async def enrich_record(record: dict) -> dict:
    """Safe to call with or without an active story."""
    async with stage("Enrich Record", optional=True):
        await asyncio.sleep(0.01)
        record["enriched"] = True
    return record


async def send_notification(message: str) -> None:
    if has_active_story():
        async with stage("Send Notification"):
            await asyncio.sleep(0.01)
            print(f"  (instrumented) sent: {message}")
    else:
        print(f"  (uninstrumented) sent: {message}")


async def main() -> None:
    print("Outside any story():")
    print("  has_active_story():", has_active_story())
    record = await enrich_record({"id": 1})  # no-op stage, no RuntimeError
    print("  enrich_record still ran:", record)
    await send_notification("background job started")

    print("\nInside a story():")
    async with story("Batch Enrichment"):
        print("  has_active_story():", has_active_story())
        record = await enrich_record({"id": 2})  # fully instrumented this time
        print("  enrich_record still ran:", record)
        await send_notification("batch item processed")

    try:
        with stage("Unsafe Stage"):  # no optional=True, and no active story
            pass
    except RuntimeError as exc:
        print(f"\nWithout optional=True, stage() still raises outside a story: {exc}")


asyncio.run(main())
