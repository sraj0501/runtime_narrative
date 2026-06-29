# runtime-narrative

**Turn any Python application into a traceable story. Get minimal logs when everything works — and surgical, LLM-powered diagnostics the moment something breaks.**

---

## The idea

Most logging tells you *that* something failed. `runtime-narrative` tells you *why* — with full awareness of every step that succeeded before the failure, what was supposed to happen next, and (optionally) a plain-English suggestion for how to fix it.

You model your application's execution as a **story** made up of **stages**. Each function or logical unit of work becomes a stage. The library watches everything:

- **When a stage passes:** one line — `✔ Stage completed: Validate Input (0.003s)`. No noise.
- **When anything fails:** a structured failure report with the exact file, line number, failing statement, the full timeline of what succeeded before it, and — if you plug in an LLM — a concrete logical fix suggestion.

This combines debugging and logging into a single mechanism: logs are minimal until something breaks, then they are explicit and actionable.

---

## Install

Zero dependencies at the core:

```bash
pip install runtime-narrative
```

Optional extras:

```bash
pip install "runtime-narrative[console]"    # colored terminal output (typer)
pip install "runtime-narrative[fastapi]"    # FastAPI/Starlette middleware
pip install "runtime-narrative[otel]"       # OpenTelemetry trace renderer
pip install "runtime-narrative[prometheus]" # Prometheus metrics renderer
pip install "runtime-narrative[anthropic]"  # Anthropic Claude failure analyzer
pip install "runtime-narrative[django]"     # Django WSGI/ASGI middleware
pip install "runtime-narrative[celery]"     # Celery task integration
pip install "runtime-narrative[grpc]"       # gRPC server interceptors
pip install "runtime-narrative[all]"        # everything above
```

---

## Quick start

```python
from runtime_narrative import story, stage, StoryRuntime  # StoryRuntime for type hints

with story("Import Customers"):
    with stage("Load CSV"):
        rows = load_csv("customers.csv")

    with stage("Validate Data"):
        validate(rows)

    with stage("Insert Records"):
        db.insert(rows)
```

**Everything works — minimal output:**

```
▶ Story started: Import Customers
✔ Stage completed: Load CSV (0.012s)
✔ Stage completed: Validate Data (0.004s)
✔ Stage completed: Insert Records (0.089s)
▶ Story ended: SUCCESS
```

**Something fails — full context, no guessing:**

```
▶ Story started: Import Customers
✔ Stage completed: Load CSV (0.012s)
✔ Stage completed: Validate Data (0.004s)

❌ Failure detected
Story:         Import Customers
Stage:         Insert Records
Error:         ValueError - duplicate customer id
Location:      app/db.py:47 (insert_row)
Code:          raise ValueError("duplicate customer id")
Recent stages: Load CSV=completed (0.012s) | Validate Data=completed (0.004s) | Insert Records=failed (0.001s)
Progress:      66% (2 / 3)
```

The library knows what succeeded before the failure. That context is always part of the report.

Async code uses identical syntax with `async with`:

```python
async with story("Import Customers"):
    async with stage("Load CSV"):
        rows = await load_csv("customers.csv")

    async with stage("Insert Records"):
        await db.insert(rows)
```

---

## LLM-powered failure analysis (optional)

Plug in any local or remote LLM. When a failure occurs, the library packages the story name, stage name, error type, exact failing line, exception chain, and traceback — and asks the LLM for a targeted diagnostic.

```python
from runtime_narrative import story, stage, OllamaFailureAnalyzer

analyzer = OllamaFailureAnalyzer(model="llama3")

with story("Import Customers", failure_analyzer=analyzer):
    with stage("Load CSV"):
        rows = load_csv("customers.csv")
    with stage("Insert Records"):
        db.insert(rows)
```

The LLM response is structured and rendered inline:

