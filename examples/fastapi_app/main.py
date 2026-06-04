from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from runtime_narrative import (
    JsonRenderer,
    OllamaFailureAnalyzer,
    RuntimeNarrativeMiddleware,
    runtime_narrative_stage,
    runtime_narrative_story,
)

from .db import create_customer, init_db, list_customers

_model = os.getenv("RUNTIME_NARRATIVE_MODEL")
_endpoint = os.getenv("RUNTIME_NARRATIVE_ENDPOINT", "http://127.0.0.1:11434/api/generate")
failure_analyzer = OllamaFailureAnalyzer(model=_model, endpoint=_endpoint) if _model else None

# Switch to JsonRenderer by setting RUNTIME_NARRATIVE_JSON=1
USE_JSON = os.getenv("RUNTIME_NARRATIVE_JSON", "0") == "1"
renderers = [JsonRenderer()] if USE_JSON else None  # None → default ConsoleRenderer

_story_kw = dict(renderers=renderers, failure_analyzer=failure_analyzer)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@runtime_narrative_stage("Initialize Database")
def _init_db() -> None:
    init_db()


@runtime_narrative_stage("Release Resources")
def _release_resources() -> None:
    pass


@runtime_narrative_story("FastAPI App Startup", **_story_kw)
def _startup() -> None:
    _init_db()


@runtime_narrative_story("FastAPI App Shutdown", **_story_kw)
def _shutdown() -> None:
    _release_resources()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    try:
        yield
    finally:
        _shutdown()


app = FastAPI(title="Runtime Narrative FastAPI Demo", version="0.1.0", lifespan=lifespan)

# Middleware wraps every request in a story automatically.
# Route handlers only need to declare stages — no story() context required.
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=renderers,
    failure_analyzer=failure_analyzer,
)


class CustomerCreate(BaseModel):
    name: str
    email: str


# ── GET /health ───────────────────────────────────────────────────────────────

@runtime_narrative_stage("Build Response")
def _health_response() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return _health_response()


# ── POST /customers ───────────────────────────────────────────────────────────

@runtime_narrative_stage("Validate Input")
def _validate_customer(payload: CustomerCreate) -> None:
    if "@" not in payload.email:
        raise ValueError("invalid email")


@runtime_narrative_stage("Insert Into Database")
def _insert_customer(payload: CustomerCreate) -> dict:
    try:
        return create_customer(payload.name, payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@runtime_narrative_stage("Build Response")
def _customer_created_response(customer: dict) -> dict:
    return {"created": True, "customer": customer}


@app.post("/customers")
async def add_customer(payload: CustomerCreate) -> dict[str, object]:
    _validate_customer(payload)
    customer = _insert_customer(payload)
    return _customer_created_response(customer)


# ── GET /customers ────────────────────────────────────────────────────────────

@runtime_narrative_stage("Fetch Customers")
def _fetch_customers() -> list:
    return list_customers()


@runtime_narrative_stage("Build Response")
def _customers_list_response(customers: list) -> dict:
    return {"count": len(customers), "customers": customers}


@app.get("/customers")
async def get_customers() -> dict[str, object]:
    customers = _fetch_customers()
    return _customers_list_response(customers)
