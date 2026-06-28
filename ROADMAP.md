# Roadmap

This document tracks what comes next for `runtime-narrative`, grounded in the core vision: **convert any Python project into a traceable story, with minimal logging on success and surgical, LLM-powered diagnostics on failure**.

Items within each phase are roughly priority-ordered. Phases are sequential in intent but may overlap in practice.

---

## What's already shipped

- `story()` / `stage()` — dual sync/async context managers
- `ConsoleRenderer` — rich terminal story output for local development
- `JsonRenderer` / `RotatingJsonRenderer` — one structured JSON object per event, rotating file support
- Lean/rich failure diagnostics — local variable capture, source snippet, frame classification, secret redaction, production traceback caps
- `OllamaFailureAnalyzer` + `LLMFailureAnalyzer` — sync and async, background analysis mode
- `RuntimeNarrativeMiddleware` — FastAPI/Starlette, auto-wraps every request in a story
- `@runtime_narrative_story` / `@runtime_narrative_stage` decorators
- Exception chain traversal, exact-cause inference
- **Auto-instrumentation** (Phase 1)
  - `@narrative_class` — class decorator: every public instance method becomes a stage
  - `@no_stage` — opt-out marker for individual methods/functions
  - `instrument_module(module)` — instruments all public callables in an existing module
  - `auto_instrument(app_roots=...)` — `sys.meta_path` import hook; zero-config instrumentation of all app modules on import

---

## Phase 2 — OpenTelemetry integration

> **Goal:** For server deployments, `runtime-narrative` should produce output compatible with OpenTelemetry standards so it plugs into existing observability stacks (Datadog, Grafana, Honeycomb, Jaeger, etc.) without any adapter layer.

### 2.1 OTel trace renderer

An `OtelRenderer` that maps the `runtime-narrative` event model to OTel spans:

| runtime-narrative event | OTel concept |
|---|---|
| `StoryStarted` → `StoryCompleted` | Root span (story name as span name) |
| `StageStarted` → `StageCompleted` | Child span (stage name as span name) |
| `FailureOccurred` | Span status `ERROR` + structured log on the span |
| `LLMAnalysisReady` | Span event with LLM suggestion as attribute |

Emits via the OTel Python SDK (`opentelemetry-sdk`) so any configured exporter (OTLP, Jaeger, Zipkin) works automatically.

### 2.2 OTel log renderer

A companion `OtelLogRenderer` that emits structured log records via the OTel Logs API. `FailureOccurred` fields map directly to log attributes — the same fields already in `JsonRenderer` but routed through the OTel log SDK instead of stdout.

### 2.3 Trace context propagation

When `RuntimeNarrativeMiddleware` creates a story per request, it should extract and attach any incoming W3C `traceparent` / `tracestate` headers so the story spans are children of the upstream trace, not orphaned roots.

### 2.4 Metrics

Emit OTel metrics automatically:
- `narrative.stage.duration` histogram (per story name + stage name)
- `narrative.story.failure_rate` counter
- `narrative.llm.analysis_latency` histogram (when an analyzer is configured)

---

## Phase 3 — LLM layer improvements

> **Goal:** Make the LLM suggestion more reliable, more actionable, and available from more providers — while keeping the no-code-rewrite contract.

### 3.1 Structured LLM output