```
+-- LLM Debug -----------------------------------------------------------+
| Exact Why                                                              |
| The INSERT fails because customer_id already exists in the customers   |
| table (UNIQUE constraint). The error is raised at db.py:47.           |
|                                                                        |
| Evidence                                                               |
| ValueError: duplicate customer id — raised after catching a            |
| sqlite3.IntegrityError from the underlying INSERT call.               |
|                                                                        |
| Targeted Fix                                                           |
| Use INSERT OR IGNORE, or check for existence before inserting.        |
| Alternatively, catch the duplicate and return the existing record.    |
|                                                                        |
>> Code Changes                                                          |
| db.py:47 — wrap the insert in try/except IntegrityError and handle    |
| the duplicate case explicitly rather than re-raising ValueError.      |
+------------------------------------------------------------------------+
```

> **Note:** The LLM suggests logical fixes only — it does not rewrite your code. The suggestion names the exact location, explains what went wrong mechanically, and tells you what to change. What you change is up to you.

### Analyzer options

| Class | API | Use case |
|---|---|---|
| `OllamaFailureAnalyzer` | Ollama native `/api/generate` | Local Ollama |
| `LLMFailureAnalyzer` | OpenAI-compatible `/v1/chat/completions` | vLLM, llama.cpp, LM Studio, Ollama OpenAI mode, any hosted API |
| `AnthropicFailureAnalyzer` | Anthropic API | Claude Haiku / Sonnet / Opus (`[anthropic]` extra required) |

```python
from runtime_narrative import LLMFailureAnalyzer

analyzer = LLMFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:8000/v1/chat/completions",
)
```

All analyzers fall back silently if the endpoint is unreachable — your application's exception still propagates normally.

All analyzers request structured JSON (`exact_why`, `evidence`, `targeted_fix`, `code_changes`) from the model and render it into guaranteed `## Header` sections. Responses that are not valid JSON fall back to raw text.

### Anthropic Claude analyzer

`AnthropicFailureAnalyzer` requires the `[anthropic]` extra and an `ANTHROPIC_API_KEY` environment variable. Defaults to `claude-haiku-4-5-20251001`; override via `model=` or the `RUNTIME_NARRATIVE_MODEL` env var:

```python
from runtime_narrative import story, stage, AnthropicFailureAnalyzer

analyzer = AnthropicFailureAnalyzer()          # reads ANTHROPIC_API_KEY from env
# or explicitly:
analyzer = AnthropicFailureAnalyzer(
    api_key="sk-ant-...",
    model="claude-sonnet-4-6",
    max_tokens=1024,
    timeout_seconds=30.0,
)

async with story("Import Customers", failure_analyzer=analyzer):
    async with stage("Insert Records"):
        db.insert(rows)
```

### Context budget

All analyzers accept `max_context_chars: int = 8000`. When the traceback would push the prompt over budget, it is trimmed from the top (keeping the most recent frames). If the budget is exhausted entirely, a `<traceback omitted>` marker is used instead:

```python
analyzer = LLMFailureAnalyzer(model="llama3", max_context_chars=4000)
```

### Failure deduplication

`DeduplicatingAnalyzer` wraps any analyzer with an LRU cache. Repeated failures at the same location return the cached suggestion immediately — no redundant LLM calls:

```python
from runtime_narrative import DeduplicatingAnalyzer, OllamaFailureAnalyzer

analyzer = DeduplicatingAnalyzer(
    OllamaFailureAnalyzer(model="llama3"),
    max_cache_size=256,   # LRU eviction above this count
)
```

Cache key is a SHA-256 hash of `(error_type, filename, lineno, exception_chain)`. `None` results (network errors, timeouts) are never cached — next call retries the model. Thread-safe; works with both sync and async analysis paths.

### Background analysis

For latency-sensitive services, use `background_analysis=True`. The `FailureOccurred` event is emitted immediately (so your error response is not delayed), and the LLM runs as a background task. When it finishes, a `LLMAnalysisReady` event is emitted:

```python
async with story("Process Order", failure_analyzer=analyzer, background_analysis=True):
    async with stage("Charge Payment"):
        await charge(order)
```

---

## Diagnostics depth

The library operates in two modes, controlled by environment variable or per-story kwargs:

| Mode | What you get |
|---|---|
| `lean` (default) | Error type, message, exact location, source line, exception chain, compressed stack summary |
| `rich` | Everything above + source code snippet (±2 lines around the error) + local variable values at the failing frame, with automatic redaction of secrets (`password`, `token`, `api_key`, etc.) |

```bash
# Enable rich diagnostics for a run
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich python myapp.py
```

