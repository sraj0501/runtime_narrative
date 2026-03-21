# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run examples
uv run python examples/basic.py
uv run python examples/success.py
uv run python examples/basic_ollama.py

# Run FastAPI demo
uv run python -m examples.fastapi_app.run
# With Ollama failure analysis:
RUNTIME_NARRATIVE_MODEL=llama3 uv run python -m examples.fastapi_app.run
# With a custom endpoint (vLLM, llama.cpp, etc.):
RUNTIME_NARRATIVE_MODEL=llama3 RUNTIME_NARRATIVE_ENDPOINT=http://localhost:8000/api/generate uv run python -m examples.fastapi_app.run
```

No test suite exists yet.

## Architecture

The library (`runtime_narrative/`) models execution as **stories** composed of **stages**, emitting lifecycle events that renderers consume.

### Core execution flow

1. `story(name)` — context manager that creates a `StoryRuntime`, sets it on `current_story` (a `ContextVar`), and emits `StoryStarted`/`StoryCompleted` events. On exception, calls `summarize_exception()` and emits `FailureOccurred` before `StoryCompleted`.
2. `stage(name)` — context manager that must be nested inside a `story`. Registers a `StageRecord` on the `StoryRuntime`, manages a `current_stage_stack` ContextVar for nesting, and emits `StageStarted`/`StageCompleted` events.
3. **Context** (`context.py`) — two `ContextVar`s: `current_story` (holds the active `StoryRuntime`) and `current_stage_stack` (holds a list of nested `StageRecord`s). This enables propagation across sync/async without parameter threading.
4. **Events** (`events.py`) — plain dataclasses: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`. `StoryRuntime.emit()` dispatches to all registered renderers via `renderer.handle(event)`.
5. **Failure** (`failure.py`) — `summarize_exception()` inspects the traceback to find the root-cause frame, extracting filename/lineno/function/source_line and building `exception_chain` and `exact_cause` strings.
6. **Renderers** (`runtime_narrative/renderer/console.py`) — `ConsoleRenderer` handles all five event types. Uses `typer.secho` for color if `typer` is available, falls back to `print`. Renders LLM analysis in a terminal box via `_render_box`.
7. **Analyzers** (`runtime_narrative/analyzers/ollama.py`) — optional `OllamaFailureAnalyzer` calls a local Ollama model to produce LLM debug text, attached to `FailureOccurred.llm_analysis`.
8. **Decorators** (`decorators.py`) — `@runtime_narrative_story` and `@runtime_narrative_stage` wrap sync/async functions in the respective context managers.

### Key design constraint

`stage()` raises `RuntimeError` if called outside an active `story()`. The story context is never implicit — it must always be established first.

### Adding a custom renderer

Implement a class with `handle(self, event: object) -> None` and dispatch to `story(..., renderers=[MyRenderer()])`. No base class or registration required.
