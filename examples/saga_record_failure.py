"""Demonstrates StoryRuntime.record_failure() for saga/rollback flows.

When a compensating action fails inside a manually-driven rollback handler,
you often don't want that failure to propagate and mark the whole saga as
failed -- you just want it observed. record_failure() emits FailureOccurred
(with the same diagnostics pipeline as a normal exception exit) without
touching exception propagation, so the story can still complete success=True.

Run:
    uv run python examples/saga_record_failure.py
"""
import asyncio

from runtime_narrative import stage, story


class InventoryError(Exception):
    pass


async def charge_card(order_id: str) -> str:
    await asyncio.sleep(0.01)
    return f"charge-{order_id}"


async def reserve_inventory(order_id: str) -> None:
    await asyncio.sleep(0.01)
    raise InventoryError(f"no stock left for order {order_id}")


async def refund_charge(charge_id: str) -> None:
    await asyncio.sleep(0.01)


class Capture:
    def __init__(self):
        self.events: list[object] = []

    async def handle(self, event: object) -> None:
        self.events.append(event)


async def main() -> None:
    cap = Capture()

    async with story("Payment Saga", renderers=[cap]) as runtime:
        async with stage("Charge Card"):
            charge_id = await charge_card("ORD-42")

        try:
            async with stage("Reserve Inventory"):
                await reserve_inventory("ORD-42")
        except InventoryError as exc:
            async with stage("Refund Charge"):
                await refund_charge(charge_id)
            # Record the failure without re-raising -- the saga's compensating
            # action succeeded, so the story should still report success.
            await runtime.record_failure(exc, stage_name="Reserve Inventory")

    kinds = [type(e).__name__ for e in cap.events]
    print("Events emitted:", kinds)

    failure = next(e for e in cap.events if type(e).__name__ == "FailureOccurred")
    print(f"FailureOccurred recorded for stage={failure.stage_name!r}, error={failure.error_type}")

    completed = next(e for e in cap.events if type(e).__name__ == "StoryCompleted")
    print(f"Story completed with success={completed.success} (compensation succeeded)")


asyncio.run(main())