Rich mode is automatically downgraded to lean in production unless explicitly allowed:

```bash
RUNTIME_NARRATIVE_ENV=production
RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION=true   # override when needed
```

Per-story configuration:

```python
from runtime_narrative import story, FailureDiagnosticsConfig

async with story(
    "Import Customers",
    runtime_environment="development",
    failure_diagnostics="rich",
    app_roots=("/path/to/my/app",),   # optional; default uses cwd
    redact_extra=("internal_id", "org_token"),  # extend built-in secret list
):
    ...

# Or pass a fully built config
cfg = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    app_roots=("/app",),
    redact_extra=("internal_id",),
)
async with story("Import Customers", diagnostics_config=cfg):
    ...
```

### Custom redaction

Rich mode captures local variables at the failing frame and automatically redacts keys containing `password`, `secret`, `token`, `api_key`, `authorization`, `cookie`, `session`, and `credential`. Pass `redact_extra` to extend this list with project-specific names:

```python
async with story("Sync Users", failure_diagnostics="rich", redact_extra=("org_id", "internal_key")):
    ...
```

The same kwarg is accepted by `RuntimeNarrativeMiddleware` and `FailureDiagnosticsConfig`.

---

## Server deployments — structured JSON logs

For production or any environment where you need machine-readable output, swap `ConsoleRenderer` for `JsonRenderer`. It emits one JSON object per lifecycle event — compatible with any structured log collector (Datadog, CloudWatch, Loki, OpenTelemetry log exporters):

```python
from runtime_narrative import story, stage, JsonRenderer

async with story("Process Payment", renderers=[JsonRenderer()]):
    async with stage("Validate Card"):
        ...
    async with stage("Charge"):
        ...
```

On success, output is minimal — one object per event:

```json
{"event": "StoryStarted", "story_id": "abc-123", "story_name": "Process Payment", "timestamp": "..."}
{"event": "StageCompleted", "story_id": "abc-123", "stage_name": "Validate Card", "duration_seconds": 0.003, "timestamp": "..."}
{"event": "StoryCompleted", "story_id": "abc-123", "success": true, "progress": {"percent": 100, ...}, "timestamp": "..."}
```

On failure, `FailureOccurred` carries the full diagnostics payload — exact location, stack frame classification, source snippet, local variables (rich mode), traceback — all in a structured, queryable form:

```json
{
  "event": "FailureOccurred",
  "story_id": "abc-123",
  "stage_name": "Charge",
  "error_type": "TimeoutError",
  "location": {"filename": "payment.py", "lineno": 82, "function": "charge_card", "source_line": "..."},
  "llm_analysis": "...",
  "diagnostics_mode": "lean",
  "stack_frames": [...],
  "compressed_stack_summary": "2 app frame(s), 4 other/hidden in full stack (6 total)",
  "stage_timeline": "Validate Card=completed (0.003s) | Charge=failed (0.012s)"
}
```

Write to a file instead of stdout:

```python
JsonRenderer(output=open("narrative.log", "a"))
```

### Rotating log files

Use `RotatingJsonRenderer` to cap log file size automatically. When the active file reaches `max_bytes` it is renamed to `narrative.log.1` (shifting older backups) and a new file is opened — no external dependencies, no cron job required:

```python
from runtime_narrative import story, stage, RotatingJsonRenderer

async with story("Process Payment", renderers=[RotatingJsonRenderer("narrative.log")]):
    async with stage("Charge"):
        ...
```

```python
RotatingJsonRenderer(
    "narrative.log",
    max_bytes=10 * 1024 * 1024,  # rotate at 10 MB (default)
    backup_count=5,               # keep narrative.log.1 … narrative.log.5 (default)
    indent=None,                  # compact single-line output (default)
)
```

---

## FastAPI / Starlette middleware

Add the middleware once and every request becomes a story automatically. Route handlers only need to declare stages:

```python
from fastapi import FastAPI
from runtime_narrative import RuntimeNarrativeMiddleware, JsonRenderer, OllamaFailureAnalyzer

app = FastAPI()
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[JsonRenderer()],                          # structured logs for prod
    failure_analyzer=OllamaFailureAnalyzer(model="llama3"),
    runtime_environment="production",                    # enforces lean + traceback cap
)

@app.post("/orders")
async def create_order(payload: OrderIn):
    with stage("Validate Input"):
        validate(payload)

    with stage("Persist Order"):
        order = await db.insert(payload)

    return {"id": order.id}
```

