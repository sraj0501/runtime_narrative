from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from runtime_narrative import RuntimeNarrativeMiddleware, JsonRenderer, OllamaFailureAnalyzer, stage, story

from .db import create_customer, init_db, list_customers

_model = os.getenv("RUNTIME_NARRATIVE_MODEL")
_endpoint = os.getenv("RUNTIME_NARRATIVE_ENDPOINT", "http://127.0.0.1:11434/api/generate")
failure_analyzer = OllamaFailureAnalyzer(model=_model, endpoint=_endpoint) if _model else None

# Switch to JsonRenderer by setting RUNTIME_NARRATIVE_JSON=1
USE_JSON = os.getenv("RUNTIME_NARRATIVE_JSON", "0") == "1"
renderers = [JsonRenderer()] if USE_JSON else None  # None → default ConsoleRenderer


@asynccontextmanager
async def lifespan(app: FastAPI):
    with story("FastAPI App Startup", renderers=renderers, failure_analyzer=failure_analyzer):
        with stage("Initialize Database"):
            init_db()
    try:
        yield
    finally:
        with story("FastAPI App Shutdown", renderers=renderers, failure_analyzer=failure_analyzer):
            with stage("Release Resources"):
                pass


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


@app.get("/health")
async def health() -> dict[str, str]:
    with stage("Build Response"):
        return {"status": "ok"}


@app.post("/customers")
async def add_customer(payload: CustomerCreate) -> dict[str, object]:
    with stage("Validate Input"):
        if "@" not in payload.email:
            raise ValueError("invalid email")

    with stage("Insert Into Database"):
        try:
            customer = create_customer(payload.name, payload.email)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    with stage("Build Response"):
        return {"created": True, "customer": customer}


@app.get("/customers")
async def get_customers() -> dict[str, object]:
    with stage("Fetch Customers"):
        customers = list_customers()

    with stage("Build Response"):
        return {"count": len(customers), "customers": customers}
