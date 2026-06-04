"""Demonstrates auto_instrument() — zero-config import-hook instrumentation.

Register the hook before importing any app modules. Every module whose source
file is under app_roots is instrumented automatically on import. Stdlib and
installed packages are unaffected.

Run:
    uv run python examples/auto_instrument.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import runtime_narrative
from runtime_narrative import story

# Register the hook before importing app modules.
# app_roots defaults to cwd; here we pin it to the examples directory so only
# modules under examples/ are instrumented (not the full project).
finder = runtime_narrative.auto_instrument(
    app_roots=[str(Path(__file__).resolve().parent)]
)

# examples.services has not been imported yet in this process, so the hook
# fires and instruments CustomerService and summarize() on the way in.
import services  # noqa: E402

svc = services.CustomerService()

with story("Auto-Instrumented Run", total_stages=3):
    rows = svc.load("crm.csv")
    svc.validate(rows)
    count = svc.save(rows)
    print(f"Saved {count} customers")

# Remove the hook when no further imports need instrumentation.
sys.meta_path.remove(finder)