Each request becomes a story named `"POST /orders"`. If the handler raises, the middleware captures the full failure context before returning the error response.

When no `renderers` are provided, the middleware auto-selects: `ConsoleRenderer` when `sys.stdout` is a real TTY (local `uvicorn` dev server), `JsonRenderer` otherwise (Docker, CI, any non-interactive environment).

When `opentelemetry-api` is installed, the middleware automatically extracts incoming W3C `traceparent` / `tracestate` headers and attaches the upstream trace context before entering the story. This means `OtelRenderer` story spans become children of the upstream trace — not orphaned roots — so distributed traces are connected end-to-end. Pass `propagate_trace_context=False` to disable this behavior.

### Progress tracking

Declare the expected stage count upfront so `progress_percent` is accurate at every stage boundary — not just at story end:

```python
from runtime_narrative import story, stage, StoryRuntime

with story("Import Customers", total_stages=3) as runtime:
    with stage("Load CSV"):
        rows = load_csv("customers.csv")
    # progress_percent is now 33%

    with stage("Validate Data"):
        validate(rows)
    # progress_percent is now 66%

    with stage("Insert Records"):
        db.insert(rows)
    # progress_percent is now 100%
```

You can also set the count dynamically after the story starts:

```python
with story("Process Batch") as runtime:
    items = fetch_items()
    runtime.set_total_stages(len(items))
    for item in items:
        with stage(f"Process {item.id}"):
            process(item)
```

---

## Auto-instrumentation

Instrument an entire class or module without touching every function individually.

### `@narrative_class`

Decorate a class and every public instance method becomes a stage automatically. The stage name is `ClassName.method_name`.

```python
from runtime_narrative import narrative_class, no_stage

@narrative_class
class OrderService:
    def validate(self, order): ...      # → stage "OrderService.validate"
    def charge(self, order): ...        # → stage "OrderService.charge"
    def fulfill(self, order): ...       # → stage "OrderService.fulfill"

    @no_stage
    def _log(self, msg): ...            # excluded — opt-out marker
```

Equivalent to manually wrapping each method in `with stage("OrderService.validate")`. The decorator handles both sync and async methods; use `async with story(...)` to fully await async renderers.

**What is skipped:** names starting with `_`, `@no_stage`-marked methods, `@property`, and inherited methods (apply `@narrative_class` to the base class separately). `@classmethod` and `@staticmethod` are skipped by default — see below.

### `@narrative_stage`

Override the auto-generated stage name for a specific method, or use it standalone on any function:

```python
from runtime_narrative import narrative_class, narrative_stage

@narrative_class
class OrderService:
    @narrative_stage("Validate Order")   # custom name overrides "OrderService.validate"
    def validate(self, order): ...

    def charge(self, order): ...         # → "OrderService.charge" (default)
```

Standalone — any function, any depth, sync or async:

```python
@narrative_stage("Process Order")
async def process(order):
    ...
```

When `name` is omitted (`@narrative_stage()`), the function name is title-cased: `validate_order` → `"Validate Order"`.

### Classmethods and staticmethods

`@narrative_class` skips classmethods and staticmethods by default. Enable them explicitly:

```python
@narrative_class(instrument_classmethods=True, instrument_staticmethods=True)
class Factory:
    @classmethod
    def create(cls): ...          # → "Factory.create"

    @staticmethod
    def validate(data): ...       # → "Factory.validate"

    @classmethod
    @no_stage
    def _internal(cls): ...       # excluded by @no_stage

    @classmethod
    @narrative_stage("Build Widget")
    def build(cls): ...           # → "Build Widget" (custom name)
```

### `@no_stage`

Opt-out marker. Apply to any method or function to exclude it from auto-instrumentation:

```python
@no_stage
def _internal_helper(self): ...
```

### `instrument_module()`

Instrument all public callables in an existing module in one call. Classes get the full `@narrative_class` treatment; top-level functions are wrapped directly. Symbols imported from other modules are not touched.