Replace the free-text prompt response with a JSON schema response (using the model's structured output / function-calling mode where available). Guarantees the four sections (`Exact Why`, `Evidence`, `Targeted Fix`, `What to Change`) always parse correctly — no regex in the renderer.

### 3.2 Provider abstraction

A unified `FailureAnalyzer` base interface that ships with adapters for:

- Anthropic Claude (`claude-haiku-4-5` by default — fast, cheap, good at reasoning)
- OpenAI
- Any OpenAI-compatible endpoint (already exists as `LLMFailureAnalyzer`)
- Ollama (already exists)
- Bring-your-own (already works via duck typing)

### 3.3 Context budget management

Large tracebacks can exceed model context windows. Add automatic context compression: trim redundant frames, summarize library-only stack segments, and prefer the `compressed_stack_summary` (already computed) over raw traceback when the payload approaches the model's limit.

### 3.4 Failure deduplication

Cache LLM suggestions by a content hash of `(error_type, source_line, exception_chain)`. Identical failures in the same process lifetime reuse the cached suggestion without hitting the model again.

---

## Phase 4 — Broader framework integrations

> **Goal:** Let the library work without modification in the most common Python server and worker runtimes.

### 4.1 Django middleware

`RuntimeNarrativeMiddleware` equivalent for Django's WSGI/ASGI middleware stack. Each request becomes a story; Django's URL resolver provides the story name.

### 4.2 Celery integration

A Celery signal listener that wraps each task execution in a story. Task name becomes the story name; the task body's stages are tracked normally. Failure reports include the Celery task ID and queue name.

### 4.3 `asyncio.TaskGroup` / `anyio` support

A context manager that wraps a group of concurrent tasks so their stages are tracked as parallel branches of a single parent story, with the failure report identifying which branch failed.

### 4.4 gRPC interceptor

Server-side interceptor that wraps each RPC in a story, analogous to `RuntimeNarrativeMiddleware`.

---

## Phase 5 — Developer experience

> **Goal:** Make the library easy to adopt, debug, and trust — especially for teams onboarding it into an existing codebase.

### 5.1 Test utilities

An assertion API for unit and integration tests:

```python
from runtime_narrative.testing import StoryRecorder

with StoryRecorder() as recorder:
    my_function()

recorder.assert_stages_completed(["Load CSV", "Validate Data", "Insert Records"])
recorder.assert_no_failure()
recorder.assert_stage_failed("Insert Records", error_type="ValueError")
```

### 5.2 Story HTML report

After a story completes (or after a batch run), generate a self-contained HTML timeline showing every stage, its duration, and the failure detail if any. Useful for sharing post-mortems or pipeline run summaries.

### 5.3 `dry_run` mode

Run a story without executing any stage body — just emit `StageStarted` / `StageCompleted` events in sequence. Useful for verifying that instrumentation is wired up correctly before running an expensive pipeline.

### 5.4 Story timeline in failure context

The `stage_timeline` field already records the last 5 stages. Extend it to include the full ordered list of stages with statuses, so the LLM and human reader both see the complete execution path, not just a tail.

---

## Phase 6 — Production-grade persistence and alerting

> **Goal:** Enable post-mortem analysis, failure trend tracking, and routing — without requiring external APM tooling.

### 6.1 Story persistence renderer

A renderer that writes completed stories (all events) to a SQLite or PostgreSQL table. Enables querying failure history, stage duration trends, and LLM suggestion recall.

### 6.2 CLI for story analysis

```bash
# Replay the last N failures from the store
runtime-narrative failures --last 10

# Show the full story for a given story_id
runtime-narrative story <story_id>

# List all stories that failed at a specific stage
runtime-narrative failures --stage "Insert Records"
```

### 6.3 Alert routing renderer

A renderer that dispatches `FailureOccurred` to configured destinations (Slack webhook, PagerDuty, email) with the LLM suggestion included. Supports routing rules (e.g., only alert on `production` environment or specific story names).

### 6.4 Redaction configuration

Allow users to define custom redaction rules beyond the built-in keyword list — regex patterns, field path expressions, or a callback — to satisfy stricter data handling requirements.

---

## What will not be built

- **Code generation or automated patching.** The library tells you *what* to fix and *why*. Applying the fix is always a human decision.
- **A hosted service or cloud backend.** Everything runs in-process or in the user's own infrastructure.
- **Replacing existing logging frameworks.** `runtime-narrative` works alongside `logging`, `structlog`, or any other logger. It is not a drop-in replacement.


---

## Changelog

### 0.3.0

**New features — Phase 1: Auto-instrumentation**

- `@narrative_class` — class decorator that wraps every public instance method as a stage. Stage name is `ClassName.method_name`. Skips names starting with `_`, `@no_stage`-marked methods, `@staticmethod`, `@classmethod`, `@property`, and inherited methods.
- `@no_stage` — opt-out marker. Apply to any method or function to exclude it from `@narrative_class` and `instrument_module`.
- `instrument_module(module)` — instruments all public callables defined in an existing module in-place. Classes get `@narrative_class`; top-level functions are wrapped directly. Imported symbols (different `__module__`) are not touched.
- `auto_instrument(app_roots=...)` — registers a `sys.meta_path` import hook that instruments every app module on import. Only modules whose source path starts with `app_roots` (default: `cwd`) are instrumented — stdlib and installed packages are unaffected. Returns the finder for later removal.

### 0.2.0

**Bug fixes**

- `ConsoleRenderer` no longer crashes with `UnicodeEncodeError` on Windows cp1252 terminals. Encoding is detected at init time; non-UTF-8 terminals automatically use ASCII glyphs (`>`, `[ok]`, `[FAIL]`). A secondary `try/except` in `_secho` catches any remaining encoding errors. Also fixed a copy-paste bug where `StoryStarted` was logged as "Stage started" instead of "Story started".
- `emit()` and `emit_async()` now isolate renderer failures. A renderer that raises any exception prints a warning to `stderr` and the next renderer continues — a crashed renderer can no longer return HTTP 500 or swallow the application exception.
- `JsonRenderer` now handles `LLMAnalysisReady` events. Background analysis results were previously silently dropped when using structured-log output.
- Progress percent is now accurate when stages are declared upfront. `StoryRuntime.set_total_stages(n)` and the `story(total_stages=n)` kwarg let the library know the expected stage count, making `progress_percent` meaningful at every stage boundary rather than always reporting 0% until `StoryCompleted`.

**New features**

- `RuntimeNarrativeMiddleware` auto-selects its renderer: `ConsoleRenderer` on a real TTY (local dev server), `JsonRenderer` otherwise (Docker, CI, any non-interactive environment). Passing `renderers=[...]` explicitly still overrides.
- `async with stage()` now dispatches through `emit_async()`, so async renderers receive stage events (awaited), not just story and failure boundaries.
- `FailureDiagnosticsConfig` validates `failure_diagnostics` at construction and raises `ValueError` immediately on invalid values instead of silently falling back to `"lean"`.
- Stage timeline in failure reports is now the full ordered history. The previous silent 5-stage truncation is removed. Console label updated from "Recent stages:" to "Stage timeline:".
- Custom redaction: `FailureDiagnosticsConfig(redact_extra=("internal_key", "org_id"))`, `story(redact_extra=...)`, and `RuntimeNarrativeMiddleware(redact_extra=...)` extend the built-in redaction keyword list for local-variable capture and nested dict serialization in rich mode.
- `RotatingJsonRenderer(path, max_bytes=10_485_760, backup_count=5)` ships as a first-class renderer. Uses standard `path.1` / `path.2` rotation semantics — no external dependencies.
- `StoryRuntime` is now exported from the top-level package for type-hinting.

---