"""Demonstrates instrument_module() — explicit instrumentation of an existing module.

Call instrument_module() once at startup after the module has been imported.
Classes get the @narrative_class treatment; top-level functions are wrapped directly.
Symbols imported from other modules (different __module__) are left untouched.

Run:
    uv run python examples/instrument_module.py
"""
from __future__ import annotations

import runtime_narrative
from runtime_narrative import story

import services

runtime_narrative.instrument_module(services)

svc = services.CustomerService()

with story("Sync Customers", total_stages=4):
    rows = svc.load("crm.csv")
    svc.validate(rows)
    count = svc.save(rows)
    summary = services.summarize(rows)
    print(f"Done: {summary}")