```python
import runtime_narrative
import myapp.services

runtime_narrative.instrument_module(myapp.services)
```

Call this once at startup, after the module has been imported.

### `auto_instrument()`

Zero-config option. Register a `sys.meta_path` import hook that instruments every app module as it is imported — no changes to application code required:

```python
# Entry point (main.py or app factory) — one line:
import runtime_narrative
runtime_narrative.auto_instrument()

# Everything imported from this point on is instrumented automatically:
from myapp.services import OrderService
from myapp.pipeline import run_pipeline
```

Only modules whose source file is under the current working directory (or `app_roots`) are instrumented — stdlib and installed packages are unaffected.

```python
# Pin to specific directories instead of cwd:
runtime_narrative.auto_instrument(app_roots=["/app/src", "/app/workers"])
```

The hook is removable:

```python
finder = runtime_narrative.auto_instrument()
# ... later ...
import sys
sys.meta_path.remove(finder)
```

---

## Decorators

Wrap entire functions without changing their call sites. The library detects `async def` automatically:

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_story(failure_analyzer=analyzer)
async def run_pipeline():
    await load_data()
    await transform()
    await export()

@runtime_narrative_stage("Load Source Data")
async def load_data():
    ...
```

All `story()` kwargs — `failure_analyzer`, `failure_diagnostics`, `runtime_environment`, `background_analysis`, `renderers`, etc. — are forwarded from `@runtime_narrative_story`.

---

## OpenTelemetry integration

`OtelRenderer` maps narrative events to OpenTelemetry spans. Requires the `[otel]` extra.

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from runtime_narrative import story, stage, OtelRenderer

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

async with story("Process Order", renderers=[OtelRenderer(tracer_provider=provider)]):
    async with stage("Validate"):
        ...
    async with stage("Charge"):
        ...
```

| Narrative event | OTel concept |
|---|---|
| `StoryStarted` → `StoryCompleted` (success) | Root span, status `OK` |
| `StoryStarted` → `StoryCompleted` (failure) | Root span, status `ERROR` + error attributes |
| `StageStarted` → `StageCompleted` | Child span of the story root |
| `FailureOccurred` | Sets `ERROR` status + attributes on root span; ends failing stage span as `ERROR` |
| `LLMAnalysisReady` | Span event on root with `narrative.llm_analysis` attribute |

Attributes on failure spans include `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `error.stack_trace`, `narrative.stage_name`, `narrative.exception_chain`.

If no `tracer_provider` is passed, the globally configured provider is used (`trace.get_tracer_provider()`).

### Filtering

Skip low-value spans to reduce trace noise:

```python
OtelRenderer(
    tracer_provider=provider,
    exclude_stages={"health_check", "cache_lookup"},  # never create spans for these
    min_duration_ms=5.0,   # suppress stage spans shorter than 5 ms
    max_attribute_length=4096,  # truncate long string attributes (default 8192)
)
```

`exclude_stages` stages that fail still mark the root span `ERROR` — only the child span is suppressed. `min_duration_ms` stages that fail are not filtered (failures always produce a span).

### OTel log renderer

`OtelLogRenderer` emits all 6 lifecycle events as OpenTelemetry log records via the `opentelemetry._logs` API. Combine it with `OtelRenderer` to get both traces and logs in your observability backend:

```python
from runtime_narrative import story, stage, OtelRenderer, OtelLogRenderer
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

log_provider = LoggerProvider()
log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))

async with story("Process Order", renderers=[
    OtelRenderer(tracer_provider=trace_provider),
    OtelLogRenderer(logger_provider=log_provider),
]):
    async with stage("Validate"):
        ...
```

| Event | OTel severity |
|---|---|
| `StoryStarted`, `StoryCompleted`, `LLMAnalysisReady` | `INFO` |
| `StageStarted`, `StageCompleted` | `DEBUG` |
| `FailureOccurred` | `ERROR` with `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `error.stack_trace`, `narrative.exception_chain` attributes |

Log records are automatically correlated with the ambient OTel span context (`trace_id` / `span_id`) so logs link to their enclosing traces in your backend.

### OTel metrics renderer

