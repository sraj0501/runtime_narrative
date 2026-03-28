# Runtime Narrative

Model your application's execution as **human-readable stories** instead of scattered log lines.

When something fails, you get a **structured** report: primary location (preferring your app code over library frames), optional source context, stack summary, and—when enabled—serialized locals. Tracebacks can be **truncated** in production instead of dumping pages of framework frames.

Example (lean mode, with snippet):

```
❌ Failure detected
Story:    Create Customer
Stage:    Validate Input
Error:    ValueError - invalid email
Location: handlers.py:24 (validate_customer)
Code:     if "@" not in payload.email:
Diagnostics: lean (primary: innermost_app)
Context:
  >   24 |     if "@" not in payload.email:
Stack summary: 1 app frame(s), …
Progress: 33% (1 / 3 stages completed)
Recent stages: Validate Input=failed (0.001s)
```

## Installation

```bash
# Core only (zero dependencies)
pip install runtime-narrative

# With colored console output
pip install "runtime-narrative[console]"

# With FastAPI middleware
pip install "runtime-narrative[fastapi]"

# Everything
pip install "runtime-narrative[all]"
```

## Quick start

```python
from runtime_narrative import story, stage

with story("Import Customers"):
    with stage("Load CSV"):
        load_file()

    with stage("Validate Data"):
        validate()

    with stage("Insert Records"):
        insert()
```

Async code uses identical syntax with `async with`:

```python
async with story("Import Customers"):
    async with stage("Load CSV"):
        await load_file()

    async with stage("Validate Data"):
        await validate()

    async with stage("Insert Records"):
        await insert()
```

## Failure diagnostics (lean vs rich)

Diagnostics are **not** tied to Python logging levels. You control depth with **environment** and an explicit **mode**:

| Mode | What you get |
|------|----------------|
| **lean** (default) | Primary frame, code line, optional file snippet, structured `stack_frames`, compressed stack summary; traceback text may be **capped** in production. |
| **rich** | Everything in lean, plus **serialized locals** for the primary frame (and one caller), with size limits and **redaction** of sensitive dict keys (e.g. `password`, `token`). |

**Environment variables** (optional; overridden by explicit `story(...)` / middleware kwargs):

| Variable | Purpose |
|----------|---------|
| `RUNTIME_NARRATIVE_ENV` | `production`, `staging`, or `development` (default `development`). In **production**, `rich` is forced to **lean** unless you set the flag below. |
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean` or `rich` (default `lean`). |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | Set to `1` or `true` to allow **rich** when `RUNTIME_NARRATIVE_ENV=production`. |

**Programmatic configuration:**

```python
from runtime_narrative import story, FailureDiagnosticsConfig

# Per-story overrides (merged with env defaults)
async with story(
    "Import Customers",
    runtime_environment="development",
    failure_diagnostics="rich",
    app_roots=("/path/to/my/app",),  # optional; default treats cwd as app code
):
    ...

# Or pass a fully built config
cfg = FailureDiagnosticsConfig(failure_diagnostics="rich", app_roots=("/app",))
async with story("Import Customers", diagnostics_config=cfg):
    ...
```

Export **`effective_diagnostics_mode(config)`** if you need to mirror the library’s production safeguard in your own code.

## FastAPI — middleware (recommended)

Add middleware once and every request gets a story automatically.
Route handlers only need to declare stages:

```python
from runtime_narrative import RuntimeNarrativeMiddleware, stage

app.add_middleware(
    RuntimeNarrativeMiddleware,
    # Optional: same diagnostic kwargs as story()
    # failure_diagnostics="rich",
    # runtime_environment="production",
)

@app.post("/customers")
async def create_customer(payload: CustomerIn):
    async with stage("Validate Input"):
        ...
    async with stage("Insert Into Database"):
        ...
    async with stage("Build Response"):
        return {"ok": True}
```

Each request runs inside **`async with story(...)`**, so async renderers (and `emit_async`) are used end-to-end for that story.

## FastAPI — decorator style

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@app.post("/customers")
@runtime_narrative_story("Create Customer")
async def create_customer(payload: CustomerIn):
    return await _save(payload)

@runtime_narrative_stage("Save to Database")
async def _save(payload):
    ...
```

The decorators detect `async def` automatically and use `async with` internally.

Optional `story()` arguments are forwarded from **`@runtime_narrative_story`**, including `failure_diagnostics`, `runtime_environment`, `allow_rich_in_production`, `app_roots`, `diagnostics_config`, `background_analysis`, `renderers`, and `failure_analyzer`.

## Structured JSON output

Pipe one JSON object per lifecycle event to stdout, a file, or any stream:

