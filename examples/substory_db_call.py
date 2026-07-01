"""Demonstrates sub-stories: nesting story() inside an already-active story().

Opening a story() while another is active (in the same sync/async context)
makes it a sub-story -- it auto-inherits renderers/diagnostics_config from
the parent and its events carry parent_story_id/root_story_id, so the full
call tree (API call -> DB call -> ...) can be reconstructed from events
alone. Each sub-story still succeeds/fails and times itself independently.

Run:
    uv run python examples/substory_db_call.py
"""
import asyncio

from runtime_narrative import ConsoleRenderer, stage, story


async def execute_query(sql: str) -> None:
    """Reusable "DB call" helper -- has no idea who its caller is."""
    async with story(f"DB: {sql}") as db_story:
        async with stage("Acquire Connection"):
            await asyncio.sleep(0.01)
        async with stage("Execute Query"):
            await asyncio.sleep(0.02)
    return db_story


async def create_order() -> None:
    async with story("POST /orders", renderers=[ConsoleRenderer()]) as api_story:
        async with stage("Validate Input"):
            await asyncio.sleep(0.005)

        async with stage("Persist Order"):
            db_story = await execute_query("INSERT INTO orders ...")

        async with stage("Notify"):
            await asyncio.sleep(0.005)

    print()
    print(f"API story:  {api_story.story_id[:6]}  parent={api_story.parent_story_id}")
    print(f"DB  story:  {db_story.story_id[:6]}  parent={db_story.parent_story_id[:6]}")
    print(f"Both share root_story_id: {api_story.root_story_id[:6] == db_story.root_story_id[:6]}")
    print(f"Renderers inherited: {db_story.renderers == api_story.renderers}")


asyncio.run(create_order())
