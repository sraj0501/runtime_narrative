# runtime-narrative

Turn any Python execution into a traceable **story** composed of named **stages**. Get minimal logs when everything works — and surgical, LLM-powered diagnostics the moment something breaks.

```
▶ Story started: Import Customers
✔ Load CSV           0.012s
✔ Validate Data      0.004s

❌ Failure at: Insert Records

  ValueError: duplicate customer id
  Location:   app/db.py:47  insert_row
  Code:       raise ValueError("duplicate customer id")
  Chain:      ValueError ← sqlite3.IntegrityError

  ## Exact Why
  A record with the same customer_id already exists (UNIQUE constraint).

  ## Targeted Fix
  Use INSERT OR IGNORE, or check for an existing row before inserting.
```

---

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Decorators](#decorators)
- [Auto-instrumentation](#auto-instrumentation)
- [Failure diagnostics](#failure-diagnostics)
- [Failure analyzers](#failure-analyzers)
- [Renderers](#renderers)
- [Framework integrations](#framework-integrations)
- [Async task groups](#async-task-groups)
- [Persistence and CLI](#persistence-and-cli)
- [Alert routing](#alert-routing)
- [Testing utilities](#testing-utilities)
- [Custom renderers and analyzers](#custom-renderers-and-analyzers)
- [Utilities](#utilities)
- [Sub-stories and log capture](#sub-stories-and-log-capture)
- [Environment variables](#environment-variables)

---

## Installation

```bash
pip install runtime-narrative
```

Optional extras unlock additional renderers and integrations:

| Extra | What it installs |
|---|---|
| `console` | `typer` — colored terminal output in `ConsoleRenderer` |
| `fastapi` | `starlette` — `RuntimeNarrativeMiddleware` |
| `otel` | `opentelemetry-api`, `opentelemetry-sdk` — `OtelRenderer`, `OtelLogRenderer`, `OtelMetricsRenderer` |
| `prometheus` | `prometheus-client` — `PrometheusRenderer` |
| `anthropic` | `anthropic` — `AnthropicFailureAnalyzer` |
| `django` | `django` — `RuntimeNarrativeDjangoMiddleware` / `SyncMiddleware` |
| `celery` | `celery` — `NarrativeTask`, `connect_narrative` |
| `grpc` | `grpcio` — `RuntimeNarrativeInterceptor` / `AsyncInterceptor` |
| `all` | Everything above |

```bash
pip install "runtime-narrative[console,fastapi,anthropic]"
pip install "runtime-narrative[all]"
```

---

## Quick start

### Sync

```python
from runtime_narrative import story, stage

with story("Import Customers"):
    with stage("Load CSV"):
        rows = load_csv("customers.csv")

    with stage("Validate Data"):
        validate(rows)

    with stage("Insert Records"):
        db.insert(rows)
```

`ConsoleRenderer` is the default. On failure it prints the exact frame, a source snippet, the exception chain, and a compressed stack summary — no configuration needed.

### Async

```python
import asyncio
from runtime_narrative import story, stage

async def run():
    async with story("Sync Pipeline"):
        async with stage("Fetch Orders"):
            orders = await fetch_orders()

        async with stage("Process Orders"):
            await process(orders)

asyncio.run(run())
```

`story` and `stage` are dual sync/async context managers — use `with` or `async with` interchangeably.

### Track progress

Declare the total stage count upfront so `progress_percent` is accurate at every stage boundary:

```python
with story("Import Customers", total_stages=3) as runtime:
    with stage("Load CSV"):    ...   # 33%
    with stage("Validate"):   ...   # 66%
    with stage("Insert"):     ...   # 100%
```

Or set it dynamically after the story starts:

```python
with story("Batch Job") as runtime:
    items = fetch_batch()
    runtime.set_total_stages(len(items))
    for item in items:
        with stage(f"Process {item.id}"): ...
```

---

## Decorators

Wrap functions without restructuring call sites. The library detects `async def` automatically:

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_stage("Load CSV")
def load_csv() -> list[str]:
    return open("customers.csv").read().splitlines()

@runtime_narrative_stage("Insert Records")
def insert(rows: list[str]) -> None:
    db.insert_many(rows)

@runtime_narrative_story("Import Customers")
def run() -> None:
    rows = load_csv()
    insert(rows)
```

`@runtime_narrative_story` accepts the same keyword arguments as `story()`: `renderers`, `failure_analyzer`, `background_analysis`, `diagnostics_config`, `failure_diagnostics`, `allow_rich_in_production`, `app_roots`, `redact_extra`, `total_stages`, `dry_run`.

---

## Auto-instrumentation

Instrument an entire class or module without wrapping every function individually.

### `@narrative_class`

Every public instance method becomes a stage. Stage names are `ClassName.method_name`:

```python
from runtime_narrative import narrative_class, no_stage, story

@narrative_class
class OrderService:
    def validate(self, order: dict) -> None: ...   # → "OrderService.validate"
    def charge(self, order: dict) -> str: ...      # → "OrderService.charge"
    def fulfill(self, order: dict) -> str: ...     # → "OrderService.fulfill"

    @no_stage
    def _log(self, msg: str) -> None: ...          # excluded

svc = OrderService()
with story("Process Order", total_stages=3):
    svc.validate(order)
    svc.charge(order)
    svc.fulfill(order)
```

Skipped by default: names starting with `_`, `@no_stage`-marked methods, `@property`, `@staticmethod`, `@classmethod`, and inherited methods. Opt in to class and static methods explicitly:

```python
@narrative_class(instrument_classmethods=True, instrument_staticmethods=True)
class Factory:
    @classmethod
    def create(cls): ...       # → "Factory.create"

    @staticmethod
    def validate(x): ...       # → "Factory.validate"

    @classmethod
    @narrative_stage("Build Widget")
    def build(cls): ...        # → "Build Widget" (custom name)
```

### `@narrative_stage`

Override the stage name on a single method or standalone function. Prevents double-wrapping when used inside `@narrative_class`:

```python
from runtime_narrative import narrative_class, narrative_stage

@narrative_class
class ReportService:
    @narrative_stage("Generate PDF Report")
    def generate(self, data: dict) -> bytes: ...   # custom name

    def archive(self, report: bytes) -> None: ...  # "ReportService.archive" (default)
```

When `name` is omitted, the function name is title-cased: `validate_order` → `"Validate Order"`.

### `@no_stage`

Exclude any method or function from all auto-instrumentation:

```python
from runtime_narrative import no_stage

@no_stage
def _cache_lookup(key: str): ...
```

### `instrument_module`

Instrument all public callables in an existing module in-place. Classes get `@narrative_class`; top-level functions are wrapped directly. Imported symbols are not touched:

```python
import runtime_narrative
import myapp.services as svc

runtime_narrative.instrument_module(svc)
```

### `auto_instrument`

Register a `sys.meta_path` import hook that instruments every app module on import. Only modules whose source path is under `app_roots` (default: `cwd`) are affected — stdlib and installed packages are unaffected:

```python
import runtime_narrative

finder = runtime_narrative.auto_instrument()

# All subsequent imports of app modules are instrumented automatically.
from myapp.services import OrderService

# Stop at any point:
import sys
sys.meta_path.remove(finder)
```

Pin to specific directories:

```python
runtime_narrative.auto_instrument(app_roots=["/app/src", "/app/workers"])
```

---

## Failure diagnostics

### Lean vs rich mode

| Mode | What is captured |
|---|---|
| `lean` (default) | Primary frame, source snippet (±2 lines), exception chain, compressed stack summary |
| `rich` | Everything in lean + local variable values for up to 2 frames, with automatic secret redaction |

```bash
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich python app.py
```

Or per-story:

```python
with story("Import", failure_diagnostics="rich"):
    ...
```

### Production safeguards

When `RUNTIME_NARRATIVE_ENV=production`:
- Tracebacks are capped at 8 000 characters.
- `rich` mode is silently downgraded to `lean` to prevent local variable leakage in logs.

Override the downgrade when needed:

```python
with story("Debug", failure_diagnostics="rich", allow_rich_in_production=True):
    ...
```

### Secret redaction

Rich mode automatically redacts local variables whose key names contain any of: `password`, `secret`, `token`, `api_key`, `apikey`, `authorization`, `cookie`, `session`, `credential`.

Extend the list with project-specific names:

```python
with story("Import", failure_diagnostics="rich", redact_extra=["internal_id", "org_key"]):
    ...
```

For more expressive rules, use `FailureDiagnosticsConfig`:

```python
from runtime_narrative import FailureDiagnosticsConfig

config = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    redact_patterns=("^internal_.*", r"\bpii\b"),   # regex, case-insensitive re.search
    redact_callback=lambda key: key.startswith("priv_"),
)

with story("Import", diagnostics_config=config):
    ...
```

`redact_callback` exceptions are caught and treated as non-redact. Both `redact_patterns` and `redact_callback` are available on `FailureDiagnosticsConfig` and flow through `merge()`.

### Full `FailureDiagnosticsConfig` reference

```python
from runtime_narrative import FailureDiagnosticsConfig

config = FailureDiagnosticsConfig(
    runtime_environment="production",       # "development" | "production"
    failure_diagnostics="lean",             # "lean" | "rich"
    allow_rich_in_production=False,
    app_roots=("/app/src",),                # paths used for primary frame selection
    redact_extra=("internal_id",),          # additional substring matches
    redact_patterns=("^priv_",),            # regex patterns (case-insensitive)
    redact_callback=lambda k: k.endswith("_key"),
    max_traceback_chars=12_000,             # development cap (None = unlimited)
    production_traceback_cap=8_000,
    max_locals_per_frame=12,
    max_local_value_len=200,
    max_local_depth=2,
    max_frames_with_locals=2,
    snippet_context_lines=2,
)

with story("Import", diagnostics_config=config):
    ...
```

`FailureDiagnosticsConfig.from_env()` reads the standard environment variables. `FailureDiagnosticsConfig.merge(base, **overrides)` layers per-story overrides on a base config.

---

## Failure analyzers

Analyzers receive structured failure data and return a diagnosis string that is attached to `FailureOccurred` and displayed by renderers. All analyzers are optional — if the endpoint is unreachable, your exception propagates normally.

### `OllamaFailureAnalyzer`

Calls a local Ollama instance or any `/api/generate`-compatible endpoint:

```python
from runtime_narrative import OllamaFailureAnalyzer, story

analyzer = OllamaFailureAnalyzer(
    model="llama3",
    endpoint="http://127.0.0.1:11434/api/generate",  # default
    timeout_seconds=60.0,
    max_context_chars=8000,
)

with story("Import Customers", failure_analyzer=analyzer):
    ...
```

### `LLMFailureAnalyzer`

Calls any OpenAI-compatible `/v1/chat/completions` endpoint (OpenAI, vLLM, llama.cpp, LM Studio, Ollama OpenAI mode):

```python
from runtime_narrative import LLMFailureAnalyzer

analyzer = LLMFailureAnalyzer(
    model="gpt-4o-mini",
    endpoint="https://api.openai.com/v1/chat/completions",
    api_key="sk-...",
    max_context_chars=8000,
)
```

### `AnthropicFailureAnalyzer` (`[anthropic]` extra)

Uses the Anthropic Claude API. Reads `ANTHROPIC_API_KEY` from the environment by default:

```python
from runtime_narrative import AnthropicFailureAnalyzer

analyzer = AnthropicFailureAnalyzer(
    model="claude-haiku-4-5-20251001",   # default
    api_key="sk-ant-...",                # or set ANTHROPIC_API_KEY
    max_tokens=1024,
    timeout_seconds=30.0,
)
```

Both `analyze_failure()` (sync) and `analyze_failure_async()` (async) are implemented. The async path uses `anthropic.AsyncAnthropic` natively — no thread offloading.

### Structured output

All analyzers request a JSON response (`exact_why`, `evidence`, `targeted_fix`, `code_changes`) and format it into guaranteed `## Header\ncontent` sections. Falls back to raw text when the model returns non-JSON.

### Context budget

Tracebacks are trimmed from the top (keeping the most recent frames) when the prompt would exceed `max_context_chars`. If the budget is exhausted before any traceback fits, a `<traceback omitted>` marker is used:

```python
analyzer = LLMFailureAnalyzer(model="llama3", max_context_chars=4000)
```

### `DeduplicatingAnalyzer`

Wraps any analyzer with an LRU cache keyed by `SHA-256(error_type, filename, lineno, exception_chain)`. Prevents redundant LLM calls for the same recurring error. `None` results (timeouts, network errors) are never cached:

```python
from runtime_narrative import DeduplicatingAnalyzer, AnthropicFailureAnalyzer

analyzer = DeduplicatingAnalyzer(
    AnthropicFailureAnalyzer(),
    max_cache_size=256,
)
```

Thread-safe; async-aware (delegates to `analyze_failure_async` when available).

### Background analysis

`background_analysis=True` emits `FailureOccurred` immediately (with `llm_analysis=None`), then runs the LLM as a background `asyncio.Task`. When the task completes, `LLMAnalysisReady` is emitted:

```python
async with story(
    "Process Order",
    failure_analyzer=analyzer,
    background_analysis=True,
):
    ...
# Response is not delayed by LLM latency.
# LLMAnalysisReady fires when analysis is ready.
```

### `FailureAnalyzer` protocol

All built-in analyzers satisfy the `@runtime_checkable` `FailureAnalyzer` protocol. Use it to type-check custom analyzers:

```python
from runtime_narrative import FailureAnalyzer

assert isinstance(my_analyzer, FailureAnalyzer)
```

---

## Renderers

A renderer is any object with `handle(self, event: object) -> None` (sync) or `async def handle(self, event: object) -> None` (async). Pass a list to `story()`, middleware, or a decorator. Async renderers are awaited inside `async with story(...)` including for stage events.

Renderers never crash a story — if a renderer raises, a warning is printed to stderr and the next renderer continues.

### `ConsoleRenderer` (default)

Colored terminal output for local development. Falls back to `print` and ASCII glyphs (`>`, `[ok]`, `[FAIL]`) when `typer` is absent or the terminal is not UTF-8 (e.g. Windows cp1252). Every line is tagged with a `[short_id]` (first 6 characters of `story_id`), color-coded per story family, and indented by nesting depth — see [Sub-stories and log capture](#sub-stories-and-log-capture) for how this looks with nested stages and sub-stories:

```python
from runtime_narrative import ConsoleRenderer

with story("My Pipeline", renderers=[ConsoleRenderer()]):
    ...
```

### `JsonRenderer`

One structured JSON object per lifecycle event. Suitable for log aggregators (Datadog, CloudWatch, Loki):

```python
from runtime_narrative import JsonRenderer

with story("My Pipeline", renderers=[JsonRenderer()]):
    ...

# Write to a file
with story("My Pipeline", renderers=[JsonRenderer(output=open("stories.jsonl", "a"))]):
    ...
```

On failure, `FailureOccurred` carries the full diagnostics payload: exact location, stack frame classifications, source snippet, local variables (rich mode), compressed stack summary, and traceback text.

### `RotatingJsonRenderer`

Same as `JsonRenderer` but writes to a rotating log file using `path.1` / `path.2` semantics. No external dependencies:

```python
from runtime_narrative import RotatingJsonRenderer

renderer = RotatingJsonRenderer(
    "stories.jsonl",
    max_bytes=10_485_760,  # rotate at 10 MB (default)
    backup_count=5,        # keep .1 through .5 (default)
)
```

### `HtmlReportRenderer`

Writes a self-contained HTML report on `StoryCompleted`. Includes a story header, per-stage duration bar chart, and a failure detail section with traceback and optional LLM analysis:

```python
from runtime_narrative import HtmlReportRenderer

with story("ETL Run", renderers=[HtmlReportRenderer("report.html", open_browser=True)]):
    ...
```

`open_browser=True` calls `webbrowser.open()` on the generated file after writing.

### `SqliteStoryRenderer`

Persists all six lifecycle events to a SQLite database. No extra dependencies. See [Persistence and CLI](#persistence-and-cli):

```python
from runtime_narrative import SqliteStoryRenderer

with story("Nightly ETL", renderers=[SqliteStoryRenderer("stories.db")]):
    ...
```

### `OtelRenderer` (`[otel]` extra)

Maps narrative events to OpenTelemetry spans. Each story is a root span; each stage is a child span:

```python
from runtime_narrative import OtelRenderer

renderer = OtelRenderer(
    exclude_stages={"Health Check"},  # never create child spans for these stages
    min_duration_ms=5.0,              # suppress spans shorter than 5 ms
    max_attribute_length=8192,        # truncate long string attributes (default)
)
```

Attributes on failure spans: `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `error.stack_trace`, `narrative.exception_chain`. `LLMAnalysisReady` adds a `llm_analysis_ready` span event with `narrative.llm_analysis`.

`exclude_stages` stages that fail still mark the root span `ERROR` — only the child span is suppressed.

### `OtelLogRenderer` (`[otel]` extra)

Emits all six lifecycle events as OpenTelemetry log records via `opentelemetry._logs`:

| Event | Severity |
|---|---|
| `StoryStarted`, `StoryCompleted`, `LLMAnalysisReady` | `INFO` |
| `StageStarted`, `StageCompleted` | `DEBUG` |
| `FailureOccurred` | `ERROR` with `error.type`, `code.filepath`, `error.stack_trace`, etc. |

Automatically correlates `trace_id`/`span_id` from the ambient OTel context so logs link to their enclosing spans:

```python
from runtime_narrative import OtelLogRenderer

renderer = OtelLogRenderer(logger_name="my_app")
```

### `OtelMetricsRenderer` (`[otel]` extra)

Emits four OTel instruments via the OpenTelemetry Metrics API:

| Instrument | Type | Labels |
|---|---|---|
| `narrative.stage.duration` | Histogram (s) | `story_name`, `stage_name` |
| `narrative.story.duration` | Histogram (s) | `story_name`, `success` |
| `narrative.story.failures` | Counter | `story_name`, `error_type` |
| `narrative.llm.analysis_latency` | Histogram (s) | `story_name` |

`narrative.llm.analysis_latency` measures the time between `FailureOccurred` and `LLMAnalysisReady` (only recorded when `background_analysis=True`):

```python
from runtime_narrative import OtelMetricsRenderer

renderer = OtelMetricsRenderer(meter_name="my_app")
```

### `PrometheusRenderer` (`[prometheus]` extra)

Exposes four Prometheus metrics:

| Metric | Type | Labels |
|---|---|---|
| `narrative_story_duration_seconds` | Histogram | `story_name`, `success` |
| `narrative_stage_duration_seconds` | Histogram | `story_name`, `stage_name` |
| `narrative_story_failures_total` | Counter | `story_name`, `error_type` |
| `narrative_story_total` | Counter | `story_name`, `success` |

```python
from runtime_narrative import PrometheusRenderer
from prometheus_client import CollectorRegistry, start_http_server

registry = CollectorRegistry()
renderer = PrometheusRenderer(registry=registry)
start_http_server(8000, registry=registry)
```

### Combining renderers

```python
from runtime_narrative import story, JsonRenderer, SqliteStoryRenderer, OtelRenderer

with story("Nightly ETL", renderers=[
    JsonRenderer(),
    SqliteStoryRenderer("stories.db"),
    OtelRenderer(),
]):
    ...
```

---

## Framework integrations

### FastAPI / Starlette

`RuntimeNarrativeMiddleware` wraps every HTTP request in `async with story(...)`. Route handlers only need to declare stages — no `story()` context required in handlers:

```python
from fastapi import FastAPI
from runtime_narrative import RuntimeNarrativeMiddleware, JsonRenderer, AnthropicFailureAnalyzer

app = FastAPI()
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[JsonRenderer()],
    failure_analyzer=AnthropicFailureAnalyzer(),
    runtime_environment="production",
)

@app.post("/orders")
async def create_order(payload: OrderIn):
    with stage("Validate Input"):
        validate(payload)
    with stage("Persist Order"):
        order = await db.insert(payload)
    return {"id": order.id}
```

Each request becomes a story named `"METHOD /path"` (e.g. `"POST /orders"`). When `renderers` is not passed, the middleware auto-selects `ConsoleRenderer` on a TTY and `JsonRenderer` otherwise.

When `opentelemetry-api` is installed, the middleware automatically extracts incoming W3C `traceparent`/`tracestate` headers so story spans become children of the upstream trace:

```python
app.add_middleware(
    RuntimeNarrativeMiddleware,
    propagate_trace_context=True,   # default; set False to disable
)
```

Use `skip_if` to bypass story wrapping for specific routes (health checks, readiness probes, etc.):

```python
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[JsonRenderer()],
    skip_if=lambda req: req.url.path in {"/health", "/ready"},
)
```

Run: `uv run python examples/middleware_skip_if.py`

### Django

**ASGI (async):**

```python
# settings.py
MIDDLEWARE = [
    "runtime_narrative.middleware_django.RuntimeNarrativeDjangoMiddleware",
    ...
]
```

**WSGI (sync):**

```python
# settings.py
MIDDLEWARE = [
    "runtime_narrative.middleware_django.RuntimeNarrativeDjangoSyncMiddleware",
    ...
]
```

Story name is `"METHOD /path"`. Requires `pip install "runtime-narrative[django]"`.

### Celery

```python
from celery import Celery
from runtime_narrative import NarrativeTask, connect_narrative, JsonRenderer

app = Celery("myapp")

# Option A — per task
@app.task(base=NarrativeTask)
def process_order(order_id: str) -> None:
    with stage("Validate"): validate(order_id)
    with stage("Charge"):   charge(order_id)

# Option B — set defaults for all tasks globally
connect_narrative(
    app,
    renderers=[JsonRenderer()],
    failure_analyzer=AnthropicFailureAnalyzer(),
)
```

Story name is `"<task.name> [task_id=<id>]"`. Override options per task by setting `narrative_*` class attributes directly. Requires `pip install "runtime-narrative[celery]"`.

### gRPC

```python
import grpc
from runtime_narrative import RuntimeNarrativeAsyncInterceptor, JsonRenderer

# Async server
server = grpc.aio.server(
    interceptors=[RuntimeNarrativeAsyncInterceptor(renderers=[JsonRenderer()])],
)

# Sync server
from runtime_narrative import RuntimeNarrativeInterceptor
server = grpc.server(
    thread_pool,
    interceptors=[RuntimeNarrativeInterceptor(renderers=[JsonRenderer()])],
)
```

Story name is the full gRPC method path, e.g. `"/mypackage.MyService/MyMethod"`. Requires `pip install "runtime-narrative[grpc]"`.

---

## Async task groups

`NarrativeTaskGroup` runs concurrent `asyncio` tasks under a shared story. Tasks inherit the parent story context automatically via `ContextVar` copy, so `stage()` calls inside tasks are tracked normally:

```python
import asyncio
from runtime_narrative import story, NarrativeTaskGroup, NarrativeTaskGroupError

async def main():
    async with story("Parallel Pipeline"):
        async with NarrativeTaskGroup() as tg:
            tg.create_task(fetch_orders(),    name="Fetch Orders")
            tg.create_task(fetch_inventory(), name="Fetch Inventory")
        # waits for both; stages from both appear in the timeline

asyncio.run(main())
```

If tasks fail, `NarrativeTaskGroupError` is raised with `failed_tasks: dict[str, BaseException]`:

```python
try:
    async with NarrativeTaskGroup() as tg:
        tg.create_task(risky_job(), name="Risky Job")
except NarrativeTaskGroupError as e:
    for task_name, exc in e.failed_tasks.items():
        print(f"{task_name} failed: {exc}")
```

No extra dependencies. Python 3.9+.

---

## Persistence and CLI

`SqliteStoryRenderer` records all six lifecycle events to a local SQLite database. No extra dependencies:

```python
from runtime_narrative import story, SqliteStoryRenderer

with story("Nightly ETL", renderers=[SqliteStoryRenderer("stories.db")]):
    ...
```

**Schema:**

| Table | Key columns |
|---|---|
| `stories` | `story_id`, `name`, `success`, `duration_seconds`, `started_at`, `completed_at` |
| `stages` | `story_id`, `stage_name`, `stage_index`, `parent_stage_name`, `duration_seconds`, `completed`, `failed` |
| `failures` | `story_id`, `stage_name`, `error_type`, `error_message`, `filename`, `lineno`, `traceback_text`, `llm_analysis` |

`LLMAnalysisReady` back-fills the `llm_analysis` column in `failures` so background analysis results are persisted even when they arrive after `StoryCompleted`.

**CLI** (registered as `runtime-narrative`):

```bash
# List the 10 most recent failures
runtime-narrative failures --db stories.db

# Filter by stage name or story name (LIKE pattern)
runtime-narrative failures --last 25 --stage "Insert Records"
runtime-narrative failures --story "Nightly ETL"

# Show the full detail for one story
runtime-narrative story <story_id> --db stories.db
```

The `--db` flag defaults to `runtime_narrative.db` in the current directory.

---

## Alert routing

`AlertRoutingRenderer` fans out `FailureOccurred` events to webhook destinations concurrently. Destination failures are logged to stderr and swallowed — they never crash the story:

```python
from runtime_narrative import (
    story,
    AlertRoutingRenderer,
    SlackWebhookDestination,
    HttpWebhookDestination,
)

renderer = AlertRoutingRenderer(
    destinations=[
        SlackWebhookDestination("https://hooks.slack.com/services/..."),
        HttpWebhookDestination(
            "https://alerts.example.com/webhook",
            headers={"Authorization": "Bearer ..."},
            timeout=5.0,
        ),
    ],
    only_stories={"Nightly ETL", "Payment Processor"},  # None = all stories
    only_error_types={"ValueError", "TimeoutError"},    # None = all error types
)

async with story("Nightly ETL", renderers=[renderer]):
    ...
```

`SlackWebhookDestination` sends a Block Kit message with a header, error detail section, and an optional analysis section when `llm_analysis` is present.

`HttpWebhookDestination` POSTs a JSON payload containing: `story_id`, `story_name`, `stage_name`, `error_type`, `error_message`, `filename`, `lineno`, `function`, `llm_analysis`, `timestamp`.

---

## `dry_run` mode

`dry_run=True` suppresses exceptions raised inside stage bodies, marks all stages completed, and emits `StoryCompleted(success=True)`. Useful for smoke-testing instrumentation wiring without triggering real side effects:

```python
with story("Nightly ETL", dry_run=True):
    with stage("Load Warehouse"):
        raise IOError("would connect to DB in prod")   # suppressed
    with stage("Transform"):
        raise RuntimeError("would run transforms")     # suppressed
# StoryCompleted(success=True) emitted for all stages
```

---

## Testing utilities

`StoryRecorder` is a dual sync/async context manager that captures story events for assertions. No output is produced:

```python
from runtime_narrative import stage
from runtime_narrative.testing import StoryRecorder

def test_pipeline_success():
    with StoryRecorder("ETL") as recorder:
        with stage("Load"):   rows = [1, 2, 3]
        with stage("Insert"): db.insert(rows)

    recorder.assert_stages_completed(["Load", "Insert"])
    recorder.assert_no_failure()
    recorder.assert_story_completed(success=True)

def test_invalid_input_fails_at_validate():
    import pytest

    with pytest.raises(ValueError):
        with StoryRecorder("ETL") as recorder:
            with stage("Load"):     pass
            with stage("Validate"): raise ValueError("bad schema")

    recorder.assert_stage_failed("Validate", error_type="ValueError")
    recorder.assert_story_completed(success=False)
```

Works as `async with StoryRecorder(...)` too. Pass any `story()` kwargs including `dry_run=True`:

```python
with StoryRecorder("ETL", dry_run=True) as recorder:
    run_pipeline()   # side effects suppressed

recorder.assert_stages_completed(["Load", "Validate", "Insert"])
recorder.assert_no_failure()
```

**Assertion methods:**

| Method | What it checks |
|---|---|
| `assert_stages_completed(names)` | All named stages appear in `StageCompleted` events |
| `assert_no_failure()` | No `FailureOccurred` event was emitted |
| `assert_stage_failed(name, error_type=None)` | A `FailureOccurred` event at that stage name; optionally checks `error_type` |
| `assert_story_completed(success=None)` | A `StoryCompleted` event was emitted; optionally checks the `success` flag |

---

## Custom renderers and analyzers

### Custom renderer

Implement `handle(self, event: object)`. Async renderers (`async def handle`) are awaited inside `async with story(...)`:

```python
class PagerDutyRenderer:
    async def handle(self, event: object) -> None:
        if type(event).__name__ == "FailureOccurred":
            await pagerduty.trigger(
                summary=f"{event.story_name} failed at {event.stage_name}",
                details={"error": event.error_type, "analysis": event.llm_analysis},
            )

async with story("Nightly ETL", renderers=[PagerDutyRenderer()]):
    ...
```

Six event types are emitted. Key fields on each:

| Event | Key fields |
|---|---|
| `StoryStarted` | `story_id`, `story_name`, `timestamp` |
| `StageStarted` | `story_id`, `story_name`, `stage_name`, `timestamp`, `stage_index` (0-based), `parent_stage_name` |
| `StageCompleted` | `story_id`, `story_name`, `stage_name`, `timestamp`, `duration_seconds`, `stage_index`, `parent_stage_name` |
| `FailureOccurred` | `story_id`, `story_name`, `stage_name`, `error_type`, `error_message`, `filename`, `lineno`, `function`, `traceback_text`, `exception_chain`, `exact_cause`, `stage_timeline`, `progress_percent`, `llm_analysis`, `diagnostics_mode`, `stack_frames`, `source_snippet`, `compressed_stack_summary`, `locals_by_frame` |
| `StoryCompleted` | `story_id`, `story_name`, `success`, `progress_percent`, `completed_stages`, `total_stages`, `timestamp` |
| `LLMAnalysisReady` | `story_id`, `story_name`, `stage_name`, `llm_analysis`, `timestamp` |

`parent_stage_name` is `None` for top-level stages and set to the enclosing stage name for nested stages. `story_name` on stage events lets a renderer filter by story without a `story_id → story_name` side table (run: `uv run python examples/stage_story_name.py`).

### Custom failure analyzer

Implement `analyze_failure(...)`. Add `analyze_failure_async(...)` for native async — otherwise the sync method is called via `asyncio.to_thread`:

```python
class MyAnalyzer:
    async def analyze_failure_async(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure,           # FailureSummary: .error_type, .error_message, .filename,
                           #                 .lineno, .function, .source_line,
                           #                 .traceback_text, .exception_chain
        stage_timeline: str,
        progress_percent: int,
    ) -> str | None:
        result = await my_llm_client.complete(build_prompt(failure))
        return result.text

    def analyze_failure(self, *, story_name, stage_name, failure, stage_timeline, progress_percent):
        # sync fallback used when called from sync story()
        return requests.post(...).json()["text"]

with story("Import", failure_analyzer=MyAnalyzer()):
    ...
```

---

## Utilities

### `has_active_story()`

Returns `True` when a `story()` context is active in the current sync or async context. Useful for library code that should behave differently when called under instrumentation:

```python
from runtime_narrative import has_active_story

def send_email(to: str, body: str) -> None:
    if has_active_story():
        # stage() is safe here
        with stage("Send Email", optional=True):
            _send(to, body)
    else:
        _send(to, body)
```

### `stage(optional=True)`

When `optional=True`, a `stage()` outside an active story is a no-op — no exception, no events, no tracking. When inside a story it behaves normally. Ideal for shared utilities:

```python
from runtime_narrative import stage

def enrich_record(record: dict) -> dict:
    with stage("Enrich Record", optional=True):
        return _lookup(record)
    return record   # reached only when no story active
```

Run: `uv run python examples/optional_stage.py`

### `StoryRuntime.record_failure()`

Emits a `FailureOccurred` event (with full diagnostics) without owning exception propagation. Use this in saga/rollback flows where a compensating action fails but you want the story to complete successfully:

```python
async with story("Payment Saga", renderers=[JsonRenderer()]) as runtime:
    async with stage("Charge Card"):
        charge_id = await charge(order)

    try:
        async with stage("Reserve Inventory"):
            await reserve(order)
    except InventoryError as exc:
        async with stage("Refund Charge"):
            await refund(charge_id)
        await runtime.record_failure(exc, stage_name="Reserve Inventory")
        # FailureOccurred emitted; story still completes success=True
```

Run: `uv run python examples/saga_record_failure.py`

---

## Sub-stories and log capture

### Sub-stories

Opening a `story()` while another is already active (in the same sync/async context) makes it a **sub-story**: it inherits the parent's `renderers`, `diagnostics_config`, and `failure_analyzer` unless you pass your own, and its `StoryStarted`/`StoryCompleted`/`FailureOccurred` events carry `parent_story_id` and `root_story_id` so the whole call tree can be reconstructed from events alone — no new API, no tree data structure to maintain yourself:

```python
async def create_order(payload):
    async with story(f"POST /orders") as api_story:
        async with stage("Persist Order"):
            # Same story() primitive. Because api_story is already active,
            # this becomes a sub-story: parent_story_id == api_story.story_id,
            # root_story_id == api_story.story_id (or further up if api_story
            # is itself nested), and renderers/diagnostics are inherited.
            async with story("DB: INSERT orders") as db_story:
                async with stage("Execute Query"):
                    await conn.execute("INSERT INTO orders ...")
```

Each sub-story succeeds or fails independently (a failed DB call doesn't automatically fail the API story unless the exception propagates or you call `record_failure`), and gets its own `duration_seconds` on `StoryCompleted`. `OtelRenderer` maps this to proper parent/child spans automatically.

Because linkage is derived from `ContextVar` state at the moment `story()` is entered — not from a shared registry — the same reusable function (e.g. a `execute_query()` helper) can be called from many different parent stories, including concurrently: `asyncio.Task` copies context at creation and each OS thread starts with a fresh top-level context, so concurrent API calls sharing one DB helper never cross-contaminate each other's story tree.

Run: `uv run python examples/substory_db_call.py`

### `NarrativeLogHandler` — capture existing `logging` calls into a story

If your application already uses `logging.warning()`/`.error()`, `NarrativeLogHandler` routes those records into the same event pipeline as `story()`/`stage()` — one stream instead of two:

```python
import logging
from runtime_narrative import NarrativeLogHandler

logging.getLogger().addHandler(NarrativeLogHandler(level=logging.WARNING))
```

Each captured record becomes a `LogRecorded` event (`story_id`, `root_story_id`, `stage_name`, `level`, `logger_name`, `message`, optional `exc_text`) emitted through the active story's renderers. Outside an active story, records fall through to an optional `fallback` handler so nothing is silently dropped:

```python
NarrativeLogHandler(level=logging.WARNING, fallback=logging.StreamHandler())
```

`ConsoleRenderer` prints every event (including `LogRecorded`) with a `[short_id]` tag — the first 6 characters of that event's `story_id` — so a specific call is identifiable when scanning or searching output. All events belonging to one story family (a root story and any sub-stories) additionally render in the same deterministic color, and lines are indented one level per stage/sub-story nesting depth, so the call tree (API call → DB sub-story → its own stages) is visible directly in the log output:

```
[ad8cc2] ▶ Story started: POST /orders
  [ad8cc2] ▶ Stage started: Persist Order
    [d17c63] ▶ Story started: DB: INSERT orders
      [d17c63] ▶ Stage started: Execute Query
      [d17c63] ✔ Stage completed: Execute Query (0.021s)
    [d17c63] ▶ Story ended: SUCCESS (0.034s)
  [ad8cc2] ✔ Stage completed: Persist Order (0.034s)
[ad8cc2] ▶ Story ended: SUCCESS (0.052s)
```

Run: `uv run python examples/logging_bridge.py`

---

## Environment variables

| Variable | Values | Default | Effect |
|---|---|---|---|
| `RUNTIME_NARRATIVE_ENV` | `development`, `production` | `development` | Production caps tracebacks to 8 000 chars and forces lean mode |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean`, `rich` | `lean` | `rich` captures local variable values at the failing frames. Invalid values raise `ValueError` at story construction. |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | `1`, `true` | off | Bypass production safeguard; allow rich diagnostics in production |
| `RUNTIME_NARRATIVE_MODEL` | model name string | — | Default model for `AnthropicFailureAnalyzer`; also used by example scripts for `OllamaFailureAnalyzer` / `LLMFailureAnalyzer` |
| `ANTHROPIC_API_KEY` | API key | — | Required by `AnthropicFailureAnalyzer`; read automatically if `api_key=` is not passed |

---

## Python compatibility

Python 3.9 – 3.13. Zero required dependencies beyond `python-dotenv`.
