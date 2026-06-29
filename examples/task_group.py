"""Demonstrates NarrativeTaskGroup — concurrent asyncio tasks under a shared story.

All tasks created via create_task() inherit the parent story's ContextVar
automatically. Stages declared inside each task appear in the shared stage
timeline. If any task fails, NarrativeTaskGroupError is raised on exit.

Run:
    uv run python examples/task_group.py
"""
import asyncio

from runtime_narrative import NarrativeTaskGroup, NarrativeTaskGroupError, stage, story


async def fetch_users() -> list[str]:
    async with stage("Fetch Users"):
        await asyncio.sleep(0.02)
        return ["alice", "bob", "carol"]


async def fetch_orders() -> list[dict]:
    async with stage("Fetch Orders"):
        await asyncio.sleep(0.04)
        return [{"id": 1, "amount": 49.00}, {"id": 2, "amount": 119.00}]


async def fetch_inventory() -> dict[str, int]:
    async with stage("Fetch Inventory"):
        await asyncio.sleep(0.01)
        return {"BOOT-42": 12, "HAT-7": 0}


async def fetch_failing() -> None:
    async with stage("Fetch Analytics"):
        await asyncio.sleep(0.03)
        raise ConnectionError("analytics service unavailable — circuit breaker open")


print("=== Concurrent success (3 tasks) ===")


async def success_run() -> None:
    async with story("Dashboard Data Load", total_stages=3):
        async with NarrativeTaskGroup() as tg:
            tg.create_task(fetch_users(), name="users")
            tg.create_task(fetch_orders(), name="orders")
            tg.create_task(fetch_inventory(), name="inventory")


asyncio.run(success_run())

print("\n=== Concurrent with one failure (4 tasks) ===")


async def failure_run() -> None:
    try:
        async with story("Full Dashboard Load", total_stages=4):
            async with NarrativeTaskGroup() as tg:
                tg.create_task(fetch_users(), name="users")
                tg.create_task(fetch_orders(), name="orders")
                tg.create_task(fetch_inventory(), name="inventory")
                tg.create_task(fetch_failing(), name="analytics")
    except NarrativeTaskGroupError as exc:
        print(f"  Failed tasks: {list(exc.failed_tasks)}")
        for name, err in exc.failed_tasks.items():
            print(f"  {name}: {err}")


asyncio.run(failure_run())
