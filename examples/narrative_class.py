"""Demonstrates @narrative_class and @no_stage.

Every public instance method of OrderService becomes a stage automatically.
The internal _log helper is excluded via @no_stage.

Run:
    uv run python examples/narrative_class.py
"""
from __future__ import annotations

from runtime_narrative import narrative_class, no_stage, story


@narrative_class
class OrderService:
    def validate(self, order: dict) -> None:
        if "amount" not in order:
            raise ValueError("order is missing 'amount'")

    def charge(self, order: dict) -> str:
        return f"charged ${order['amount']:.2f}"

    def fulfill(self, order: dict) -> str:
        return f"fulfilled order {order.get('id', 'unknown')}"

    @no_stage
    def _log(self, msg: str) -> None:
        pass  # internal helper — not a stage


svc = OrderService()

print("=== Success path ===")
order = {"id": "ORD-001", "amount": 99.00}
with story("Process Order", total_stages=3):
    svc.validate(order)
    receipt = svc.charge(order)
    svc.fulfill(order)

print("\n=== Failure path ===")
bad_order = {"id": "ORD-002"}
try:
    with story("Process Order", total_stages=3):
        svc.validate(bad_order)
        svc.charge(bad_order)
        svc.fulfill(bad_order)
except ValueError:
    pass
