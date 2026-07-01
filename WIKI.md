# runtime-narrative — Complete Guide

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Core Concepts](#3-core-concepts)
4. [Quick Start](#4-quick-start)
5. [story() — The Story Context Manager](#5-story--the-story-context-manager)
6. [stage() — Stage Context Managers](#6-stage--stage-context-managers)
7. [Decorators](#7-decorators)
8. [Auto-Instrumentation](#8-auto-instrumentation)
9. [Failure Diagnostics](#9-failure-diagnostics)
10. [Renderers](#10-renderers)
11. [Framework Integrations](#11-framework-integrations)
12. [Async Task Groups](#12-async-task-groups)
13. [SQLite Persistence and CLI](#13-sqlite-persistence-and-cli)
14. [Testing with StoryRecorder](#14-testing-with-storyrecorder)
15. [dry_run Mode](#15-dry_run-mode)
16. [Background Analysis](#16-background-analysis)
17. [Custom Renderers](#17-custom-renderers)
18. [Custom Failure Analyzers](#18-custom-failure-analyzers)
19. [Environment Variables](#19-environment-variables)
20. [Event Reference](#20-event-reference)
21. [Sub-stories and Log Capture](#21-sub-stories-and-log-capture)

---

## 1. Overview

`runtime-narrative` models program execution as **stories** — named units of work that unfold across a sequence of named **stages**. As each story and stage starts or finishes, the library emits structured lifecycle events. One or more **renderers** consume those events and do something useful with them: print colored output to the terminal, write JSON logs, export OpenTelemetry spans, fire Prometheus metrics, or send webhooks.

The mental model is deliberately close to how engineers describe work in conversation: "we ran the Import Customers job, it loaded the CSV, validated the rows, then failed during Insert Records." That narrative is exactly what the library captures automatically, including timing per stage, a compressed stack summary, and an optional source snippet at the failure site.

The library has two usage layers that compose cleanly. The **explicit** layer gives you `story()` and `stage()` context managers — you control exactly what gets a name. The **auto-instrumentation** layer (`@narrative_class`, `instrument_module`, `auto_instrument`) can instrument entire modules or classes with a single line, turning every public method into a stage with zero per-method boilerplate. Both layers produce the same event stream and are compatible with the same renderers.

The core of the library — story, stage, events, context propagation, and the diagnostics engine — has no required dependencies beyond Python's standard library and `python-dotenv`. Optional extras add colored console output (`typer`), web framework middleware (`starlette`, `django`), observability backends (`opentelemetry-*`, `prometheus-client`), LLM-based failure analysis (`anthropic`), and framework integrations (`celery`, `grpcio`). The async design is pervasive: every context manager supports both `with` and `async with`, every analyzer exposes both `analyze_failure` and `analyze_failure_async`, and async renderers are properly awaited when the story runs asynchronously.

---

## 2. Installation

Install the core package:

```bash
pip install runtime-narrative
```

Install with a specific extra:

```bash
pip install "runtime-narrative[console]"    # colored terminal output
pip install "runtime-narrative[fastapi]"    # FastAPI / Starlette middleware
pip install "runtime-narrative[anthropic]"  # Anthropic Claude failure analysis
pip install "runtime-narrative[all]"        # everything
```

Install multiple extras together:

```bash
pip install "runtime-narrative[console,fastapi,otel]"
```

### Extras reference

| Extra | Installs | Use for |
|-------|----------|---------|
| `console` | `typer>=0.9.0` | Colored, bold terminal output via `ConsoleRenderer` |
| `fastapi` | `starlette>=0.27.0` | `RuntimeNarrativeMiddleware` for FastAPI / Starlette |
| `otel` | `opentelemetry-api`, `opentelemetry-sdk` | `OtelRenderer`, `OtelLogRenderer`, `OtelMetricsRenderer` |
| `prometheus` | `prometheus-client>=0.19.0` | `PrometheusRenderer` for Prometheus metrics |
| `anthropic` | `anthropic>=0.25.0` | `AnthropicFailureAnalyzer` via Claude API |
| `django` | `django>=3.2` | `RuntimeNarrativeDjangoMiddleware` (ASGI + WSGI) |
| `celery` | `celery>=5.0` | `NarrativeTask` base class and `connect_narrative` |
| `grpc` | `grpcio>=1.50.0` | `RuntimeNarrativeInterceptor` and async variant |
| `all` | everything above | Kitchen-sink install for development |

### With uv

```bash
uv add runtime-narrative
uv add "runtime-narrative[console,fastapi]"
uv sync --group dev   # includes test and build tools
```

---

## 3. Core Concepts

### The pipeline: Story → Stages → Events → Renderers

```
┌───────────────────────────────────────────────────────────┐
│  story("Import Customers")                                │
│    ├── stage("Load CSV")    ──► StageStarted             │
│    │                        ──► StageCompleted           │
│    ├── stage("Validate")    ──► StageStarted             │
│    │                        ──► StageCompleted           │
│    └── stage("Insert")      ──► StageStarted             │
│                             ──► FailureOccurred          │
│                             ──► StoryCompleted           │
│                                      │                   │
│                               renderers.handle(event)    │
│                               [ConsoleRenderer,          │
│                                JsonRenderer, ...]        │
└───────────────────────────────────────────────────────────┘
```

A **story** is a named execution scope. It owns a `StoryRuntime` that tracks all stages registered within it, maintains a progress counter, and dispatches events to attached renderers. A story emits `StoryStarted` on entry and `StoryCompleted` on exit (regardless of success or failure). When an exception escapes a story without being caught inside it, the story emits `FailureOccurred` with rich diagnostics before emitting `StoryCompleted`.

**Stages** are the named steps inside a story. Each stage emits `StageStarted` on entry and, if it completes without error, `StageCompleted` with its duration. If a stage raises an exception, it marks the stage as failed and lets the exception propagate to the story boundary, where it is caught and turned into `FailureOccurred`. Stages can nest: opening a `stage()` inside another `stage()` records `parent_stage_name` on the inner record.

**Events** are plain dataclasses with no behavior. The six events are: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`, and `LLMAnalysisReady`. All six are part of the stable public API and importable directly from `runtime_narrative` — see [Section 20](#20-event-reference). Any renderer that understands these types can do arbitrary things with them.

**Renderers** receive every event via their `handle` method. There is no base class and no registration system — any object with `handle(self, event: object) -> None` qualifies. Async renderers declare `async def handle(self, event: object)` and are awaited only when the story itself is running asynchronously (via `async with story(...)`).

### Context propagation via ContextVar

The library uses two `ContextVar` values defined in `runtime_narrative/context.py`:

- `current_story` — holds the active `StoryRuntime` (or `None`)
- `current_stage_stack` — holds a list of currently open `StageRecord` objects for nesting

Because `ContextVar` propagates into async tasks via `contextvars.copy_context()`, you never thread the story runtime through function arguments. Any function called inside a `with story(...)` or `async with story(...)` block can open a stage by calling `stage("name")` — the active story is found automatically. This works correctly in asyncio tasks, threads spawned by `asyncio.to_thread`, and chained coroutines.

### The renderer protocol

```python
class MyRenderer:
    def handle(self, event: object) -> None:
        if type(event).__name__ == "FailureOccurred":
            print(f"FAILURE: {event.error_type}: {event.error_message}")
```

Async variant:

```python
class MyAsyncRenderer:
    async def handle(self, event: object) -> None:
        await some_io_operation(event)
```

Async renderers are only awaited when `emit_async` is called — which happens during `async with story(...)` entry/exit. Stage events inside a synchronous `with story(...)` block use `emit()` (sync), so async renderer `handle` coroutines are not awaited for those events. If you need async handling of stage events, use `async with story(...)`.

### The analyzer protocol

```python
class MyAnalyzer:
    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure,          # FailureSummary — see section 18
        stage_timeline: str,
        progress_percent: int,
    ) -> str | None:
        ...

    # Optional async variant — if absent, analyze_failure is called via asyncio.to_thread
    async def analyze_failure_async(self, *, ...) -> str | None:
        ...
```

The analyzer receives a `FailureSummary` (error type, message, filename, lineno, traceback text, exception chain) plus context about where in the story the failure occurred. Returning `None` is equivalent to "no analysis available."

---

## 4. Quick Start

### Context manager API — success path

```python
from runtime_narrative import story, stage

with story("Import Customers", total_stages=3):
    with stage("Load CSV"):
        rows = ["alice", "bob", "carol"]

    with stage("Validate Data"):
        if not rows:
            raise ValueError("No rows found")

    with stage("Insert Records"):
        print(f"Inserted {len(rows)} records")
```

The `total_stages=3` hint lets renderers show accurate progress percentages. Without it, the runtime infers total stages from how many stages have been registered so far, which means percentages are always 100% at completion rather than showing intermediate progress.

### Decorator API — failure path

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_stage("Load CSV")
def load_csv() -> list[str]:
    return ["alice", "bob"]

@runtime_narrative_stage("Validate Data")
def validate(rows: list[str]) -> None:
    if not rows:
        raise ValueError("No rows found")

@runtime_narrative_stage("Insert Records")
def insert(rows: list[str]) -> None:
    raise ValueError("duplicate customer id")  # triggers FailureOccurred

@runtime_narrative_story("Import Customers")
def run() -> None:
    rows = load_csv()
    validate(rows)
    insert(rows)

try:
    run()
except Exception:
    pass
```

Both APIs produce identical event streams. Decorators are convenient when you want to instrument functions defined in different modules, or when you prefer to keep the story/stage boundary close to the function definition rather than at the call site.

### Async context manager

```python
import asyncio
from runtime_narrative import story, stage

async def main():
    async with story("Async Pipeline"):
        async with stage("Fetch Data"):
            await asyncio.sleep(0.1)

        async with stage("Process"):
            pass

asyncio.run(main())
```

---

## 5. story() — The Story Context Manager

### Constructor signature

```python
story(
    name: str,
    *,
    renderers: Sequence[object] | None = None,
    failure_analyzer = None,
    background_analysis: bool = False,
    diagnostics_config: FailureDiagnosticsConfig | None = None,
    runtime_environment: str | None = None,
    failure_diagnostics: str | None = None,
    allow_rich_in_production: bool | None = None,
    app_roots: Sequence[str] | None = None,
    redact_extra: Sequence[str] | None = None,
    total_stages: int | None = None,
    dry_run: bool = False,
)
```

`__enter__` / `__aenter__` returns a `StoryRuntime` instance.

### Parameter reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Human-readable story name. Appears in all events and renderer output. |
| `renderers` | `Sequence[object] \| None` | `[ConsoleRenderer()]` | One or more renderer objects. Pass an empty list `[]` to silence all output. |
| `failure_analyzer` | `object \| None` | `None` | Analyzer called on exception to produce LLM analysis text. |
| `background_analysis` | `bool` | `False` | Emit `FailureOccurred` immediately with `llm_analysis=None`, then emit `LLMAnalysisReady` asynchronously. Requires `async with`. |
| `diagnostics_config` | `FailureDiagnosticsConfig \| None` | `None` | Full config object. When provided, all individual diagnostic kwargs are ignored. |
| `runtime_environment` | `str \| None` | reads env | `"development"` or `"production"`. Production caps traceback length and forces lean mode. |
| `failure_diagnostics` | `str \| None` | reads env | `"lean"` (default) or `"rich"` (captures local variables on failure). |
| `allow_rich_in_production` | `bool \| None` | `None` | When `True`, rich mode is permitted even in production. |
| `app_roots` | `Sequence[str] \| None` | `None` (uses cwd) | Directories considered "app code" for primary frame selection. Frames inside these paths are preferred over stdlib/site-packages. |
| `redact_extra` | `Sequence[str] \| None` | `None` | Additional key substrings to redact from local variables in rich mode. |
| `total_stages` | `int \| None` | `None` | Declared total stages. Enables accurate progress percentages. Can also be set later via `runtime.set_total_stages(n)`. |
| `dry_run` | `bool` | `False` | Stage exceptions are suppressed; all stages complete; story always succeeds. |

### Sync usage

```python
from runtime_narrative import story, stage

with story("Deploy Release", total_stages=4) as runtime:
    print(f"Story ID: {runtime.story_id}")
    with stage("Run Tests"):
        pass
    with stage("Build Image"):
        pass
    with stage("Push to Registry"):
        pass
    with stage("Update Manifests"):
        pass
```

### Async usage

```python
import asyncio
from runtime_narrative import story, stage

async def deploy():
    async with story("Deploy Release", total_stages=4) as runtime:
        async with stage("Run Tests"):
            await asyncio.sleep(0.5)
        async with stage("Build Image"):
            await asyncio.sleep(1.0)
        print(f"Progress after 2 stages: {runtime.progress_percent}%")
        async with stage("Push to Registry"):
            await asyncio.sleep(0.2)
        async with stage("Update Manifests"):
            await asyncio.sleep(0.1)

asyncio.run(deploy())
```

### StoryRuntime API

`story.__enter__` / `story.__aenter__` returns a `StoryRuntime`:

| Member | Type | Description |
|--------|------|-------------|
| `name` | `str` | Story name |
| `story_id` | `str` | UUID for this execution |
| `started_at` | `datetime` | Entry timestamp |
| `stages` | `list[StageRecord]` | All stages opened so far |
| `dry_run` | `bool` | Whether dry_run is active |
| `completed_stages` | `int` (property) | Count of `StageCompleted` events |
| `total_stages` | `int` (property) | Declared or inferred total |
| `progress_percent` | `int` (property) | `completed_stages / total_stages * 100` |
| `set_total_stages(n)` | method | Update the declared total after entry |
| `build_stage_timeline()` | method | Returns a one-line stage summary string |
| `emit(event)` | method | Sync dispatch to all renderers |
| `emit_async(event)` | method | Async dispatch, awaiting async renderers |
| `record_failure(exc, *, stage_name=None)` | async method | Emit `FailureOccurred` for *exc* without affecting exception propagation (see below) |

### record_failure() — explicit failure recording

Use `await runtime.record_failure(exc)` in saga or rollback handlers where you need to record a failure *without* relying on `__aexit__` owning the exception lifecycle:

```python
import asyncio
from runtime_narrative import story, stage

async def saga():
    async with story("Payment Saga", renderers=[...]) as runtime:
        try:
            async with stage("Charge Card"):
                raise ConnectionError("gateway timeout")
        except ConnectionError as exc:
            # Record the failure — FailureOccurred is emitted with full diagnostics
            await runtime.record_failure(exc, stage_name="Charge Card")
            # You control what happens next — compensate, re-raise, or swallow
            await rollback()
            raise

asyncio.run(saga())
```

`record_failure` runs the same diagnostics pipeline as the normal `__aexit__` path (lean/rich mode, redaction, traceback capping) and emits `FailureOccurred` via `emit_async`. It never suppresses or re-raises the exception.

Run: `uv run python examples/saga_record_failure.py`

### Tracking progress

```python
from runtime_narrative import story, stage

with story("Data Pipeline") as runtime:
    runtime.set_total_stages(5)  # can set after entry instead of in constructor

    with stage("Extract"):
        pass
    print(f"{runtime.progress_percent}%")   # 20%

    with stage("Transform"):
        pass
    print(f"{runtime.progress_percent}%")   # 40%

    with stage("Load"):
        pass
    print(f"Completed: {runtime.completed_stages} / {runtime.total_stages}")
```

### Multiple renderers

```python
from runtime_narrative import story
from runtime_narrative.renderer.console import ConsoleRenderer
from runtime_narrative.renderer.json_renderer import JsonRenderer

with open("events.jsonl", "a") as log_file:
    with story(
        "Import Customers",
        renderers=[
            ConsoleRenderer(),
            JsonRenderer(output=log_file),
        ],
    ):
        ...
```

### Silencing output

Pass an empty list to suppress all output — useful in tests or library code where the caller decides rendering:

```python
with story("Silent Operation", renderers=[]):
    ...
```

---

## 6. stage() — Stage Context Managers

`stage(name)` is a dual sync/async context manager that must be called inside an active `story()`. It registers a `StageRecord` on the story runtime, emits `StageStarted` and (on success) `StageCompleted`, and records its duration.

### Sync usage

```python
from runtime_narrative import story, stage

with story("Process Order"):
    with stage("Validate Input") as record:
        print(f"Stage index: {record.stage_index}")

    with stage("Charge Payment"):
        pass

    with stage("Send Confirmation"):
        pass
```

`__enter__` returns a `StageRecord`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Stage name |
| `started_at` | `datetime` | When the stage opened |
| `ended_at` | `datetime \| None` | When the stage closed |
| `duration_seconds` | `float \| None` | Elapsed time, set on close |
| `completed` | `bool` | `True` when the stage exited cleanly |
| `failed` | `bool` | `True` when the stage propagated an exception |
| `stage_index` | `int` | Zero-based position in the story's stage list |
| `parent_stage_name` | `str \| None` | Name of the enclosing stage, or `None` |

### Async usage

```python
import asyncio
from runtime_narrative import story, stage

async def process_order(order_id: str) -> None:
    async with story("Process Order"):
        async with stage("Fetch Order"):
            await asyncio.sleep(0.1)

        async with stage("Process Payment"):
            await asyncio.sleep(0.2)

        async with stage("Dispatch"):
            await asyncio.sleep(0.05)

asyncio.run(process_order("ORD-001"))
```

### Nesting stages

Stages may nest arbitrarily. The inner stage records `parent_stage_name` pointing to the outer stage, which allows renderers and analyzers to reconstruct a tree view of the execution.

```python
from runtime_narrative import story, stage

with story("Deploy Service"):
    with stage("Build"):
        with stage("Compile"):
            pass
        with stage("Run Unit Tests"):
            pass
        with stage("Package"):
            pass

    with stage("Release"):
        with stage("Push Artifacts"):
            pass
        with stage("Update Config"):
            pass
```

In the event stream, `StageStarted` for `"Compile"` has `parent_stage_name="Build"`. Each inner stage also appears in the flat `StoryRuntime.stages` list, and in `build_stage_timeline()`.

### Calling stage() outside a story

`stage()` raises `RuntimeError` immediately if there is no active story in the current context. Two escape hatches are available for library code or background jobs that may run with or without an enclosing story:

**`has_active_story()` probe** — check before entering a stage:

```python
from runtime_narrative import has_active_story, stage

def my_lib_function():
    if has_active_story():
        with stage("My Lib Work"):
            _do_work()
    else:
        _do_work()
```

**`stage(optional=True)`** — silently skips instrumentation when no story is active; behaves normally when inside one:

```python
from runtime_narrative import stage

def my_lib_function():
    with stage("My Lib Work", optional=True):
        _do_work()  # instrumented inside a story, plain call outside
```

Run: `uv run python examples/optional_stage.py`

---

## 7. Decorators

The decorator API wraps individual functions in story or stage context managers. Decorators detect whether the function is a coroutine and apply `async with` or `with` accordingly.

### `@runtime_narrative_stage`

Wraps a function in a `stage()`. The stage name defaults to the function name with underscores replaced by spaces and title-cased when called with no arguments.

```python
from runtime_narrative import runtime_narrative_stage

@runtime_narrative_stage("Load CSV")           # explicit name
def load_csv() -> list[str]:
    return ["alice", "bob"]

@runtime_narrative_stage()                     # inferred name: "Validate Data"
def validate_data(rows: list[str]) -> None:
    if not rows:
        raise ValueError("empty dataset")

@runtime_narrative_stage("Insert Records")
async def insert_records(rows: list[str]) -> int:
    return len(rows)
```

### `@runtime_narrative_story`

Wraps a function in a `story()`. Accepts all the same keyword arguments as `story()`. The story name defaults to the function name title-cased when called with no arguments.

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_story(
    "Import Customers",
    failure_diagnostics="rich",
)
def import_customers() -> None:
    rows = load_csv()
    validate_data(rows)
    insert_records_sync(rows)
```

### Function composition pattern

Decorate stages independently, then call them from inside a decorated story. The stage functions can live in different modules — the story context is found via `ContextVar` so no explicit passing is needed.

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_stage("Load CSV")
def load_csv() -> list[str]:
    return ["alice", "bob"]

@runtime_narrative_stage("Validate Data")
def validate(rows: list[str]) -> None:
    assert rows, "empty dataset"

@runtime_narrative_stage("Insert Records")
def insert(rows: list[str]) -> int:
    return len(rows)

@runtime_narrative_story("Import Customers")
def run() -> None:
    rows = load_csv()
    validate(rows)
    count = insert(rows)
    print(f"Inserted {count} records")

try:
    run()
except Exception:
    pass
```

### Async decorator composition

```python
import asyncio
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@runtime_narrative_stage("Fetch Users")
async def fetch_users() -> list[dict]:
    await asyncio.sleep(0.1)
    return [{"id": 1, "name": "Alice"}]

@runtime_narrative_stage("Sync to CRM")
async def sync_to_crm(users: list[dict]) -> None:
    await asyncio.sleep(0.2)

@runtime_narrative_story("CRM Sync")
async def run_sync() -> None:
    users = await fetch_users()
    await sync_to_crm(users)

asyncio.run(run_sync())
```

---

## 8. Auto-Instrumentation

Auto-instrumentation removes per-function boilerplate by wrapping public callables as stages at the class, module, or import level.

### 8.1 `@narrative_class`

Wraps every public instance method of a class as a stage. The stage name is `"ClassName.method_name"`.

```python
from runtime_narrative import narrative_class, story

@narrative_class
class OrderService:
    def validate(self, order: dict) -> None:        # → stage "OrderService.validate"
        if "amount" not in order:
            raise ValueError("missing amount")

    def charge(self, order: dict) -> str:           # → stage "OrderService.charge"
        return f"charged ${order['amount']:.2f}"

    def fulfill(self, order: dict) -> str:          # → stage "OrderService.fulfill"
        return f"fulfilled order {order.get('id')}"

svc = OrderService()

with story("Process Order", total_stages=3):
    svc.validate({"id": "ORD-1", "amount": 49.99})
    receipt = svc.charge({"id": "ORD-1", "amount": 49.99})
    svc.fulfill({"id": "ORD-1", "amount": 49.99})
```

**What `@narrative_class` skips by default:**

- Methods whose names start with `_` (private/dunder)
- Methods decorated with `@no_stage`
- `@classmethod` descriptors
- `@staticmethod` descriptors
- `@property` descriptors
- Methods inherited from parent classes (only `vars(cls)` is inspected)

**Opt in to classmethods and staticmethods:**

```python
@narrative_class(instrument_classmethods=True, instrument_staticmethods=True)
class Factory:
    @classmethod
    def create(cls, **kw):            # → stage "Factory.create"
        return cls(**kw)

    @staticmethod
    def validate_schema(data: dict):  # → stage "Factory.validate_schema"
        assert "type" in data
```

### 8.2 `@narrative_stage`

A per-function or per-method decorator for explicit stage naming. When `name` is omitted, the function name is title-cased. This decorator also works inside `@narrative_class` to override the default `ClassName.method_name` stage name — `@narrative_class` detects the `_narrative_stage_name` sentinel and skips re-wrapping to prevent double-instrumentation.

```python
from runtime_narrative import narrative_stage, narrative_class, story

@narrative_stage("Validate Payment")   # explicit custom name
def check_payment(card: str) -> bool:
    return card.startswith("4")

@narrative_class
class PaymentService:
    @narrative_stage("Charge Customer")   # overrides default "PaymentService.charge"
    def charge(self, amount: float) -> str:
        return f"charged ${amount:.2f}"

    def refund(self, amount: float) -> str:  # default: "PaymentService.refund"
        return f"refunded ${amount:.2f}"

with story("Checkout"):
    check_payment("4111111111111111")
    svc = PaymentService()
    svc.charge(49.99)
```

### 8.3 `@no_stage`

An opt-out marker that excludes a method or function from all auto-instrumentation — `@narrative_class`, `instrument_module`, and `auto_instrument` all respect it.

```python
from runtime_narrative import narrative_class, no_stage

@narrative_class
class ReportService:
    def generate(self, data: list) -> str:    # → stage "ReportService.generate"
        return self._format(data)

    @no_stage
    def _format(self, data: list) -> str:     # private; @no_stage for explicit clarity
        return "\n".join(str(d) for d in data)

    @no_stage
    def debug_dump(self) -> None:             # public but not a meaningful stage
        print(repr(self))
```

`@no_stage` sets `fn._narrative_skip = True`. It does not change the function's behavior.

### 8.4 `instrument_module`

Instruments all public callables defined in an already-imported module in-place:

- Classes whose `__module__` matches the module name get `@narrative_class` applied
- Top-level functions whose `__module__` matches are wrapped directly
- Symbols imported from other modules are not touched

```python
import runtime_narrative
from runtime_narrative import story
import myapp.services as services

runtime_narrative.instrument_module(services)  # call once after import

svc = services.CustomerService()

with story("Sync Customers", total_stages=3):
    rows = svc.load("crm.csv")
    svc.validate(rows)
    count = svc.save(rows)
```

This is the right tool when retrofitting existing code you do not own or do not want to modify.

### 8.5 `auto_instrument`

Registers a `sys.meta_path` import hook that instruments every app module on import. Only modules whose source file starts with one of the `app_roots` paths are instrumented — stdlib and installed packages are unaffected.

```python
import sys
import runtime_narrative
from runtime_narrative import story
from pathlib import Path

# Register the hook BEFORE importing any app modules
finder = runtime_narrative.auto_instrument(
    app_roots=[str(Path(__file__).resolve().parent)]
)

# These modules are instrumented on the way in
import myapp.orders
import myapp.payments

with story("Process Order"):
    svc = myapp.orders.OrderService()
    svc.validate({"amount": 49.99})
    svc.charge({"amount": 49.99})

# Remove the hook when you no longer need it
sys.meta_path.remove(finder)
```

`auto_instrument` defaults `app_roots` to the current working directory when called with no arguments:

```python
runtime_narrative.auto_instrument()  # instruments all modules under os.getcwd()
```

---

## 9. Failure Diagnostics

When an exception escapes a story, `runtime-narrative` builds an `EnrichedFailure` and emits it as a `FailureOccurred` event. How much information the failure contains is controlled by `FailureDiagnosticsConfig`.

### 9.1 Lean mode (default)

Lean mode adds no overhead beyond reading the traceback. It collects:

- **Primary frame**: the innermost app-code frame in the traceback (falling back to innermost non-stdlib, then the leaf frame). The frame's filename, line number, function name, and source line are included.
- **Source snippet**: a few lines of source context around the primary frame (`snippet_context_lines=2` on each side by default).
- **Compressed stack summary**: a one-line count like `"2 app frame(s), 5 other/hidden in full stack (7 total)"`.
- **Exception chain**: a human-readable description of any chained `__cause__` or `__context__` exceptions.

```python
from runtime_narrative import story, stage, FailureDiagnosticsConfig

lean_config = FailureDiagnosticsConfig(failure_diagnostics="lean")

try:
    with story("Checkout", diagnostics_config=lean_config):
        with stage("Charge Card"):
            raise ValueError("card declined: insufficient funds")
except ValueError:
    pass
```

### 9.2 Rich mode

Rich mode additionally captures local variable values from the primary frame and up to one enclosing frame. This is invaluable for debugging because it shows the exact values in scope at the point of failure.

```python
from runtime_narrative import story, stage, FailureDiagnosticsConfig

rich_config = FailureDiagnosticsConfig(failure_diagnostics="rich")

def process_payment(card_number: str, amount: float) -> None:
    retries = 3
    raise ValueError("gateway timeout")

try:
    with story("Checkout", diagnostics_config=rich_config):
        with stage("Charge Card"):
            process_payment("4111111111111111", 99.99)
except ValueError:
    pass
# FailureOccurred.locals_by_frame contains: amount=99.99, retries=3
# card_number is NOT redacted by default — add redact_extra=("card_number",) to redact it
```

**`FailureDiagnosticsConfig` field reference:**

| Field | Default | Description |
|-------|---------|-------------|
| `runtime_environment` | `"development"` | `"development"` or `"production"` |
| `failure_diagnostics` | `"lean"` | `"lean"` or `"rich"` |
| `allow_rich_in_production` | `False` | Bypass the production safety guard |
| `app_roots` | `()` | Directories whose frames are labeled "app" for primary frame selection. Defaults to cwd when empty. |
| `redact_extra` | `()` | Additional key substrings to redact (case-insensitive substring match) |
| `redact_patterns` | `()` | Regex patterns matched against local variable key names |
| `redact_callback` | `None` | `Callable[[str], bool]` — return `True` to redact the key |
| `max_traceback_chars` | `12_000` | Truncate traceback text in development at this length |
| `production_traceback_cap` | `8_000` | Traceback cap applied in production |
| `max_locals_per_frame` | `12` | Maximum local variables captured per frame |
| `max_local_value_len` | `200` | Maximum character length for a single variable's repr |
| `max_local_depth` | `2` | Recursion depth when serializing nested containers |
| `max_frames_with_locals` | `2` | Number of frames (starting at primary) for which locals are captured |
| `snippet_context_lines` | `2` | Lines of source before and after the primary line |

### 9.3 Production mode

In production, two safety behaviors are enforced automatically:

1. The traceback is truncated at `production_traceback_cap` (default 8 000 characters).
2. Rich mode is forced to lean unless `allow_rich_in_production=True` is explicitly set.

```python
from runtime_narrative import story, stage, FailureDiagnosticsConfig

prod_config = FailureDiagnosticsConfig(
    runtime_environment="production",
    failure_diagnostics="lean",
)

try:
    with story("Checkout", diagnostics_config=prod_config):
        with stage("Charge Card"):
            raise RuntimeError("connection pool exhausted")
except RuntimeError:
    pass
```

To use rich mode in production (e.g., a controlled staging environment):

```python
prod_rich = FailureDiagnosticsConfig(
    runtime_environment="production",
    failure_diagnostics="rich",
    allow_rich_in_production=True,
)
```

Production mode can also be set without constructing a full config:

```python
with story("Job", runtime_environment="production", failure_diagnostics="lean"):
    ...
```

### 9.4 Secret redaction

When rich mode captures local variables, any variable whose name matches a redacted pattern has its value replaced with `"<redacted>"`. The count of redacted keys is reported in `FailureOccurred.redaction_removed_keys`.

**Built-in redacted key substrings** (case-insensitive, substring match):
`password`, `secret`, `token`, `api_key`, `apikey`, `authorization`, `cookie`, `session`, `credential`

**`redact_extra`** — additional substrings:

```python
config = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    redact_extra=("card_number", "cvv", "ssn"),
)

def pay(card_number: str, cvv: str, amount: float) -> None:
    raise ValueError("declined")

try:
    with story("Payment", diagnostics_config=config):
        with stage("Charge"):
            pay("4111111111111111", "123", 99.99)
except ValueError:
    pass
# card_number → <redacted>, cvv → <redacted>, amount → 99.99
```

**`redact_patterns`** — regular expressions matched against variable names:

```python
config = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    redact_patterns=(
        r"pan$",        # matches card_pan, account_pan
        r"^priv_",      # matches priv_key, priv_cert
        r"_hash$",      # matches pw_hash, token_hash
    ),
)
```

**`redact_callback`** — a custom predicate for arbitrary logic:

```python
config = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    redact_callback=lambda key: key.endswith("_ref") or key.startswith("internal_"),
)
```

All three mechanisms compose additively — specifying `redact_extra` does not disable the built-in list.

### 9.5 `from_env()` and environment variable overrides

`FailureDiagnosticsConfig.from_env()` reads configuration from environment variables:

| Environment variable | Effect |
|---------------------|--------|
| `RUNTIME_NARRATIVE_ENV` | Sets `runtime_environment`. Values: `development` (default), `production` |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | Sets `failure_diagnostics`. Values: `lean` (default), `rich` |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | Sets `allow_rich_in_production`. Values: `1`, `true` |

When you construct `story(...)` without passing `diagnostics_config`, the story internally calls `from_env()` as the base and applies any kwargs on top of it via `merge()`. This means you can change diagnostic depth across all stories in a process by setting environment variables — useful for debugging in non-production environments.

```bash
# Enable rich diagnostics for a single run without code changes
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich python examples/basic.py
```

### 9.6 `FailureDiagnosticsConfig.merge()`

`merge()` creates a new config by overlaying specified fields onto an existing base config. Fields you do not specify are inherited from the base unchanged.

```python
from runtime_narrative import FailureDiagnosticsConfig

base = FailureDiagnosticsConfig.from_env()

# Specialise for a single story
per_story = FailureDiagnosticsConfig.merge(
    base,
    failure_diagnostics="rich",
    redact_extra=("card_number", "cvv"),
)

# Specialise for production
prod = FailureDiagnosticsConfig.merge(
    base,
    runtime_environment="production",
    failure_diagnostics="lean",
)
```

### 9.7 Built-in Failure Analyzers

Failure analyzers attach LLM-generated explanations to `FailureOccurred`. Pass any analyzer as `failure_analyzer=` to `story()`, a decorator, or middleware.

#### `OllamaFailureAnalyzer`

Uses Ollama's native `/api/generate` endpoint. A dataclass — pass fields as constructor arguments.

```python
from runtime_narrative import OllamaFailureAnalyzer, story, stage

analyzer = OllamaFailureAnalyzer(
    model="llama3",
    endpoint="http://127.0.0.1:11434/api/generate",  # default
    timeout_seconds=30.0,
    max_context_chars=8000,
)

try:
    with story("Pipeline", failure_analyzer=analyzer):
        with stage("Load"):
            raise ValueError("source file missing")
except ValueError:
    pass
```

| Field | Default | Description |
|-------|---------|-------------|
| `model` | required | Ollama model name |
| `endpoint` | `"http://127.0.0.1:11434/api/generate"` | Ollama API endpoint |
| `timeout_seconds` | `12.0` | HTTP timeout |
| `include_traceback_lines` | `30` | Lines of traceback sent in the prompt |
| `max_context_chars` | `8000` | Total prompt character budget; traceback is trimmed to fit |

#### `LLMFailureAnalyzer`

OpenAI-compatible `/v1/chat/completions` endpoint. Works with vLLM, llama.cpp, LM Studio, and Ollama in OpenAI mode.

```python
from runtime_narrative import LLMFailureAnalyzer

analyzer = LLMFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:8000/v1/chat/completions",
    timeout_seconds=30.0,
)
```

Both `OllamaFailureAnalyzer` and `LLMFailureAnalyzer` request structured JSON from the model (`exact_why`, `evidence`, `targeted_fix`, `code_changes`) and format the response into `## Exact Why / ## Evidence / ## Targeted Fix / ## Code Changes` sections. If the model returns non-JSON, the raw text is used as a fallback.

#### `AnthropicFailureAnalyzer`

Calls the Anthropic API. Requires the `[anthropic]` extra and `ANTHROPIC_API_KEY`.

```python
from runtime_narrative import AnthropicFailureAnalyzer

analyzer = AnthropicFailureAnalyzer(
    model="claude-haiku-4-5-20251001",  # default; override via RUNTIME_NARRATIVE_MODEL
    api_key=None,                        # reads ANTHROPIC_API_KEY
    timeout_seconds=30.0,
    max_tokens=1024,
)
```

Provides both `analyze_failure` (sync, using `anthropic.Anthropic`) and `analyze_failure_async` (async, using `anthropic.AsyncAnthropic`). Response parsing identical to the OpenAI-compatible analyzers.

#### `DeduplicatingAnalyzer`

Wraps any analyzer to avoid repeat API calls for the same error site.

```python
from runtime_narrative import AnthropicFailureAnalyzer, DeduplicatingAnalyzer

inner = AnthropicFailureAnalyzer()
analyzer = DeduplicatingAnalyzer(inner, max_cache_size=256)
```

The cache key is a SHA-256 hash of `(error_type, filename, lineno, exception_chain)`. `None` results (network failures, timeouts) are never cached — the next call retries the model. LRU eviction applies when the cache reaches `max_cache_size`. Thread-safe. Delegates to `inner.analyze_failure_async()` when available.

---

## 10. Renderers

A renderer is any object with a `handle(self, event: object)` method. There is no base class, no registration step. Sync renderers work with both `with story(...)` and `async with story(...)`; async renderers (whose `handle` is a coroutine) are only awaited when using `async with story(...)`. Renderer exceptions are caught, printed to stderr, and never crash the story.

```python
from runtime_narrative import story, stage

async with story("My Pipeline", renderers=[RendererA(), RendererB()]):
    async with stage("Step 1"):
        ...
```

### 10.1 ConsoleRenderer

Prints colored, human-readable output to stdout. Uses `typer.secho` for color when the `console` extra is installed; falls back to plain `print` otherwise. Automatically substitutes ASCII glyphs (`>`, `[ok]`, `[FAIL]`) for Unicode ones on non-UTF-8 terminals. Handles all seven events (including `LogRecorded`).

`ConsoleRenderer` is the default when no `renderers=` argument is passed to `story()`.

Every line carries a `[short_id]` tag (first 6 characters of that event's `story_id`), colored per story family (a root story and its sub-stories share one deterministic color), and indented by nesting depth (one level per open stage / sub-story). See [§21 Sub-stories and Log Capture](#21-sub-stories-and-log-capture) for the full nested output.

```python
from runtime_narrative import story, stage, ConsoleRenderer  # top-level import

with story("Import Pipeline", renderers=[ConsoleRenderer()]):
    with stage("Load CSV"):
        data = ["alice", "bob"]
    with stage("Validate"):
        assert data
```

### 10.2 JsonRenderer

Emits one JSON object per line to stdout (or a file). Designed for log aggregators and NDJSON pipelines. `FailureOccurred` output includes the full extended diagnostics payload: `stack_frames`, `source_snippet`, `locals_by_frame`, `traceback_text`, and all other fields.

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.json_renderer import JsonRenderer

# Write to stdout (default)
with story("ETL Run", renderers=[JsonRenderer()]):
    with stage("Extract"):
        pass

# Write to a file with indentation
with open("events.json", "w") as f:
    renderer = JsonRenderer(output=f, indent=2)
    with story("ETL Run", renderers=[renderer]):
        with stage("Extract"):
            pass
```

| Argument | Default | Effect |
|---|---|---|
| `output` | `sys.stdout` | Any file-like object with a `write` method |
| `indent` | `None` | Passed to `json.dumps`; `None` produces compact single-line output |

### 10.3 RotatingJsonRenderer

A subclass of `JsonRenderer` that rotates the output file when it reaches a size limit, following `logging.handlers.RotatingFileHandler` naming conventions.

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.json_renderer import RotatingJsonRenderer

renderer = RotatingJsonRenderer(
    "narrative_events.log",
    max_bytes=5 * 1024 * 1024,  # rotate at 5 MB
    backup_count=3,              # keep .log, .log.1, .log.2, .log.3
)

with story("Nightly Batch", renderers=[renderer]):
    with stage("Fetch Orders"):
        pass
```

| Argument | Default | Effect |
|---|---|---|
| `path` | required | Destination file path |
| `max_bytes` | `10_485_760` (10 MB) | Rotate when the active file exceeds this size. `0` disables. |
| `backup_count` | `5` | Number of rotated files to keep |
| `indent` | `None` | JSON indentation |

### 10.4 HtmlReportRenderer

Writes a self-contained HTML report file on `StoryCompleted`. Includes a story header with outcome badge, stage timeline bar chart (proportional durations), and (on failure) a failure detail section with the traceback and any LLM analysis. No external CSS or JS dependencies.

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.html_renderer import HtmlReportRenderer

renderer = HtmlReportRenderer("report.html", open_browser=True)

with story("Data Pipeline", renderers=[renderer]):
    with stage("Load"):
        pass
    with stage("Transform"):
        pass
    with stage("Export"):
        pass
# After the with block, report.html is written and opened in the default browser
```

| Argument | Default | Effect |
|---|---|---|
| `path` | required | Output file path (created or overwritten on `StoryCompleted`) |
| `open_browser` | `False` | Open the file in the system browser after writing |

`HtmlReportRenderer` collects all events in memory and writes on `StoryCompleted`. If the process is killed before the story completes, no file is written.

### 10.5 SqliteStoryRenderer

Persists all story events to a SQLite database. No extra dependencies — uses stdlib `sqlite3`. The connection is opened lazily on the first `handle()` call; tables are created with `CREATE TABLE IF NOT EXISTS`.

See [Section 13](#13-sqlite-persistence-and-cli) for the schema and CLI details.

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.persistence_renderer import SqliteStoryRenderer

renderer = SqliteStoryRenderer("myapp.db")

with story("User Import", renderers=[renderer]):
    with stage("Fetch Users"):
        pass
    with stage("Upsert"):
        pass
```

| Argument | Default | Effect |
|---|---|---|
| `db_path` | `"runtime_narrative.db"` | SQLite file path (created if it does not exist) |

### 10.6 OtelRenderer

Maps story events to OpenTelemetry spans. Each story becomes a root span; each stage becomes a child span. On `FailureOccurred`, the story span's status is set to `ERROR` with rich attributes. On `LLMAnalysisReady`, a span event is added. Requires the `[otel]` extra.

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from runtime_narrative import story, stage
from runtime_narrative.renderer.otel_renderer import OtelRenderer

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))

renderer = OtelRenderer(
    tracer_provider=provider,
    tracer_name="myapp",
    min_duration_ms=5.0,              # skip spans faster than 5 ms
    exclude_stages={"Health Check"},  # never create spans for these stages
)

with story("Order Processing", renderers=[renderer]):
    with stage("Validate"):
        pass
    with stage("Charge Card"):
        pass

spans = exporter.get_finished_spans()
for span in spans:
    print(span.name, span.status.status_code.name)
```

| Argument | Default | Effect |
|---|---|---|
| `tracer_provider` | `None` (uses global) | OTel `TracerProvider` |
| `tracer_name` | `"runtime_narrative"` | Tracer name for span attribution |
| `max_attribute_length` | `8192` | Truncate string span attributes to this length |
| `min_duration_ms` | `0.0` | Skip stage spans shorter than this duration |
| `exclude_stages` | `None` | Set of stage names whose spans are never created |

### 10.7 OtelLogRenderer

Emits all six lifecycle events as OpenTelemetry log records. Automatically correlates records with the ambient OTel context (trace ID, span ID, trace flags). Requires the `[otel]` extra.

| Event | Severity |
|---|---|
| `StoryStarted` | INFO |
| `StageStarted` | DEBUG |
| `StageCompleted` | DEBUG |
| `FailureOccurred` | ERROR — includes `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `narrative.exception_chain`, `error.stack_trace` |
| `LLMAnalysisReady` | INFO |
| `StoryCompleted` | INFO |

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.otel_log_renderer import OtelLogRenderer

renderer = OtelLogRenderer(logger_name="myapp.narrative")

async with story("Checkout Flow", renderers=[renderer]):
    async with stage("Validate Cart"):
        pass
    async with stage("Submit Payment"):
        pass
```

| Argument | Default | Effect |
|---|---|---|
| `logger_provider` | `None` (uses global) | OTel `LoggerProvider` |
| `logger_name` | `"runtime_narrative"` | Logger name |

### 10.8 OtelMetricsRenderer

Emits four OpenTelemetry metric instruments. Requires the `[otel]` extra.

| Instrument | Type | Unit | Labels |
|---|---|---|---|
| `narrative.stage.duration` | Histogram | `s` | `story_name`, `stage_name` |
| `narrative.story.duration` | Histogram | `s` | `story_name`, `success` |
| `narrative.story.failures` | Counter | `1` | `story_name`, `error_type` |
| `narrative.llm.analysis_latency` | Histogram | `s` | `story_name` — only fires with `background_analysis=True` |

```python
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from runtime_narrative import story, stage
from runtime_narrative.renderer.otel_metrics_renderer import OtelMetricsRenderer

reader = InMemoryMetricReader()
provider = MeterProvider(metric_readers=[reader])

renderer = OtelMetricsRenderer(meter_provider=provider, meter_name="myapp")

with story("Nightly Job", renderers=[renderer]):
    with stage("Extract"):
        pass
    with stage("Load"):
        pass

metrics = reader.get_metrics_data()
```

### 10.9 PrometheusRenderer

Emits four Prometheus metrics via `prometheus_client`. Requires the `[prometheus]` extra.

| Metric | Type | Labels |
|---|---|---|
| `narrative_story_duration_seconds` | Histogram | `story_name`, `success` |
| `narrative_stage_duration_seconds` | Histogram | `story_name`, `stage_name` |
| `narrative_story_failures_total` | Counter | `story_name`, `error_type` |
| `narrative_story_total` | Counter | `story_name`, `success` |

```python
from prometheus_client import CollectorRegistry, generate_latest
from runtime_narrative import story, stage
from runtime_narrative.renderer.prometheus_renderer import PrometheusRenderer

registry = CollectorRegistry()
renderer = PrometheusRenderer(registry=registry)

with story("API Request", renderers=[renderer]):
    with stage("Auth"):
        pass
    with stage("Fetch Data"):
        pass

print(generate_latest(registry).decode())
```

Pass a custom `registry` to isolate metrics in tests or multi-tenant setups. If `registry=None`, the default global registry is used.

### 10.10 AlertRoutingRenderer

An async renderer that fires on `FailureOccurred` events only. Calls all configured destinations concurrently via `asyncio.gather`. Destination failures are caught and logged to stderr — they never propagate to the story.

Because `AlertRoutingRenderer.handle` is a coroutine, it is **only awaited** when using `async with story(...)`. It silently does nothing in a sync `with story(...)` context.

```python
import asyncio
from runtime_narrative import story, stage
from runtime_narrative.renderer.alert_renderer import (
    AlertRoutingRenderer,
    HttpWebhookDestination,
    SlackWebhookDestination,
)

alert_renderer = AlertRoutingRenderer(
    destinations=[
        HttpWebhookDestination(
            "https://alerts.internal/webhook",
            headers={"Authorization": "Bearer mysecret"},
            timeout=5.0,
        ),
        SlackWebhookDestination(
            "https://hooks.slack.com/services/T000/B000/xxxx",
            timeout=8.0,
        ),
    ],
    only_stories={"Order Processing", "Nightly Billing"},  # filter by story name
    only_error_types={"TimeoutError", "ConnectionError"},   # filter by error class name
)

async def main():
    try:
        async with story("Payment Flow", renderers=[alert_renderer]):
            async with stage("Charge"):
                raise ConnectionError("gateway unreachable")
    except ConnectionError:
        pass

asyncio.run(main())
```

**`HttpWebhookDestination`** POSTs a JSON payload with fields: `story_id`, `story_name`, `stage_name`, `error_type`, `error_message`, `filename`, `lineno`, `function`, `llm_analysis`, `timestamp`.

**`SlackWebhookDestination`** (subclass of `HttpWebhookDestination`) posts a Block Kit payload: a header block ("Story failed: {name}"), a section block with stage/error/location, and an optional analysis section when `llm_analysis` is present.

---

## 11. Framework Integrations

### 11.1 FastAPI / Starlette

`RuntimeNarrativeMiddleware` wraps every HTTP request in `async with story("METHOD /path")`. Route handlers receive the story context automatically and call `stage()` directly — no `story()` block needed in handlers.

```python
from fastapi import FastAPI
from runtime_narrative import RuntimeNarrativeMiddleware, stage
from runtime_narrative.renderer.json_renderer import JsonRenderer

app = FastAPI()

app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[JsonRenderer()],
    failure_diagnostics="rich",
    app_roots=["myapp"],
)

@app.post("/orders")
async def create_order(payload: dict):
    async with stage("Validate Input"):
        assert payload.get("item_id"), "item_id required"
    async with stage("Persist Order"):
        return {"order_id": 42}
```

**Auto-renderer selection.** When `renderers` is omitted, the middleware checks `sys.stdout.isatty()`: TTY → `ConsoleRenderer` (local dev), non-TTY → `JsonRenderer` (Docker/CI/production).

**W3C traceparent propagation.** The middleware reads `traceparent`/`tracestate` headers from each incoming request and attaches the extracted OTel context before creating the story span. Story spans become children of the caller's trace when combined with `OtelRenderer`.

```python
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[OtelRenderer(tracer_provider=my_provider)],
    propagate_trace_context=True,   # default; set False to disable
)
```

All diagnostic kwargs supported by `story()` are forwarded: `diagnostics_config`, `runtime_environment`, `failure_diagnostics`, `allow_rich_in_production`, `app_roots`, `redact_extra`. Requires the `[fastapi]` extra.

**Disabling instrumentation per-request.** Pass a `skip_if` callable to suppress story creation for specific requests — useful for health checks, metrics scrapers, or test clients:

```python
app.add_middleware(
    RuntimeNarrativeMiddleware,
    renderers=[JsonRenderer()],
    skip_if=lambda req: req.url.path in ("/health", "/metrics", "/readyz"),
)
```

When `skip_if(request)` returns `True`, the request passes straight through with no story created and no events emitted.

Run: `uv run python examples/middleware_skip_if.py`

### 11.2 Django

Two middleware classes are provided: an async ASGI variant and a sync WSGI variant. Both follow the same story naming convention (`"GET /path"`, `"POST /path"`).

**Async ASGI:**

```python
# settings.py
MIDDLEWARE = [
    "runtime_narrative.middleware_django.RuntimeNarrativeDjangoMiddleware",
    "django.middleware.common.CommonMiddleware",
    # ...
]
```

The async middleware uses `async with story(...)`, so async renderers are awaited and `AlertRoutingRenderer` works correctly.

**Sync WSGI:**

```python
MIDDLEWARE = [
    "runtime_narrative.middleware_django.RuntimeNarrativeDjangoSyncMiddleware",
    # ...
]
```

**Passing options** — Django does not support constructor kwargs in `MIDDLEWARE`. Subclass to inject options:

```python
# myapp/middleware.py
from runtime_narrative.middleware_django import RuntimeNarrativeDjangoMiddleware
from runtime_narrative.renderer.json_renderer import RotatingJsonRenderer

class AppNarrativeMiddleware(RuntimeNarrativeDjangoMiddleware):
    def __init__(self, get_response):
        super().__init__(
            get_response,
            renderers=[RotatingJsonRenderer("narrative.log")],
            failure_diagnostics="rich",
        )
```

Both classes auto-select `ConsoleRenderer` on TTY, `JsonRenderer` otherwise, when `renderers` is omitted. Requires the `[django]` extra.

### 11.3 Celery

**Using `NarrativeTask` as a base class:**

```python
from celery import Celery
from runtime_narrative.celery import NarrativeTask
from runtime_narrative import stage

app = Celery("myapp", broker="redis://localhost:6379/0")

@app.task(base=NarrativeTask)
def process_invoice(invoice_id: int) -> dict:
    with stage("Fetch Invoice"):
        invoice = {"id": invoice_id, "amount": 100}
    with stage("Calculate Tax"):
        invoice["tax"] = invoice["amount"] * 0.1
    return invoice
```

The story name is `"myapp.tasks.process_invoice [task_id=<celery-task-id>]"`. Configure renderers via class-level attributes:

```python
from runtime_narrative.celery import NarrativeTask
from runtime_narrative.renderer.json_renderer import RotatingJsonRenderer

class MyTask(NarrativeTask):
    narrative_renderers = [RotatingJsonRenderer("celery_narrative.log")]
    narrative_failure_diagnostics = "rich"
    narrative_app_roots = ["myapp"]

@app.task(base=MyTask)
def process_invoice(invoice_id: int) -> dict:
    ...
```

**Using `connect_narrative` to configure all tasks globally:**

```python
from runtime_narrative.celery import NarrativeTask, connect_narrative
from runtime_narrative.renderer.json_renderer import RotatingJsonRenderer

connect_narrative(
    app,
    renderers=[RotatingJsonRenderer("celery_narrative.log")],
    failure_diagnostics="rich",
    app_roots=["myapp"],
)

# All tasks using base=NarrativeTask now use these settings
@app.task(base=NarrativeTask)
def send_email(user_id: int) -> None: ...

@app.task(base=NarrativeTask)
def generate_report(report_id: int) -> None: ...
```

`NarrativeTask` uses `with story(...)` (sync). Async renderers are not awaited. Requires the `[celery]` extra.

### 11.4 gRPC

**Sync interceptor:**

```python
import grpc
from concurrent import futures
from runtime_narrative.grpc_interceptor import RuntimeNarrativeInterceptor
from runtime_narrative.renderer.json_renderer import JsonRenderer

interceptor = RuntimeNarrativeInterceptor(
    renderers=[JsonRenderer()],
    failure_diagnostics="rich",
)

server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[interceptor],
)
```

Inside a servicer, call `stage()` without wrapping in your own `story()`:

```python
from runtime_narrative import stage

class OrderServicer(orders_pb2_grpc.OrderServiceServicer):
    def CreateOrder(self, request, context):
        with stage("Validate"):
            assert request.item_id, "item_id required"
        with stage("Persist"):
            return orders_pb2.OrderResponse(order_id=42)
```

**Async interceptor:**

```python
import grpc.aio
from runtime_narrative.grpc_interceptor import RuntimeNarrativeAsyncInterceptor

interceptor = RuntimeNarrativeAsyncInterceptor(
    renderers=[JsonRenderer()],
)

server = grpc.aio.server(interceptors=[interceptor])
```

The async interceptor uses `async with story(...)`, so async renderers are awaited. Requires the `[grpc]` extra.

---

## 12. Async Task Groups

`NarrativeTaskGroup` runs concurrent asyncio tasks inside a shared story. It works on Python 3.9+ and preserves the story context across all child tasks automatically via asyncio's `ContextVar` copy-on-task-create behaviour.

### How context propagates

When `asyncio.create_task` is called, asyncio copies the current `contextvars.Context` snapshot to the new task. Because `current_story` is a `ContextVar`, each child task automatically sees the parent story — no explicit passing required.

### Success path

```python
import asyncio
from runtime_narrative import story, stage
from runtime_narrative.task_group import NarrativeTaskGroup

async def fetch_users():
    async with stage("Fetch Users"):
        await asyncio.sleep(0.02)
        return ["alice", "bob"]

async def fetch_config():
    async with stage("Fetch Config"):
        await asyncio.sleep(0.01)
        return {"timeout": 30}

async def main():
    async with story("Startup", total_stages=2):
        async with NarrativeTaskGroup() as tg:
            users_task = tg.create_task(fetch_users(), name="fetch-users")
            config_task = tg.create_task(fetch_config(), name="fetch-config")
        # Both tasks have completed when __aexit__ returns
        users = await users_task
        config = await config_task

asyncio.run(main())
```

### Failure path

If any task raises, `NarrativeTaskGroup.__aexit__` collects all failures and raises `NarrativeTaskGroupError`. The `failed_tasks` attribute maps task name to exception.

```python
from runtime_narrative.task_group import NarrativeTaskGroup, NarrativeTaskGroupError

async def unreliable():
    async with stage("Unreliable Step"):
        raise ConnectionError("upstream timed out")

async def fine():
    async with stage("Fine Step"):
        await asyncio.sleep(0.01)

async def main():
    async with story("Parallel Work"):
        try:
            async with NarrativeTaskGroup() as tg:
                tg.create_task(unreliable(), name="unreliable")
                tg.create_task(fine(), name="fine")
        except NarrativeTaskGroupError as exc:
            for name, error in exc.failed_tasks.items():
                print(f"Task {name!r} failed: {type(error).__name__}: {error}")

asyncio.run(main())
```

If an exception propagates out of the `async with NarrativeTaskGroup()` block before `__aexit__` runs normally, all pending tasks are cancelled.

`NarrativeTaskGroup` requires no extra dependencies and does not require Python 3.11's `asyncio.TaskGroup`.

---

## 13. SQLite Persistence and CLI

### Schema

`SqliteStoryRenderer` creates three tables on first use:

**`stories`** — one row per story:

| Column | Type | Description |
|---|---|---|
| `story_id` | TEXT PK | UUID |
| `name` | TEXT | Story name |
| `started_at` | TEXT | ISO-8601 timestamp |
| `completed_at` | TEXT | ISO-8601 timestamp |
| `success` | INTEGER | 1 = success, 0 = failed |
| `duration_seconds` | REAL | Computed from timestamps via `julianday` |

**`stages`** — one row per stage execution:

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `story_id` | TEXT | FK to stories |
| `stage_name` | TEXT | Stage name |
| `stage_index` | INTEGER | Position in story |
| `parent_stage_name` | TEXT | Null for top-level stages |
| `started_at` | TEXT | |
| `completed_at` | TEXT | |
| `duration_seconds` | REAL | |
| `completed` | INTEGER | 1 when `StageCompleted` emitted |
| `failed` | INTEGER | 1 when `FailureOccurred` emitted |

**`failures`** — one row per failure:

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `story_id` | TEXT | FK to stories |
| `stage_name` | TEXT | Stage where failure occurred |
| `error_type` | TEXT | Exception class name |
| `error_message` | TEXT | `str(exc)` |
| `filename` | TEXT | Primary frame path |
| `lineno` | INTEGER | Primary frame line number |
| `function` | TEXT | Primary frame function name |
| `source_line` | TEXT | Failing source line |
| `traceback_text` | TEXT | Full traceback |
| `exception_chain` | TEXT | |
| `llm_analysis` | TEXT | Null until `LLMAnalysisReady` back-fills it |
| `occurred_at` | TEXT | `datetime('now')` |

### Wiring up the renderer

```python
from runtime_narrative import story, stage
from runtime_narrative.renderer.persistence_renderer import SqliteStoryRenderer

db = SqliteStoryRenderer("narrative.db")

with story("User Import", renderers=[db], total_stages=2):
    with stage("Fetch"):
        users = [{"id": 1, "name": "Alice"}]
    with stage("Upsert"):
        pass
```

### CLI

The `runtime-narrative` CLI is registered as a console script at install time.

**List recent failures:**

```bash
# Last 10 failures in the default database
runtime-narrative failures

# Last 25 failures in a custom database
runtime-narrative failures --db narrative.db --last 25

# Filter by stage name
runtime-narrative failures --stage "Upsert"

# Filter by story name
runtime-narrative failures --story "User Import"

# Combine filters
runtime-narrative failures --stage "Charge Card" --story "Order%" --last 5
```

**Show full details for a specific story:**

```bash
runtime-narrative story <story_id>
runtime-narrative story a1b2c3d4 --db narrative.db
```

The `story` subcommand prints the story summary, a table of all stages with status and duration, and full failure details including LLM analysis when available.

**Direct SQL access:**

Since the database is plain SQLite you can query it directly with any tool:

```python
import sqlite3

conn = sqlite3.connect("narrative.db")

# Failed stories in the last hour
rows = conn.execute("""
    SELECT name, duration_seconds, completed_at
    FROM stories
    WHERE success = 0
      AND completed_at > datetime('now', '-1 hour')
    ORDER BY completed_at DESC
""").fetchall()

# Most common failure types
rows = conn.execute("""
    SELECT error_type, COUNT(*) as count
    FROM failures
    GROUP BY error_type
    ORDER BY count DESC
""").fetchall()
```

---

## 14. Testing with StoryRecorder

`StoryRecorder` is a dual sync/async context manager for use in tests. It creates the story context internally, records every emitted event, and provides assertion helpers that produce clear failure messages.

### The key design rule

**`StoryRecorder` IS the story.** Functions under test must call `stage()` directly without their own `story()` wrapper. If the function under test wraps itself in `story()`, the story contexts will nest and stage events from the inner story will not be visible to the recorder.

```python
# Correct — the function calls stage() directly, no story() inside
def import_users(path: str) -> None:
    from runtime_narrative import stage
    with stage("Read File"):
        data = open(path).read()
    with stage("Parse CSV"):
        rows = [line.split(",") for line in data.splitlines()]
    with stage("Upsert"):
        pass

# In the test:
from runtime_narrative.testing import StoryRecorder

def test_import_users(tmp_path):
    csv = tmp_path / "users.csv"
    csv.write_text("alice,alice@example.com\n")
    with StoryRecorder("User Import") as r:
        import_users(str(csv))
    r.assert_stages_completed(["Read File", "Parse CSV", "Upsert"])
    r.assert_no_failure()
```

### All four assertion methods

```python
# 1. Verify that each named stage emitted StageCompleted
r.assert_stages_completed(["Load", "Validate", "Insert"])
# → AssertionError: "Expected stages not completed: ['Insert']. Completed stages were: ['Load', 'Validate']"

# 2. Verify no FailureOccurred was emitted
r.assert_no_failure()
# → AssertionError: "Expected no failure but got: ValueError: duplicate key at ..."

# 3. Verify a specific stage raised — error_type is a STRING (the class name)
r.assert_stage_failed("Insert")
r.assert_stage_failed("Insert", error_type="ValueError")
# → AssertionError: "Expected error type 'ValueError' at stage 'Insert' but got 'KeyError'"

# 4. Verify StoryCompleted was emitted
r.assert_story_completed()
r.assert_story_completed(success=True)
r.assert_story_completed(success=False)
```

**Important:** `error_type` in `assert_stage_failed` is a **string** (e.g., `"ValueError"`), not the class itself. `FailureOccurred.error_type` is always a string.

### Sync and async patterns

```python
import asyncio
from runtime_narrative import stage
from runtime_narrative.testing import StoryRecorder

# Sync
def test_sync_success():
    with StoryRecorder("Pipeline", total_stages=2) as r:
        with stage("Step A"):
            pass
        with stage("Step B"):
            pass
    r.assert_stages_completed(["Step A", "Step B"])
    r.assert_no_failure()

# Async
async def _async_pipeline(fail: bool):
    async with stage("Fetch"):
        await asyncio.sleep(0)
    async with stage("Save"):
        if fail:
            raise IOError("disk full")

def test_async_failure():
    async def run():
        async with StoryRecorder("Async Pipeline") as r:
            await _async_pipeline(fail=True)
        return r

    import pytest
    with pytest.raises(IOError):
        r = asyncio.run(run())
    r.assert_stage_failed("Save", error_type="IOError")
    r.assert_story_completed(success=False)
```

### Inspecting raw events

All emitted events are available on `recorder.events`:

```python
with StoryRecorder("Pipeline") as r:
    with stage("Load"):
        pass

stage_events = [e for e in r.events if type(e).__name__ == "StageCompleted"]
assert stage_events[0].duration_seconds >= 0

story_started = next(e for e in r.events if type(e).__name__ == "StoryStarted")
assert story_started.story_name == "Pipeline"
```

### Using dry_run with StoryRecorder

```python
def test_stages_are_wired_up():
    with StoryRecorder("Pipeline", dry_run=True) as r:
        with stage("Fetch from DB"):
            raise RuntimeError("skipped — no DB in test")
        with stage("Write to S3"):
            raise RuntimeError("skipped — no S3 in test")
    r.assert_stages_completed(["Fetch from DB", "Write to S3"])
    r.assert_no_failure()
```

---

## 15. dry_run Mode

`dry_run=True` on `story()` puts the runtime into skeleton mode: stage bodies are executed, but any exception raised inside a stage is silently suppressed. The stage is reported as `StageCompleted` and the story completes with `success=True`. No `FailureOccurred` event is emitted.

### What it does and does not do

- Stage bodies **run** — code up to the exception executes normally.
- Exceptions **do not propagate** out of the `stage()` block.
- No `FailureOccurred` is emitted; no LLM analysis is triggered.
- `StageCompleted` is emitted for every stage.
- The story ends with `StoryCompleted(success=True)`.

### When to use it

`dry_run` is designed for smoke-testing instrumentation without side effects:

- Verify that all expected stages are wired up before running the real pipeline.
- CI checks that confirm instrumentation coverage without a database, S3, or external API.
- Generating an HTML report or SQLite schema from a "dry" run.

### Before and after comparison

```python
from runtime_narrative import story, stage

# Without dry_run: ValueError propagates
try:
    with story("Import Pipeline"):
        with stage("Fetch from DB"):
            raise ValueError("no DB configured")
        with stage("Write to S3"):
            pass  # never reached
except ValueError:
    pass

# With dry_run=True: exceptions suppressed, all stages complete
with story("Import Pipeline", dry_run=True):
    with stage("Fetch from DB"):
        raise ValueError("no DB configured")  # suppressed
    with stage("Write to S3"):
        raise RuntimeError("no S3 in test")   # suppressed
# Story ends: SUCCESS — both stages show as completed
```

`dry_run` works identically for `async with stage(...)`:

```python
import asyncio
from runtime_narrative import story, stage

async def main():
    async with story("Pipeline", dry_run=True):
        async with stage("Fetch"):
            raise IOError("network unavailable")  # suppressed
        async with stage("Process"):
            raise TypeError("schema mismatch")    # suppressed

asyncio.run(main())
```

---

## 16. Background Analysis

By default, when a `failure_analyzer` is configured, `story.__aexit__` calls the analyzer and blocks until it returns before emitting `FailureOccurred`. For remote LLM APIs this can add seconds of latency to the failure path.

Setting `background_analysis=True` changes this to a non-blocking two-event sequence:

1. `FailureOccurred` is emitted immediately with `llm_analysis=None`.
2. The story emits `StoryCompleted` and the context exits — the HTTP response (or story block) returns.
3. An `asyncio.Task` running the analyzer completes later and emits `LLMAnalysisReady`.

### Requirements

`background_analysis=True` only works with `async with story(...)`. The asyncio event loop must remain running after the story exits for the background task to complete. In a web server context (FastAPI, Django ASGI) this is always the case.

### Code example

```python
import asyncio
from runtime_narrative import story, stage
from runtime_narrative.analyzers.ollama import OllamaFailureAnalyzer
from runtime_narrative.renderer.console import ConsoleRenderer

analyzer = OllamaFailureAnalyzer(model="llama3", timeout_seconds=30.0)

async def main():
    try:
        async with story(
            "Checkout",
            renderers=[ConsoleRenderer()],
            failure_analyzer=analyzer,
            background_analysis=True,  # FailureOccurred fires immediately
        ):
            async with stage("Charge Card"):
                raise ValueError("card number invalid")
    except ValueError:
        pass
    # FailureOccurred and StoryCompleted have already fired.
    # Give the background task time to complete.
    await asyncio.sleep(35)

asyncio.run(main())
```

### Observing the two-event sequence

```python
events_log = []

class SequenceRecorder:
    async def handle(self, event):
        events_log.append(type(event).__name__)

# After a failure with background_analysis=True, events arrive as:
# StoryStarted → StageStarted → FailureOccurred → StoryCompleted → LLMAnalysisReady
```

When `background_analysis=True` but no `failure_analyzer` is set, the story behaves identically to `background_analysis=False` — no `LLMAnalysisReady` is ever emitted.

---

## 17. Custom Renderers

Any object with a `handle` method is a valid renderer. There is no protocol to import, no base class to extend.

### Sync renderer

A sync renderer's `handle` method is called directly by `StoryRuntime.emit()`. It works with both sync and async stories.

```python
from runtime_narrative import story, stage

class MetricsRenderer:
    def __init__(self):
        self.stage_durations: dict[str, float] = {}

    def handle(self, event: object) -> None:
        name = type(event).__name__
        if name == "StageCompleted":
            self.stage_durations[event.stage_name] = event.duration_seconds
        elif name == "FailureOccurred":
            print(f"[metrics] failure: {event.error_type} in {event.stage_name!r}")

metrics = MetricsRenderer()

with story("ETL", renderers=[metrics]):
    with stage("Extract"):
        pass
    with stage("Load"):
        pass

print(metrics.stage_durations)
```

### Async renderer

An async renderer's `handle` coroutine is awaited by `StoryRuntime.emit_async()`. It is **only awaited** when using `async with story(...)`. In a sync `with story(...)` context the async handle is never called.

```python
import asyncio
import aiohttp
from runtime_narrative import story, stage

class WebhookRenderer:
    def __init__(self, url: str):
        self._url = url

    async def handle(self, event: object) -> None:
        if type(event).__name__ != "StageCompleted":
            return
        async with aiohttp.ClientSession() as session:
            await session.post(self._url, json={
                "stage": event.stage_name,
                "duration": event.duration_seconds,
            })

async def main():
    renderer = WebhookRenderer("https://collector.internal/stages")
    async with story("Pipeline", renderers=[renderer]):
        async with stage("Step 1"):
            await asyncio.sleep(0.01)

asyncio.run(main())
```

### Inspecting event types

Use `type(event).__name__` to branch on event types without importing from `runtime_narrative.events`. This avoids circular imports in third-party renderer packages.

```python
def handle(self, event: object) -> None:
    name = type(event).__name__
    if name == "StoryStarted":
        self._start_timer(event.story_id)
    elif name == "StoryCompleted":
        elapsed = self._stop_timer(event.story_id)
        print(f"{event.story_name!r} took {elapsed:.2f}s, success={event.success}")
    elif name == "FailureOccurred":
        self._increment_counter(event.error_type)
    elif name == "LLMAnalysisReady":
        print(f"Analysis: {event.llm_analysis}")
```

If you prefer explicit imports:

```python
from runtime_narrative.events import StoryStarted, StageCompleted, FailureOccurred

def handle(self, event: object) -> None:
    if isinstance(event, FailureOccurred):
        ...
```

---

## 18. Custom Failure Analyzers

A failure analyzer is any object with an `analyze_failure` method. There is no base class.

### The protocol

```python
from runtime_narrative.failure import FailureSummary

class MyAnalyzer:
    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> str | None:
        ...

    # Optional async variant — if absent, analyze_failure is called via asyncio.to_thread
    async def analyze_failure_async(self, *, ...) -> str | None:
        ...
```

`FailureSummary` is a dataclass from `runtime_narrative.failure` with fields: `error_type`, `error_message`, `filename`, `lineno`, `function`, `source_line`, `exception_chain`, `exact_cause`, `traceback_text`.

Return a string to attach as `llm_analysis` on `FailureOccurred`, or return `None` to indicate no analysis.

### Minimal custom analyzer

```python
from runtime_narrative import story, stage

class RuleBasedAnalyzer:
    def analyze_failure(
        self, *, story_name, stage_name, failure, stage_timeline, progress_percent
    ) -> str | None:
        if failure.error_type == "FileNotFoundError":
            return (
                f"File not found at {failure.filename}:{failure.lineno}. "
                "Check that the input path exists and the service has read access."
            )
        if failure.error_type == "TimeoutError":
            return "Upstream timed out. Check network connectivity and retry budget."
        return None

with story("Pipeline", failure_analyzer=RuleBasedAnalyzer()):
    with stage("Read Config"):
        raise FileNotFoundError("config.json")
```

### Adding async support

If `analyze_failure_async` is present, `story.__aexit__` calls it directly. If only `analyze_failure` is present, the story wraps it in `asyncio.to_thread` to avoid blocking the event loop.

```python
import asyncio
import aiohttp

class HttpAnalyzer:
    def __init__(self, url: str):
        self._url = url

    def analyze_failure(self, *, story_name, stage_name, failure, stage_timeline, progress_percent):
        # Sync fallback — used in sync story() context
        import urllib.request, json
        payload = json.dumps({"traceback": failure.traceback_text}).encode()
        try:
            with urllib.request.urlopen(self._url, data=payload, timeout=10) as resp:
                return json.loads(resp.read())["analysis"]
        except Exception:
            return None

    async def analyze_failure_async(self, *, story_name, stage_name, failure, stage_timeline, progress_percent):
        # Preferred in async context — called directly without to_thread overhead
        async with aiohttp.ClientSession() as session:
            try:
                resp = await session.post(
                    self._url,
                    json={"traceback": failure.traceback_text},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                data = await resp.json()
                return data.get("analysis")
            except Exception:
                return None
```

---

## 19. Environment Variables

All environment variables are read by `FailureDiagnosticsConfig.from_env()` at story construction time. Programmatic configuration always takes precedence over environment variables via `merge()`.

| Variable | Values | Default | Effect |
|---|---|---|---|
| `RUNTIME_NARRATIVE_ENV` | `development`, `production` | `development` | In `production`: traceback capped at 8 000 chars; `rich` forced to `lean` unless `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION=1` |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean`, `rich` | `lean` | `rich` captures local variables for up to 2 frames |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | `1`, `true`, `yes`, `on` | off | Permits `rich` diagnostics even when `RUNTIME_NARRATIVE_ENV=production` |
| `RUNTIME_NARRATIVE_MODEL` | model name string | — | Read by `OllamaFailureAnalyzer`, `LLMFailureAnalyzer`, and `AnthropicFailureAnalyzer` to select a model |
| `RUNTIME_NARRATIVE_ENDPOINT` | URL | — | Custom LLM endpoint for example scripts |
| `ANTHROPIC_API_KEY` | API key | — | Required by `AnthropicFailureAnalyzer`; raises `ValueError` at construction if absent |

### Precedence rules

Environment variables form the base layer. Programmatic kwargs override them:

```python
import os
os.environ["RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS"] = "lean"

# Override for this specific story
with story(
    "My Story",
    failure_diagnostics="rich",          # wins over env var
    runtime_environment="development",
):
    ...
```

When `diagnostics_config=` is passed explicitly, the environment variables are ignored entirely:

```python
from runtime_narrative import FailureDiagnosticsConfig

config = FailureDiagnosticsConfig(
    runtime_environment="production",
    failure_diagnostics="rich",
    allow_rich_in_production=True,
    app_roots=("/opt/myapp",),
    redact_extra=("internal_token", "db_url"),
)

with story("Pipeline", diagnostics_config=config):
    ...
```

### Production behavior summary

```bash
# Rich downgraded to lean silently in production
RUNTIME_NARRATIVE_ENV=production \
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich \
python myapp.py

# Rich permitted explicitly in production
RUNTIME_NARRATIVE_ENV=production \
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich \
RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION=1 \
python myapp.py
```

---

## 20. Event Reference

All events are plain `dataclasses` and are part of the stable public API. Import them directly from `runtime_narrative`:

```python
from runtime_narrative import (
    StoryStarted, StageStarted, StageCompleted,
    FailureOccurred, StoryCompleted, LLMAnalysisReady, LogRecorded,
    Event,   # Union[StoryStarted, StageStarted, StageCompleted, FailureOccurred, StoryCompleted, LLMAnalysisReady, LogRecorded]
)
```

They are emitted in a fixed sequence within each story:

```
StoryStarted → (StageStarted → StageCompleted)* → [FailureOccurred] → StoryCompleted
                                                                              ↓
                                                              [LLMAnalysisReady]  (background_analysis only)
```

### StoryStarted

Emitted when the story context is entered.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID for this story execution |
| `story_name` | `str` | The name passed to `story(name)` |
| `timestamp` | `datetime` | Wall-clock time at story start |
| `parent_story_id` | `str \| None` | `story_id` of the enclosing story, or `None` for a root story |
| `root_story_id` | `str` | `story_id` of the top-most ancestor (itself, if this is a root story) |

### StageStarted

Emitted when a `stage()` context is entered.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the enclosing story |
| `story_name` | `str` | Name of the enclosing story |
| `stage_name` | `str` | The name passed to `stage(name)` |
| `timestamp` | `datetime` | Wall-clock time at stage start |
| `stage_index` | `int` | Zero-based position of this stage in the story (default `0`) |
| `parent_stage_name` | `str \| None` | Name of the enclosing stage, or `None` for top-level stages |
| `root_story_id` | `str` | `story_id` of the top-most ancestor story (lets a renderer group stages by call tree, not just by story) |

### StageCompleted

Emitted when a stage exits without exception (or in `dry_run` mode even if it raised).

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the enclosing story |
| `story_name` | `str` | Name of the enclosing story |
| `stage_name` | `str` | Stage name |
| `timestamp` | `datetime` | Wall-clock time at stage exit |
| `duration_seconds` | `float` | Elapsed time from stage enter to stage exit |
| `stage_index` | `int` | Zero-based position (default `0`) |
| `parent_stage_name` | `str \| None` | Name of the enclosing stage, or `None` |
| `root_story_id` | `str` | `story_id` of the top-most ancestor story |

`story_name` on stage events means a renderer can filter by story without tracking a `story_id → story_name` side table populated from `StoryStarted`/`StoryCompleted`. Run: `uv run python examples/stage_story_name.py`

### FailureOccurred

Emitted when an exception propagates out of the story block. Contains the full enriched failure payload.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the story |
| `story_name` | `str` | Story name |
| `stage_name` | `str` | Name of the stage where the failure occurred |
| `error_type` | `str` | Exception class name, e.g. `"ValueError"` |
| `error_message` | `str` | `str(exc)` |
| `filename` | `str` | Source file of the primary frame |
| `lineno` | `int` | Line number of the primary frame |
| `function` | `str` | Function name of the primary frame |
| `source_line` | `str` | Source text of the failing line |
| `exception_chain` | `str` | Human-readable chain of chained exceptions |
| `exact_cause` | `str` | Inferred one-line cause description |
| `llm_analysis` | `str \| None` | Analyzer output; `None` if no analyzer or `background_analysis=True` |
| `stage_timeline` | `str` | Text summary of all stages and their states |
| `progress_percent` | `int` | Percentage of stages completed at failure time |
| `completed_stages` | `int` | Count of `StageCompleted` events before this failure |
| `total_stages` | `int` | Total stages seen (or declared via `total_stages=`) |
| `timestamp` | `datetime` | Wall-clock time of failure |
| `traceback_text` | `str` | Full formatted traceback (may be truncated in production) |
| `diagnostics_mode` | `str` | `"lean"` or `"rich"` (default `"lean"`) |
| `primary_frame_reason` | `str` | Why this frame was chosen: `"leaf"`, `"innermost_app"`, or `"innermost_non_stdlib"` |
| `stack_frames` | `list[dict]` | Structured list of all frames; each dict has `index`, `filename`, `lineno`, `function`, `kind`, `line`, `is_primary` |
| `source_snippet` | `str \| None` | Multi-line source context around the primary frame (±`snippet_context_lines` lines) |
| `compressed_stack_summary` | `str` | One-line summary, e.g. `"2 app frame(s), 5 other/hidden in full stack (7 total)"` |
| `hidden_frame_count` | `int` | Number of non-app frames in the full stack |
| `traceback_truncated` | `bool` | `True` if `traceback_text` was capped |
| `locals_by_frame` | `dict \| None` | Local variables per frame (rich mode only); keys are `"frame_0"`, `"frame_1"`, etc. |
| `redaction_removed_keys` | `int` | Count of local variable keys that were redacted |
| `parent_story_id` | `str \| None` | `story_id` of the enclosing story, or `None` for a root story |
| `root_story_id` | `str` | `story_id` of the top-most ancestor story |

### StoryCompleted

Emitted unconditionally at story exit, after any `FailureOccurred`.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the story |
| `story_name` | `str` | Story name |
| `success` | `bool` | `True` if the story exited without exception |
| `progress_percent` | `int` | Final percentage of stages completed |
| `completed_stages` | `int` | Final count of completed stages |
| `total_stages` | `int` | Total stages seen or declared |
| `timestamp` | `datetime` | Wall-clock time at story exit |
| `duration_seconds` | `float` | Elapsed time from story enter to story exit |
| `parent_story_id` | `str \| None` | `story_id` of the enclosing story, or `None` for a root story |
| `root_story_id` | `str` | `story_id` of the top-most ancestor story |

### LLMAnalysisReady

Emitted after `StoryCompleted` only when `background_analysis=True` and the analyzer returned a non-`None` result.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the story that failed |
| `story_name` | `str` | Story name |
| `stage_name` | `str` | Stage where the failure occurred |
| `llm_analysis` | `str` | Analyzer output text |
| `timestamp` | `datetime` | Wall-clock time when the analysis completed |

### LogRecorded

Emitted by `NarrativeLogHandler` when it captures a stdlib `logging` record while a story is active.

| Field | Type | Description |
|---|---|---|
| `story_id` | `str` | UUID of the story active when the record was captured |
| `story_name` | `str` | Name of that story |
| `root_story_id` | `str` | `story_id` of the top-most ancestor story |
| `stage_name` | `str` | Name of the active stage, or `""` if none |
| `level` | `str` | `record.levelname`, e.g. `"WARNING"` |
| `logger_name` | `str` | `record.name` |
| `message` | `str` | `record.getMessage()` |
| `timestamp` | `datetime` | `record.created` as a `datetime` |
| `exc_text` | `str \| None` | Formatted exception text if the record carried `exc_info` |

---

## 21. Sub-stories and Log Capture

### Sub-stories

`story()` opened while another `story()` is already active (in the same sync/async context) automatically becomes a **sub-story** — no new API. It:

- Inherits `renderers`, `diagnostics_config`, and `failure_analyzer` from the parent unless you pass your own explicitly.
- Sets `parent_story_id` to the parent's `story_id`.
- Sets `root_story_id` to the top-most ancestor's `story_id` (so a 3-level nesting all shares one `root_story_id`).
- Still succeeds/fails and times itself independently — a failed sub-story does not automatically fail its parent.

```python
async def execute_query(sql: str):
    async with story(f"DB: {sql}") as db_story:
        async with stage("Execute Query"):
            await conn.execute(sql)

async def create_order():
    async with story("POST /orders") as api_story:
        async with stage("Persist Order"):
            await execute_query("INSERT INTO orders ...")
            # execute_query's story is a sub-story of api_story:
            #   parent_story_id == api_story.story_id
            #   root_story_id   == api_story.story_id
```

This works correctly under concurrency without extra effort: `asyncio.Task` copies `ContextVar` state at creation time, and each OS thread starts with a fresh top-level context, so multiple concurrent callers of a shared helper like `execute_query()` never cross-link into each other's story tree. `OtelRenderer` uses `parent_story_id` to make sub-stories real child spans of their parent span.

Run: `uv run python examples/substory_db_call.py`

### `NarrativeLogHandler`

Routes existing `logging.warning()`/`.error()` calls into the same event pipeline as `story()`/`stage()`, instead of a second, disconnected log stream:

```python
import logging
from runtime_narrative import NarrativeLogHandler

logging.getLogger().addHandler(NarrativeLogHandler(level=logging.WARNING))
```

Each captured record becomes a `LogRecorded` event. Outside an active story, records fall through to an optional `fallback` handler so nothing outside instrumentation is silently dropped:

```python
NarrativeLogHandler(level=logging.WARNING, fallback=logging.StreamHandler())
```

`ConsoleRenderer` tags every rendered line — including `LogRecorded` — with `[short_id]` (the first 6 characters of that event's `story_id`), and colors all events belonging to one story family (a root story plus any sub-stories) the same deterministic color. This gives a visual way to tell interleaved/concurrent stories apart on the console.

Lines are also indented one level per stage/sub-story nesting depth, so the call tree renders directly in the log:

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

The indent level for each story is tracked per `story_id` internally (base indent for a sub-story = parent's indent + parent's currently-open stage depth + 1) and cleaned up when that story's `StoryCompleted` is handled, so long-running processes don't leak memory per story.

Run: `uv run python examples/logging_bridge.py`
