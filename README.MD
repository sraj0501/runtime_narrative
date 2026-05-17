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
pip install "runtime-narrative[console]"   # colored terminal output (typer)
pip install "runtime-narrative[fastapi]"   # FastAPI/Starlette middleware
pip install "runtime-narrative[all]"       # everything
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

```python
from runtime_narrative import LLMFailureAnalyzer

analyzer = LLMFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:8000/v1/chat/completions",
)
```

Both fall back silently if the endpoint is unreachable — your application's exception still propagates normally.

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
):
    ...

# Or pass a fully built config
cfg = FailureDiagnosticsConfig(failure_diagnostics="rich", app_roots=("/app",))
async with story("Import Customers", diagnostics_config=cfg):
    ...
```

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

## Custom renderer

Any object with a `handle(event)` method is a valid renderer. Async renderers (`async def handle`) are awaited automatically inside `async with story(...)`:

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

Events you will receive: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`, `LLMAnalysisReady` (only when `background_analysis=True`).

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

---

## Environment variables

| Variable | Values | Default | Effect |
|---|---|---|---|
| `RUNTIME_NARRATIVE_ENV` | `development`, `production` | `development` | Production caps traceback length and forces lean mode |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean`, `rich` | `lean` | `rich` captures local variables at the failing frames |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | `1`, `true` | off | Bypass production safeguard for rich diagnostics |

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