`OtelMetricsRenderer` emits four instruments via the OpenTelemetry Metrics API:

```python
from runtime_narrative import story, stage, OtelMetricsRenderer
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=60_000)
meter_provider = MeterProvider(metric_readers=[reader])

async with story("Nightly Batch", renderers=[OtelMetricsRenderer(meter_provider=meter_provider)]):
    async with stage("Load"):
        ...
```

| Instrument | Type | Labels |
|---|---|---|
| `narrative.stage.duration` | Histogram (unit `s`) | `story_name`, `stage_name` |
| `narrative.story.duration` | Histogram (unit `s`) | `story_name`, `success` (`"true"` / `"false"`) |
| `narrative.story.failures` | Counter | `story_name`, `error_type` |
| `narrative.llm.analysis_latency` | Histogram (unit `s`) | `story_name` |

`narrative.llm.analysis_latency` measures the time between `FailureOccurred` and `LLMAnalysisReady` — only recorded when background LLM analysis is enabled.

---

## Prometheus metrics

`PrometheusRenderer` records four metrics via `prometheus-client`. Requires the `[prometheus]` extra.

```python
from runtime_narrative import story, stage, PrometheusRenderer

async with story("Nightly Batch", renderers=[PrometheusRenderer()]):
    async with stage("Load"):
        ...
    async with stage("Transform"):
        ...
```

| Metric | Type | Labels |
|---|---|---|
| `narrative_story_duration_seconds` | Histogram | `story_name`, `success` (`"true"` / `"false"`) |
| `narrative_stage_duration_seconds` | Histogram | `story_name`, `stage_name` |
| `narrative_story_failures_total` | Counter | `story_name`, `error_type` |
| `narrative_story_total` | Counter | `story_name`, `success` |

Use a custom registry to isolate metrics across services or in tests:

```python
from prometheus_client import CollectorRegistry, start_http_server

registry = CollectorRegistry()
renderer = PrometheusRenderer(registry=registry)
start_http_server(8000, registry=registry)
```

---

## Django middleware

`RuntimeNarrativeDjangoMiddleware` wraps every ASGI Django request in a story. `RuntimeNarrativeDjangoSyncMiddleware` does the same for WSGI (sync). Requires the `[django]` extra.

```python
# settings.py
MIDDLEWARE = [
    "runtime_narrative.middleware_django.RuntimeNarrativeDjangoMiddleware",
    # ... other middleware
]
```

Or with explicit options in an ASGI entry point:

```python
from runtime_narrative import RuntimeNarrativeDjangoMiddleware, JsonRenderer, OllamaFailureAnalyzer

application = RuntimeNarrativeDjangoMiddleware(
    get_response=django_asgi_app,
    renderers=[JsonRenderer()],
    failure_analyzer=OllamaFailureAnalyzer(model="llama3"),
    runtime_environment="production",
)
```

Story name is `"METHOD /path"` (e.g. `"POST /api/orders"`).

---

## Celery integration

`NarrativeTask` is a Celery `Task` base class that wraps each task execution in a story. Requires the `[celery]` extra.

```python
from celery import Celery
from runtime_narrative import NarrativeTask, OllamaFailureAnalyzer

app = Celery("myapp")

@app.task(base=NarrativeTask)
def process_order(order_id):
    with stage("Validate"):
        validate(order_id)
    with stage("Charge"):
        charge(order_id)
```

To set defaults for all tasks in an app:

```python
from runtime_narrative import connect_narrative, JsonRenderer

connect_narrative(
    app,
    renderers=[JsonRenderer()],
    failure_analyzer=OllamaFailureAnalyzer(model="llama3"),
    runtime_environment="production",
)
```

Story name is `"<task.name> [task_id=<id>]"` (e.g. `"myapp.tasks.process_order [task_id=abc-123]"`). Override any option per-task by setting the `narrative_*` class attribute directly.

---

## Concurrent tasks — `NarrativeTaskGroup`

Run multiple async tasks under a single story and track all their stages together. No extra dependencies required.

```python
from runtime_narrative import story, NarrativeTaskGroup

async with story("Parallel Pipeline", renderers=[...]):
    async with NarrativeTaskGroup() as tg:
        tg.create_task(load_data(), name="Load Data")
        tg.create_task(load_config(), name="Load Config")
    # both completed — stages from both appear in the story timeline
```

