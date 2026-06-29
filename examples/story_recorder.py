"""Demonstrates StoryRecorder — test utility for asserting on story events.

StoryRecorder IS the story: it sets the active story context so that stage()
calls inside the block are attributed to it. Functions under test must call
stage() directly (not wrap with story()) — that is the typical pattern for
testable pipeline functions.

This script runs the assertions as standalone code; in a real project you would
use StoryRecorder inside pytest test functions.

Run:
    uv run python examples/story_recorder.py
"""
import asyncio

from runtime_narrative import StoryRecorder, stage


# ── Functions under test — call stage() but not story() ───────────────────────

def import_customers(rows: list[str]) -> None:
    with stage("Validate"):
        if not rows:
            raise ValueError("empty input")
    with stage("Insert"):
        pass  # success


async def async_pipeline(fail: bool) -> None:
    async with stage("Fetch"):
        await asyncio.sleep(0)
    async with stage("Process"):
        if fail:
            raise RuntimeError("downstream error")


# ── Sync: success path ────────────────────────────────────────────────────────

print("=== sync: success path ===")
with StoryRecorder("Import Customers", total_stages=2) as rec:
    import_customers(["alice", "bob"])

rec.assert_no_failure()
rec.assert_story_completed(success=True)
rec.assert_stages_completed(["Validate", "Insert"])
print(f"  Captured {len(rec.events)} events — all assertions passed")


# ── Sync: failure path ────────────────────────────────────────────────────────

print("\n=== sync: failure path ===")
try:
    with StoryRecorder("Import Customers", total_stages=2) as rec:
        import_customers([])
except ValueError:
    pass

rec.assert_stage_failed("Validate", error_type="ValueError")  # error_type is a string
rec.assert_story_completed(success=False)
print(f"  Captured {len(rec.events)} events — failure assertions passed")


# ── Async: success path ───────────────────────────────────────────────────────

print("\n=== async: success path ===")


async def run_async_success() -> None:
    async with StoryRecorder("Async Pipeline", total_stages=2) as rec:
        await async_pipeline(fail=False)
    rec.assert_no_failure()
    rec.assert_stages_completed(["Fetch", "Process"])
    print(f"  Captured {len(rec.events)} events — all assertions passed")


asyncio.run(run_async_success())


# ── Async: failure path ───────────────────────────────────────────────────────

print("\n=== async: failure path ===")


async def run_async_failure() -> None:
    try:
        async with StoryRecorder("Async Pipeline", total_stages=2) as rec:
            await async_pipeline(fail=True)
    except RuntimeError:
        pass
    rec.assert_stage_failed("Process", error_type="RuntimeError")
    rec.assert_story_completed(success=False)
    print(f"  Captured {len(rec.events)} events — failure assertions passed")


asyncio.run(run_async_failure())
