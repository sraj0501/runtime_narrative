"""Deep async call chain used by the "ugliest traceback" demo.

See ``examples/fastapi_ugly_traceback_demo.py`` for the full story. This
module exists on its own so the exact same business logic — and the exact
same bug — can be exercised through two FastAPI apps: one with zero
runtime-narrative instrumentation (to show the raw traceback), and one
wrapped by ``RuntimeNarrativeMiddleware`` (to show the diagnosis).

The call chain deliberately layers the kind of generic infrastructure code
every real async service accumulates — a retry decorator, a timing
decorator, a lock/connection-pool context manager, an ``asyncio.gather``
fan-out — between the route handler and the actual bug, so a raw traceback
has real depth to get lost in.
"""
from __future__ import annotations

import asyncio
import functools
import time
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, TypeVar

from runtime_narrative import stage

T = TypeVar("T")


# ── Generic infra noise: the decorators/context managers every codebase has ──

def with_retry(times: int = 2) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Generic async retry decorator — every failed attempt adds real frames."""
    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for _attempt in range(1, times + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - intentionally broad; generic retry wrapper
                    last_exc = exc
            assert last_exc is not None
            raise last_exc from None
        return wrapper
    return decorator


def log_timing(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Generic async timing decorator — another layer of indirection."""
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            time.perf_counter() - start
    return wrapper


@asynccontextmanager
async def resource_lock(name: str):
    """Stands in for a connection pool / distributed lock acquisition."""
    await asyncio.sleep(0)
    try:
        yield
    finally:
        await asyncio.sleep(0)


# ── The business logic the bug hides in ────────────────────────────────────────

# Percentage promos are floats; BOGO promos are structured deals. That
# distinction is exactly what the buggy line below forgets to check.
PROMO_TABLE: dict[str, Any] = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
    "BOGO-SHIRT": {"buy": 1, "get": 1, "item_sku": "SHIRT-001"},
}


async def _compute_line_discount(item: dict, promo_code: str) -> float:
    """The actual bug: BOGO promos are dicts, not discount rates."""
    promo = PROMO_TABLE[promo_code]
    await asyncio.sleep(0)
    return item["price"] * promo  # TypeError when promo_code is a BOGO deal


class PricingEngine:
    @with_retry(times=2)
    async def apply_discounts(self, cart: list[dict], promo_code: str) -> float:
        async with resource_lock("pricing-cache"):
            discounts = await asyncio.gather(
                *[_compute_line_discount(item, promo_code) for item in cart]
            )
        return sum(discounts)


class InventoryService:
    async def reserve(self, cart: list[dict]) -> None:
        await asyncio.sleep(0)


class PaymentGateway:
    async def charge(self, payment_method: str, amount: float) -> str:
        await asyncio.sleep(0)
        return "txn_demo_001"


class OrderRepository:
    async def save(self, order: dict) -> int:
        await asyncio.sleep(0)
        return 1


class OrderOrchestrator:
    def __init__(self) -> None:
        self.pricing = PricingEngine()
        self.inventory = InventoryService()
        self.payment = PaymentGateway()
        self.repository = OrderRepository()

    @log_timing
    async def run(self, cart: list[dict], promo_code: str, payment_method: str) -> dict:
        # optional=True: this same pipeline is also exercised with no active
        # story() at all (the "bare" app in the traceback demo) — stage()
        # becomes a no-op there instead of raising "no active story".
        async with stage("Reserve Inventory", optional=True):
            await self.inventory.reserve(cart)

        async with stage("Apply Pricing", optional=True):
            total = await self.pricing.apply_discounts(cart, promo_code)

        async with stage("Charge Payment", optional=True):
            txn_id = await self.payment.charge(payment_method, total)

        async with stage("Persist Order", optional=True):
            order_id = await self.repository.save(
                {"cart": cart, "total": total, "txn_id": txn_id}
            )

        return {"order_id": order_id, "total": total, "txn_id": txn_id}


async def checkout_order(cart: list[dict], promo_code: str, payment_method: str) -> dict:
    """Entry point called by both the bare and the instrumented route handlers."""
    orchestrator = OrderOrchestrator()
    return await orchestrator.run(cart, promo_code, payment_method)