Each task inherits the parent story's `ContextVar` context automatically, so `stage()` calls inside tasks are tracked normally. If tasks fail, `NarrativeTaskGroupError` is raised with a `failed_tasks: dict[str, BaseException]` mapping:

```python
from runtime_narrative import NarrativeTaskGroupError

try:
    async with NarrativeTaskGroup() as tg:
        tg.create_task(risky_job(), name="Risky Job")
except NarrativeTaskGroupError as e:
    for task_name, exc in e.failed_tasks.items():
        print(f"{task_name} failed: {exc}")
```

---

## gRPC interceptors

`RuntimeNarrativeInterceptor` (sync) and `RuntimeNarrativeAsyncInterceptor` (async) wrap each RPC in a story. Requires the `[grpc]` extra.

```python
import grpc
from runtime_narrative import RuntimeNarrativeAsyncInterceptor, JsonRenderer

interceptor = RuntimeNarrativeAsyncInterceptor(renderers=[JsonRenderer()])

server = grpc.aio.server(interceptors=[interceptor])
```

Story name is the full gRPC method path, e.g. `"/mypackage.MyService/DoThing"`.

For sync (non-async) gRPC servers:

```python
import grpc
from runtime_narrative import RuntimeNarrativeInterceptor

interceptor = RuntimeNarrativeInterceptor(renderers=[JsonRenderer()])
server = grpc.server(
    futures.ThreadPoolExecutor(),
    interceptors=[interceptor],
)
```

Both interceptors accept the same `renderers`, `failure_analyzer`, and diagnostic kwargs as all other integration points.

---

## Testing utilities

`StoryRecorder` is a drop-in context manager that starts a story with a built-in capturing renderer and exposes assertion methods:

```python
from runtime_narrative import stage
from runtime_narrative.testing import StoryRecorder

def test_etl_stages():
    with StoryRecorder("ETL") as r:
        with stage("Load"):
            pass
        with stage("Validate"):
            pass
        with stage("Export"):
            pass

    r.assert_stages_completed(["Load", "Validate", "Export"])
    r.assert_no_failure()

def test_invalid_input_fails_at_validate():
    with pytest.raises(ValueError):
        with StoryRecorder("ETL") as r:
            with stage("Load"):
                pass
            with stage("Validate"):
                raise ValueError("bad schema")

    r.assert_stage_failed("Validate", error_type="ValueError")
    r.assert_story_completed(success=False)
```

Works as `async with StoryRecorder(...)` too — pass any `**story_kwargs` (including `dry_run=True`).

---

## `dry_run` mode

Pass `dry_run=True` to `story()` to suppress all stage-body exceptions and still emit `StageStarted` / `StageCompleted` for every stage. The story always completes as `success=True`. Useful for verifying instrumentation wiring before running expensive operations:

```python
with story("Nightly ETL", dry_run=True):
    with stage("Load Warehouse"):
        raise IOError("would connect to DB in production")
    with stage("Transform"):
        raise RuntimeError("would run transforms in production")
    with stage("Export"):
        raise IOError("would upload in production")
# → StageCompleted emitted for all 3 stages, StoryCompleted(success=True)
```

Combine with `StoryRecorder` to assert your stage wiring without side effects:

```python
with StoryRecorder("Nightly ETL", dry_run=True) as r:
    run_pipeline()

r.assert_stages_completed(["Load Warehouse", "Transform", "Export"])
r.assert_no_failure()
```

---

## HTML report

`HtmlReportRenderer` writes a self-contained HTML file when the story completes:

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.html_renderer import HtmlReportRenderer

with story("Batch Job", renderers=[HtmlReportRenderer("report.html", open_browser=True)]):
    with stage("Load"):
        pass
    with stage("Process"):
        pass
# → report.html written; browser opens automatically if open_browser=True
```

The report includes: story name, duration, success/failure badge, a per-stage duration bar chart, and a failure detail section with traceback and LLM analysis (if any).

---

## Custom renderer

Any object with a `handle(event)` method is a valid renderer. Async renderers (`async def handle`) are awaited automatically inside `async with story(...)`, including for `StageStarted` and `StageCompleted` events:

```python
class SlackRenderer:
    async def handle(self, event):
        if event.__class__.__name__ == "FailureOccurred":
            await slack.post(
                f"*{event.story_name}* failed at *{event.stage_name}*\n"
                f"`{event.error_type}: {event.error_message}`"
            )

