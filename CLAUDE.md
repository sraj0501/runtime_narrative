# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (includes typer, uvicorn, fastapi, pydantic for examples)
uv sync --group dev

# Copy env var template (all vars are optional)
cp .env.example .env

# Run examples
uv run python examples/basic.py
uv run python examples/success.py
uv run python examples/basic_ollama.py  # requires RUNTIME_NARRATIVE_MODEL

# Run FastAPI demo
uv run python -m examples.fastapi_app.run
# With Ollama failure analysis:
RUNTIME_NARRATIVE_MODEL=llama3 uv run python -m examples.fastapi_app.run
# With a custom endpoint (vLLM, llama.cpp, etc.):
RUNTIME_NARRATIVE_MODEL=llama3 RUNTIME_NARRATIVE_ENDPOINT=http://localhost:8000/api/generate uv run python -m examples.fastapi_app.run

# Rich failure diagnostics (locals, etc.) via env
RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS=rich uv run python examples/basic.py

# Tests (dev dependency group)
uv sync --group dev
uv run pytest tests/ -v
```

## Architecture

The library (`runtime_narrative/`) models execution as **stories** composed of **stages**, emitting lifecycle events that renderers consume.

### Core execution flow

1. `story(name)` — dual sync/async context manager (`with` / `async with`) that creates a `StoryRuntime`, sets it on `current_story` (a `ContextVar`), and emits `StoryStarted`/`StoryCompleted` events. On exception, builds enriched failure data (see **Diagnostics** below), optionally runs failure analysis, and emits `FailureOccurred` before `StoryCompleted`.
2. `stage(name)` — dual sync/async context manager that must be nested inside a `story`. Registers a `StageRecord` on the `StoryRuntime`, manages a `current_stage_stack` ContextVar for nesting, and emits `StageStarted`/`StageCompleted` via **`emit()`** (sync). Nested `stage()` inside `async with story` does not use `emit_async`; async renderers’ `handle` coroutines are therefore **not** awaited for stage events (use a sync renderer for full stage coverage, or rely on async emit for story/failure-only paths).
3. **Context** (`context.py`) — two `ContextVar`s: `current_story` (holds the active `StoryRuntime`) and `current_stage_stack` (holds a list of nested `StageRecord`s). This enables propagation across sync/async without parameter threading.
4. **Events** (`events.py`) — plain dataclasses: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`, `LLMAnalysisReady`. `FailureOccurred` includes diagnostics fields (`diagnostics_mode`, `primary_frame_reason`, `stack_frames`, `source_snippet`, `compressed_stack_summary`, `hidden_frame_count`, `traceback_truncated`, optional `locals_by_frame`, `redaction_removed_keys`). `StoryRuntime.emit()` dispatches synchronously; `StoryRuntime.emit_async()` dispatches asynchronously, awaiting renderers whose `handle` is a coroutine function.
5. **Failure** (`failure.py`) — `summarize_exception()` still produces a minimal `FailureSummary` from a traceback leaf frame. The **story** path uses **`build_enriched_failure()`** in `diagnostics.py`, which picks a **primary** frame (innermost **app** code by default), optional file snippet, structured stack, traceback caps in production, and **rich** locals when enabled.
6. **Diagnostics** (`diagnostics.py`) — `FailureDiagnosticsConfig` (with `from_env()` / `merge()`), `effective_diagnostics_mode()` (forces **lean** in production unless `allow_rich_in_production`), `build_enriched_failure()` → `EnrichedFailure` → `_make_failure_occurred()` in `story.py`. Env: `RUNTIME_NARRATIVE_ENV`, `RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS`, `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION`. Story kwargs: `diagnostics_config`, `runtime_environment`, `failure_diagnostics`, `allow_rich_in_production`, `app_roots`.
7. **Renderers** (`runtime_narrative/renderer/console.py`) — `ConsoleRenderer` handles all six event types. Uses `typer.secho` for color if `typer` is available, falls back to `print`. Renders LLM analysis in a terminal box via `_render_box`. Prints diagnostics snippet, stack summary, and rich locals when present. Supports both sync `handle()` and (by duck-typing in `emit_async`) async `handle()`. **`json_renderer.py`** emits extended `FailureOccurred` fields including `traceback_text` when present.
8. **Analyzers** (`runtime_narrative/analyzers/ollama.py`) — `LLMFailureAnalyzer` (OpenAI-compatible) and `OllamaFailureAnalyzer` (Ollama native). Both expose `analyze_failure()` (sync, uses `urllib`) and `analyze_failure_async()` (async, runs the sync version via `asyncio.to_thread`). They receive `FailureSummary` from **`EnrichedFailure.summary`** (primary frame + possibly truncated traceback). `story.__aexit__` prefers `analyze_failure_async` when available; falls back to `asyncio.to_thread(analyze_failure)` for third-party analyzers that only provide a sync method.
9. **Background analysis** — `story(..., background_analysis=True)` emits `FailureOccurred` (with `llm_analysis=None`) immediately, then schedules `_run_background_analysis()` as an `asyncio.Task`. When the task completes it emits `LLMAnalysisReady`. The initial `FailureOccurred` includes the same diagnostics fields as the synchronous-analysis path.
10. **Async story exit** — `story.__aexit__` (async) runs `build_enriched_failure` via **`asyncio.to_thread`** so traceback walking and optional file reads do not block the event loop.
11. **Middleware** (`middleware.py`) — `RuntimeNarrativeMiddleware` wraps each request in **`async with story(...)`** (not sync `with`), forwarding `renderers`, `failure_analyzer`, and diagnostic kwargs. Ensures async renderers are awaited for request-scoped stories.
12. **Decorators** (`decorators.py`) — `@runtime_narrative_story` and `@runtime_narrative_stage` wrap sync functions with `with` and async functions with `async with`. `@runtime_narrative_story` forwards diagnostic and `background_analysis` kwargs into `story()`.

### Key design constraint

`stage()` raises `RuntimeError` if called outside an active `story()`. The story context is never implicit — it must always be established first.

### Adding a custom renderer

Implement a class with `handle(self, event: object) -> None` (sync) or `async def handle(self, event: object) -> None` (async) and pass it to `story(..., renderers=[MyRenderer()])`. No base class or registration required. Async renderers are only awaited when using `async with story(...)` via `emit_async()` (including per-request stories created by `RuntimeNarrativeMiddleware`).
