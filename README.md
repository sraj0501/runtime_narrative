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

This README is a fast on-ramp. For complete API reference, every renderer/analyzer/integration in depth, and the full event schema, see **[WIKI.md](WIKI.md)**.

## Why

- **Stories and stages** — `story()`/`stage()` are dual sync/async context managers (or decorators, or auto-instrumentation) that need no restructuring of existing code.
- **Sub-story tracing** — nest a `story()` inside an active one (e.g. an API call triggering a DB query) and it auto-links as a traceable child with its own success/failure and duration — no new API.
- **Lean by default, rich on demand** — a compressed stack summary and exact failure frame always; local-variable capture with automatic secret redaction only when you ask for it.
- **Optional LLM diagnosis** — Ollama, any OpenAI-compatible endpoint, or Anthropic Claude can turn a traceback into an exact-cause explanation and a targeted fix.
- **Bring your own everything** — any object with `handle(event)` is a renderer; any object with `analyze_failure(...)` is an analyzer. Console, JSON, SQLite, OpenTelemetry, Prometheus, HTML, webhooks, and stdlib `logging` capture all ship built in.

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
| `django` | `django` — Django ASGI/WSGI middleware |
| `celery` | `celery` — `NarrativeTask`, `connect_narrative` |
| `grpc` | `grpcio` — gRPC server interceptors |
| `structlog` | `structlog` — richer default `ConsoleRenderer` style for captured `logging` output |
| `all` | Everything above |

```bash
pip install "runtime-narrative[console,fastapi,anthropic]"
```

---

## Quick start

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

`ConsoleRenderer` is the default and needs no configuration — on failure it prints the exact frame, a source snippet, the exception chain, and a compressed stack summary. `story`/`stage` are dual sync/async: `async with` works identically for async code.

---

## Sub-stories: end-to-end call tracing

Open a `story()` while another is already active (in the same sync/async context) and it automatically becomes a linked **sub-story** — inheriting the parent's renderers/diagnostics/analyzer, carrying `parent_story_id`/`root_story_id`, and succeeding or failing independently:

```python
async def execute_query(sql: str):
    async with story(f"DB: {sql}"):           # auto-linked to whatever story is active
        async with stage("Execute Query"):
            await conn.execute(sql)

async def create_order():
    async with story("POST /orders"):
        async with stage("Persist Order"):
            await execute_query("INSERT INTO orders ...")
```

`ConsoleRenderer` renders the resulting call tree directly, tagging every line with a `[short_id]`, coloring a whole story family consistently, and indenting by nesting depth:

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

This holds up under concurrency for free: `asyncio.Task` copies `ContextVar` state at creation and each OS thread starts with a fresh top-level context, so many concurrent callers sharing one helper (like `execute_query` above) never cross-link into each other's tree.