async with story("Nightly ETL", renderers=[SlackRenderer()]):
    ...
```

Events you will receive:

| Event | Key fields |
|---|---|
| `StoryStarted` | `story_id`, `story_name`, `timestamp` |
| `StageStarted` | `story_id`, `stage_name`, `timestamp`, `stage_index` (0-based), `parent_stage_name` (for nested stages) |
| `StageCompleted` | `story_id`, `stage_name`, `timestamp`, `duration_seconds`, `stage_index`, `parent_stage_name` |
| `FailureOccurred` | `story_id`, `story_name`, `stage_name`, `error_type`, `error_message`, `filename`, `lineno`, `function`, `traceback_text`, `exception_chain`, `stage_timeline`, `llm_analysis`, … |
| `StoryCompleted` | `story_id`, `story_name`, `success`, `progress_percent`, `completed_stages`, `total_stages`, `timestamp` |
| `LLMAnalysisReady` | `story_id`, `story_name`, `stage_name`, `llm_analysis`, `timestamp` — only emitted when `background_analysis=True` |

`stage_index` is the 0-based position of the stage in the story's stage list. `parent_stage_name` is `None` for top-level stages and set to the enclosing stage's name for nested stages.

---

## Custom failure analyzer

Any object with an `analyze_failure(...)` method works. Add `analyze_failure_async(...)` for native async — otherwise the sync version is called via `asyncio.to_thread` so it never blocks the event loop:

```python
class MyAnalyzer:
    async def analyze_failure_async(
        self, *, story_name, stage_name, failure, stage_timeline, progress_percent
    ):
        # failure is a FailureSummary:
        #   .error_type, .error_message, .filename, .lineno,
        #   .function, .source_line, .traceback_text, .exception_chain
        result = await my_llm_client.complete(build_prompt(failure))
        return result.text

async with story("Import", failure_analyzer=MyAnalyzer()):
    ...
```

Type-check your custom analyzer against the `FailureAnalyzer` protocol (all built-in analyzers already satisfy it):

```python
from runtime_narrative import FailureAnalyzer
assert isinstance(MyAnalyzer(), FailureAnalyzer)
```

---

## Environment variables

| Variable | Values | Default | Effect |
|---|---|---|---|
| `RUNTIME_NARRATIVE_ENV` | `development`, `production` | `development` | Production caps traceback length and forces lean mode |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean`, `rich` | `lean` | `rich` captures local variables at the failing frames. Invalid values raise `ValueError` at story construction. |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | `1`, `true` | off | Bypass production safeguard for rich diagnostics |
| `RUNTIME_NARRATIVE_MODEL` | model name string | — | Default model for `AnthropicFailureAnalyzer`, `LLMFailureAnalyzer`, and `OllamaFailureAnalyzer` when `model=` is not passed explicitly |
| `ANTHROPIC_API_KEY` | API key string | — | Required by `AnthropicFailureAnalyzer`; read automatically if not passed as `api_key=` |

---

## Philosophy

- **Zero noise on success.** One line per stage. No log spam when things work.
- **Full context on failure.** The library already knows what succeeded, what failed, and where. It uses that to give you an actionable report, not a raw stacktrace dropped into a log file.
- **LLM is optional, never required.** Every feature works without an LLM. The analyzer is purely additive. If it fails to respond, your exception still propagates normally.
- **Logical fixes, not code rewrites.** The LLM suggestion names the exact mechanism and location of the failure, and tells you what logic to change. It does not generate code diffs.
- **Async-first, sync-compatible.** Both `with story()` and `async with story()` work. The library never blocks the event loop — failure diagnostics and LLM calls both run via `asyncio.to_thread`.
- **No framework lock-in.** Use it in a script, a FastAPI app, a Celery worker, a CLI, or a data pipeline. The only required hook is wrapping your code in `story()` / `stage()`.

---

## License

MIT
