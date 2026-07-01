"""Demonstrates RuntimeNarrativeMiddleware(skip_if=...) (v1.0.1).

skip_if lets you bypass story wrapping entirely for specific requests --
health checks, readiness probes, metrics scrapers -- without creating a
story, emitting events, or running diagnostics for them.

Requires the "fastapi" extra: uv sync --group dev (already includes starlette)

Run:
    uv run python examples/middleware_skip_if.py
"""
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from runtime_narrative import RuntimeNarrativeMiddleware, stage


class Capture:
    def __init__(self):
        self.events: list[object] = []

    def handle(self, event: object) -> None:
        self.events.append(event)


async def health_check(request):
    return PlainTextResponse("ok")


async def create_order(request):
    with stage("Validate Input"):
        pass
    with stage("Persist Order"):
        pass
    return PlainTextResponse("created")


cap = Capture()

app = Starlette(
    routes=[
        Route("/health", endpoint=health_check, methods=["GET"]),
        Route("/orders", endpoint=create_order, methods=["POST"]),
    ],
    middleware=[
        Middleware(
            RuntimeNarrativeMiddleware,
            renderers=[cap],
            skip_if=lambda req: req.url.path in {"/health", "/ready"},
        )
    ],
)

client = TestClient(app)

client.get("/health")
print(f"GET /health   -> events emitted: {len(cap.events)} (skip_if bypassed story wrapping)")

cap.events.clear()
client.post("/orders")
kinds = [type(e).__name__ for e in cap.events]
print(f"POST /orders  -> events emitted: {kinds}")
