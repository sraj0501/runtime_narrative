"""The ugliest traceback we could build in async FastAPI code -- and how
runtime-narrative cuts through it.

Both runs below hit the exact same bug through the exact same async call
chain (route handler -> orchestrator -> retry-wrapped pricing engine ->
asyncio.gather fan-out -> per-line-item discount calculation -- see
examples/fastapi_app/order_pipeline.py). The only difference is
instrumentation:

1. A bare FastAPI app with no runtime-narrative at all -- what Python,
   Starlette, and asyncio hand you by default.
2. The same route wrapped by RuntimeNarrativeMiddleware with rich
   diagnostics -- pointing straight at the one line that matters, out of
   dozens of frames.

Set RUNTIME_NARRATIVE_MODEL (Ollama) or ANTHROPIC_API_KEY before running to
also see the LLM turn the diagnosis into a plain-English explanation.

Run:
    uv run python examples/fastapi_ugly_traceback_demo.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from dotenv import load_dotenv

from runtime_narrative import ConsoleRenderer, FailureDiagnosticsConfig, RuntimeNarrativeMiddleware  # noqa: E402
from runtime_narrative.analyzers import OllamaFailureAnalyzer  # noqa: E402

from fastapi_app.order_pipeline import checkout_order  # noqa: E402

load_dotenv()

CHECKOUT_PAYLOAD = {
    "cart": [
        {"sku": "SHIRT-001", "price": 29.99},
        {"sku": "HAT-002", "price": 14.50},
    ],
    # BOGO promos are structured deals, not discount rates -- this is what
    # trips up _compute_line_discount() several layers down.
    "promo_code": "BOGO-SHIRT",
    "payment_method": "card_demo",
}

# Optional LLM analyzer -- same env-driven setup as examples/basic_ollama.py
# and examples/fastapi_app/main.py. Off by default; the diagnosis itself
# needs no LLM at all.
_model = os.getenv("RUNTIME_NARRATIVE_MODEL")
_endpoint = os.getenv("RUNTIME_NARRATIVE_ENDPOINT", "http://127.0.0.1:11434/api/generate")
_failure_analyzer = OllamaFailureAnalyzer(model=_model, endpoint=_endpoint) if _model else None
if _failure_analyzer is None and os.getenv("ANTHROPIC_API_KEY"):
    from runtime_narrative import AnthropicFailureAnalyzer

    _failure_analyzer = AnthropicFailureAnalyzer()


# ── 1. Bare FastAPI, zero instrumentation ──────────────────────────────────────

bare_app = FastAPI(title="Bare (no runtime-narrative)")


@bare_app.post("/orders/checkout")
async def bare_checkout(payload: dict) -> dict:
    return await checkout_order(payload["cart"], payload["promo_code"], payload["payment_method"])


async def run_bare() -> None:
    print("=" * 78)
    print("1) WITHOUT runtime-narrative -- raw Python/Starlette/asyncio traceback")
    print("=" * 78)
    transport = ASGITransport(app=bare_app)
    async with AsyncClient(transport=transport, base_url="http://demo") as client:
        try:
            await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD)
        except Exception:
            raw_tb = traceback.format_exc()
            print(raw_tb)
            frame_count = raw_tb.count('File "')
            print(
                f"--- {frame_count} stack frames, {len(raw_tb.splitlines())} lines of "
                "output. The real bug -- a BOGO promo dict multiplied against a price -- "
                "is in there somewhere, mixed in with retry-loop noise, asyncio.gather's "
                "own task-stepping frames, and Starlette's routing internals. ---\n"
            )


# ── 2. Same bug, same depth, through runtime-narrative ─────────────────────────
# renderers=[ConsoleRenderer()] is pinned explicitly (rather than left to
# default_renderers()'s TTY auto-detection) so this demo prints the same
# rich output whether run from a terminal or piped/redirected.

narrative_app = FastAPI(title="Instrumented (runtime-narrative)")
narrative_app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[ConsoleRenderer()],
    failure_analyzer=_failure_analyzer,
    diagnostics_config=FailureDiagnosticsConfig(failure_diagnostics="rich"),
)


@narrative_app.post("/orders/checkout")
async def narrative_checkout(payload: dict) -> dict:
    return await checkout_order(payload["cart"], payload["promo_code"], payload["payment_method"])


async def run_instrumented() -> None:
    print("=" * 78)
    print("2) WITH runtime-narrative -- identical call stack, identical bug")
    print("=" * 78)
    transport = ASGITransport(app=narrative_app)
    async with AsyncClient(transport=transport, base_url="http://demo") as client:
        try:
            await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD)
        except Exception:
            pass  # the story's ConsoleRenderer already printed the diagnosis above

    print(
        "\nSame async pipeline, same retry-wrapped pricing engine, same "
        "asyncio.gather fan-out -- but instead of scrolling through dozens of "
        "frames, the output above names the exact failing line, the exact "
        "frame, a source snippet, the stage that was in progress ('Apply "
        "Pricing'), and the local variable values that caused it. Set "
        "RUNTIME_NARRATIVE_MODEL or ANTHROPIC_API_KEY and it also explains, "
        "in plain English, exactly what went wrong and how to fix it."
    )


async def main() -> None:
    await run_bare()
    await run_instrumented()


if __name__ == "__main__":
    asyncio.run(main())