Run: `uv run python examples/substory_db_call.py` — full reference: [WIKI §21](WIKI.md#21-sub-stories-and-log-capture)

---

## Capture existing `logging` calls

`NarrativeLogHandler` folds `logging.warning()`/`.error()` into the same event pipeline as `story()`/`stage()` — one stream instead of two, tagged with the story/stage it happened in:

```python
import logging
from runtime_narrative import NarrativeLogHandler

logging.getLogger().addHandler(NarrativeLogHandler(level=logging.WARNING))
```

`extra={...}` becomes structured fields; with the `structlog` extra installed, `ConsoleRenderer` renders them with structlog's own default style (colored level, timestamp, `key=value` fields):

```python
logger.warning("cache miss", extra={"order_id": "ORD-42"})
# [d9e653] 2026-07-01T16:28:34 [warning  ] cache miss   order_id=ORD-42 stage=Fetch
```

Customize per-level prefixes or plug in your own renderer:

```python
ConsoleRenderer(level_icons={"warning": "⚠ ", "error": "✗ "})
```

Route different story families to different styles or destinations with `FilteredRenderer(predicate, renderer)` — every event carries `story_name`:

```python
from runtime_narrative import ConsoleRenderer, FilteredRenderer

renderers = [
    FilteredRenderer(lambda e: e.story_name.startswith("GET "), ConsoleRenderer()),
    FilteredRenderer(lambda e: not e.story_name.startswith("GET "), ConsoleRenderer(level_icons={"error": "✗ "})),
]
```

Run: `uv run python examples/logging_bridge.py`, `uv run python examples/structured_log_routing.py` — full reference: [WIKI §21](WIKI.md#21-sub-stories-and-log-capture)

---

## Feature tour

Everything below works the same way in every context (sync/async, decorators, auto-instrumentation, any framework middleware). One line each here; full detail and every parameter in the Wiki.

| Area | What you get | Full reference |
|---|---|---|
| Decorators | `@runtime_narrative_story` / `@runtime_narrative_stage` — wrap functions without restructuring call sites | [WIKI §7](WIKI.md#7-decorators) |
| Auto-instrumentation | `@narrative_class`, `@no_stage`, `instrument_module()`, `auto_instrument()` — instrument classes/modules with zero call-site changes | [WIKI §8](WIKI.md#8-auto-instrumentation) |
| Failure diagnostics | Lean/rich modes, production traceback caps, secret redaction, `FailureDiagnosticsConfig` | [WIKI §9](WIKI.md#9-failure-diagnostics) |
| Failure analyzers | `OllamaFailureAnalyzer`, `LLMFailureAnalyzer`, `AnthropicFailureAnalyzer`, `DeduplicatingAnalyzer`, `background_analysis=True` | [WIKI §9](WIKI.md#9-failure-diagnostics), [§16](WIKI.md#16-background-analysis) |
| Renderers | `ConsoleRenderer`, `JsonRenderer`/`RotatingJsonRenderer`, `HtmlReportRenderer`, `SqliteStoryRenderer`, `OtelRenderer`/`OtelLogRenderer`/`OtelMetricsRenderer`, `PrometheusRenderer`, `AlertRoutingRenderer`, `FilteredRenderer` | [WIKI §10](WIKI.md#10-renderers) |
| Framework integrations | FastAPI/Starlette middleware, Django ASGI/WSGI middleware, Celery task base class, gRPC interceptors | [WIKI §11](WIKI.md#11-framework-integrations) |
| Async task groups | `NarrativeTaskGroup` — concurrent `asyncio` tasks under one shared story | [WIKI §12](WIKI.md#12-async-task-groups) |
| Persistence & CLI | `SqliteStoryRenderer` + `runtime-narrative failures` / `runtime-narrative story <id>` | [WIKI §13](WIKI.md#13-sqlite-persistence-and-cli) |
| Testing | `StoryRecorder` — dual sync/async assertion API, no output produced | [WIKI §14](WIKI.md#14-testing-with-storyrecorder) |
| `dry_run` mode | Suppress stage-body exceptions; verify instrumentation wiring with no side effects | [WIKI §15](WIKI.md#15-dry_run-mode) |
| Custom renderers/analyzers | Any `handle(event)` object is a renderer; any `analyze_failure(...)` object is an analyzer | [WIKI §17](WIKI.md#17-custom-renderers), [§18](WIKI.md#18-custom-failure-analyzers) |
| Utilities | `has_active_story()`, `stage(optional=True)` for library code that may run with or without a story | [WIKI §6](WIKI.md#6-stage--stage-context-managers) |
| `StoryRuntime.record_failure()` | Record a failure in saga/rollback flows without owning exception propagation | [WIKI §5](WIKI.md#5-story--the-story-context-manager) |
| Event schema | All seven event dataclasses and their fields | [WIKI §20](WIKI.md#20-event-reference) |

---

## Examples

Every script under `examples/` is runnable as-is: `uv run python examples/<name>.py`.

**Core**
| Script | Demonstrates |
|---|---|
| `success.py` | Minimal `story()`/`stage()` API, no decorators, a success path |
| `basic.py` | `@runtime_narrative_story`/`@runtime_narrative_stage` decorators, a failure path |
| `basic_ollama.py` | Same failure path with `OllamaFailureAnalyzer` attached |

**Sub-stories and logging (newest features)**
| Script | Demonstrates |
|---|---|
| `substory_db_call.py` | Nested `story()` auto-linking as a sub-story (API call → DB call) |
| `logging_bridge.py` | `NarrativeLogHandler` folding `logging` calls into the story pipeline |
| `structured_log_routing.py` | `extra=` fields, `level_icons`, and `FilteredRenderer` per-story-family routing |

**Auto-instrumentation**
| Script | Demonstrates |
|---|---|
| `narrative_class.py` | `@narrative_class` and `@no_stage` |
| `instrument_module.py` | `instrument_module()` on an existing module |
| `auto_instrument.py` | `auto_instrument()` import-hook, zero call-site changes |

**Failure diagnostics and analysis**
| Script | Demonstrates |
|---|---|
| `diagnostics_config.py` | `FailureDiagnosticsConfig` — rich mode, redaction, production caps |
| `background_analysis.py` | `background_analysis=True` — non-blocking LLM analysis |
| `anthropic_analyzer.py` | `AnthropicFailureAnalyzer` + `DeduplicatingAnalyzer` |

**Renderers and observability**
| Script | Demonstrates |
|---|---|
| `html_report.py` | `HtmlReportRenderer` — self-contained HTML report |
| `sqlite_persistence.py` | `SqliteStoryRenderer` + the `runtime-narrative` CLI |
| `otel_tracing.py` | `OtelRenderer`, `OtelLogRenderer`, `OtelMetricsRenderer` |
| `alert_routing.py` | `AlertRoutingRenderer` — async webhook fan-out |
| `colorful_errors_and_emojis.py` | `ConsoleRenderer`'s built-in color + `level_icons` emoji across log levels and a failure |

**Framework integrations and concurrency**
| Script | Demonstrates |
|---|---|
| `middleware_skip_if.py` | `RuntimeNarrativeMiddleware(skip_if=...)` for FastAPI/Starlette |
| `task_group.py` | `NarrativeTaskGroup` — concurrent asyncio tasks under one story |
| `fastapi_app/` | Full FastAPI demo app (`uv run python -m examples.fastapi_app.run`) |

**Testing and lifecycle utilities**
| Script | Demonstrates |
|---|---|
| `story_recorder.py` | `StoryRecorder` test assertion API |
| `dry_run_mode.py` | `dry_run=True` — verify wiring with no side effects |
| `optional_stage.py` | `has_active_story()` and `stage(optional=True)` |
| `saga_record_failure.py` | `StoryRuntime.record_failure()` in a saga/rollback flow |
| `stage_story_name.py` | `story_name` on `StageStarted`/`StageCompleted` |

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

Python 3.9+. Async task groups (`NarrativeTaskGroup`) require no additional dependencies. Type hints use `from __future__ import annotations` throughout for compatibility with older typing syntax.

---

## More

- **[WIKI.md](WIKI.md)** — complete reference: every parameter, every renderer, every event field.
- **[CHANGELOG.md](CHANGELOG.md)** — what changed in each release.
- **[ROADMAP.md](ROADMAP.md)** — what's shipped and what's next.