```python
from runtime_narrative import RuntimeNarrativeMiddleware, JsonRenderer

app.add_middleware(RuntimeNarrativeMiddleware, renderers=[JsonRenderer()])
```

Output (one line per event):

```json
{"event": "StoryStarted", "story_id": "...", "story_name": "POST /customers", "timestamp": "..."}
{"event": "StageStarted", "story_id": "...", "stage_name": "Validate Input", "timestamp": "..."}
{"event": "StageCompleted", "story_id": "...", "stage_name": "Validate Input", "duration_seconds": 0.001, "timestamp": "..."}
```

On failure, `FailureOccurred` also includes structured diagnostics, for example:

- `diagnostics_mode`, `primary_frame_reason`, `stack_frames`, `source_snippet`, `compressed_stack_summary`, `hidden_frame_count`, `traceback_truncated`
- `locals_by_frame` and `redaction_removed_keys` when mode is **rich**
- `traceback_text` (may be truncated when `traceback_truncated` is true)

```json
{"event": "StoryCompleted", "story_id": "...", "success": true, "progress": {"percent": 100, ...}, "timestamp": "..."}
```

Write to a file instead of stdout:

```python
JsonRenderer(output=open("runtime_narrative.log", "a"))
```

## LLM failure analysis

Plug in any LLM backend — model name and endpoint are always required (no defaults).

**OpenAI-compatible backends** (vLLM, llama.cpp `--server`, LM Studio, Ollama OpenAI mode):

```python
from runtime_narrative import LLMFailureAnalyzer, story

analyzer = LLMFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:8000/v1/chat/completions",
)

with story("Process Orders", failure_analyzer=analyzer):
    ...
```

**Ollama native API:**

```python
from runtime_narrative import OllamaFailureAnalyzer, story

analyzer = OllamaFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:11434/api/generate",
)

with story("Process Orders", failure_analyzer=analyzer):
    ...
```

Falls back silently if the endpoint is unavailable.

Both analyzers are async-safe. In an `async with story(...)`, the HTTP call runs via
`asyncio.to_thread` so it never blocks the event loop.

Analyzers receive a **`FailureSummary`** built from the same **primary-frame** logic as
`FailureOccurred`; in **production**, `traceback_text` on that summary may already be
truncated (see failure diagnostics above). **`locals_by_frame` is not sent to the LLM** by default.

**Background (decoupled) analysis**

Pass `background_analysis=True` to emit `FailureOccurred` immediately and run the
LLM call as a background task. When the analysis is ready, a `LLMAnalysisReady` event
is emitted and the console renderer prints the debug box after the story has already
completed. Useful in latency-sensitive async services:

```python
async with story("Process Orders", failure_analyzer=analyzer, background_analysis=True):
    ...
```

## Custom renderer

Implement a `handle` method to receive all lifecycle events. Both sync and async
renderers are supported:

```python
# Sync renderer
class MyRenderer:
    def handle(self, event):
        print(event.__class__.__name__, event.__dict__)

# Async renderer
class MyAsyncRenderer:
    async def handle(self, event):
        await db.insert(event.__class__.__name__, event.__dict__)

with story("My Story", renderers=[MyRenderer()]):
    ...

async with story("My Story", renderers=[MyAsyncRenderer()]):
    ...
```

Events: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`,
`StoryCompleted`, `LLMAnalysisReady` (only when `background_analysis=True`).

`FailureOccurred` carries both the original location fields and the extended diagnostics fields above; custom renderers should use `getattr(event, "diagnostics_mode", "lean")` if they must stay compatible with older library versions.

## Environment variables

All variables are optional. Copy `.env.example` to `.env` as a starting point:

```bash
cp .env.example .env
```

| Variable | Purpose | Default |
|----------|---------|---------|
| `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS` | `lean` or `rich` locals capture | `lean` |
| `RUNTIME_NARRATIVE_ENV` | `production` forces lean diagnostics | unset |
| `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION` | Set `1` to override production guard | `0` |
| `RUNTIME_NARRATIVE_MODEL` | LLM model name — enables failure analysis when set | unset |
| `RUNTIME_NARRATIVE_ENDPOINT` | LLM generate endpoint | `http://127.0.0.1:11434/api/generate` |
| `RUNTIME_NARRATIVE_JSON` | Set `1` to use `JsonRenderer` instead of console | `0` |
| `RUNTIME_NARRATIVE_HOST` | FastAPI example host | `127.0.0.1` |
| `RUNTIME_NARRATIVE_PORT` | FastAPI example port | `8000` |
| `RUNTIME_NARRATIVE_RELOAD` | FastAPI example auto-reload | `1` |

None of these are required just to import or use the library.

## Running tests

```bash
uv sync --group dev
uv run pytest tests/ -v
```

## License

MIT
