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
- **Auto-instrumentation Phase 1** (`v0.3.0`)
  - `@narrative_class` — class decorator: every public instance method becomes a stage
  - `@no_stage` — opt-out marker for individual methods/functions
  - `instrument_module(module)` — instruments all public callables in an existing module
  - `auto_instrument(app_roots=...)` — `sys.meta_path` import hook; zero-config instrumentation of all app modules on import
- **Auto-instrumentation Phase 2** (`v0.4.0`)
  - `@narrative_stage(name=None)` — per-method/function stage decorator with custom name; prevents double-wrapping inside `@narrative_class`
  - `@narrative_class(instrument_classmethods=True)` — opt-in instrumentation of `@classmethod` methods
  - `@narrative_class(instrument_staticmethods=True)` — opt-in instrumentation of `@staticmethod` methods
- **Observability renderers** (`v0.5.0`)
  - `OtelRenderer` — maps narrative events to OpenTelemetry spans; `exclude_stages` and `min_duration_ms` filtering params
  - `PrometheusRenderer` — four metrics: story/stage duration histograms, failure and total counters
  - `StageStarted` / `StageCompleted` now carry `stage_index` and `parent_stage_name` for nested stage tracking
- **Phase 2 OTel integration** (`v0.6.0`)
  - `OtelLogRenderer` — all 6 lifecycle events as OTel log records (INFO/DEBUG/ERROR); correlates trace/span IDs from ambient context
  - `OtelMetricsRenderer` — 4 OTel instruments: `narrative.stage.duration`, `narrative.story.duration`, `narrative.story.failures`, `narrative.llm.analysis_latency`
  - `RuntimeNarrativeMiddleware` extracts W3C `traceparent`/`tracestate` headers; story spans become children of upstream traces

---

## Phase 2 — OpenTelemetry integration

> **Goal:** For server deployments, `runtime-narrative` should produce output compatible with OpenTelemetry standards so it plugs into existing observability stacks (Datadog, Grafana, Honeycomb, Jaeger, etc.) without any adapter layer.

### 2.1 OTel trace renderer ✅ shipped in v0.5.0

`OtelRenderer` maps narrative events to OTel spans with `exclude_stages` and `min_duration_ms` filtering.

### 2.2 OTel log renderer ✅ shipped in v0.6.0

`OtelLogRenderer` emits all 6 lifecycle events as OTel log records. Failures are `ERROR` severity with full diagnostics attributes; lifecycle events are `INFO`/`DEBUG`. Correlates `trace_id`/`span_id` from the ambient OTel context.

### 2.3 Trace context propagation ✅ shipped in v0.6.0

`RuntimeNarrativeMiddleware` extracts incoming W3C `traceparent`/`tracestate` headers via `opentelemetry.propagate.extract()` before entering each request's story. Story spans become children of the upstream trace. `propagate_trace_context=False` to opt out.

### 2.4 OTel metrics ✅ shipped in v0.6.0

`OtelMetricsRenderer` emits four OTel instruments: `narrative.stage.duration`, `narrative.story.duration`, `narrative.story.failures`, `narrative.llm.analysis_latency`.

---

## Phase 3 — LLM layer improvements ✅ shipped in v0.7.0

> **Goal:** Make the LLM suggestion more reliable, more actionable, and available from more providers — while keeping the no-code-rewrite contract.

### 3.1 Structured LLM output ✅ shipped in v0.7.0

`LLMFailureAnalyzer` and `OllamaFailureAnalyzer` now request a JSON object (`exact_why`, `evidence`, `targeted_fix`, `code_changes`) instead of free-text. Responses are parsed into guaranteed `## Header\ncontent` sections; falls back to raw text if the model returns non-JSON.

### 3.2 Provider abstraction ✅ shipped in v0.7.0

`FailureAnalyzer` `@runtime_checkable` Protocol defines the required interface. `AnthropicFailureAnalyzer` ships as the first new adapter (Anthropic Claude, `[anthropic]` extra). All existing analyzers satisfy the protocol structurally.

### 3.3 Context budget management ✅ shipped in v0.7.0

`max_context_chars: int = 8000` on `LLMFailureAnalyzer` and `OllamaFailureAnalyzer`. Traceback trimmed from the top when prompt exceeds budget; replaced with `<traceback omitted>` marker when budget exhausted entirely.

### 3.4 Failure deduplication ✅ shipped in v0.7.0

`DeduplicatingAnalyzer(inner, max_cache_size=256)` wraps any analyzer. LRU cache keyed by SHA-256 of `(error_type, filename, lineno, exception_chain)`. `None` results never cached. Thread-safe; async-aware.

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

### 0.7.0

**New features — Phase 3 LLM layer improvements**

- `FailureAnalyzer` protocol — `@runtime_checkable` `typing.Protocol`; all existing analyzers satisfy it structurally.
- `AnthropicFailureAnalyzer` — Anthropic Claude adapter (`[anthropic]` extra). Defaults to `claude-haiku-4-5-20251001`; reads `ANTHROPIC_API_KEY` and `RUNTIME_NARRATIVE_MODEL` from env. Full sync + async support.
- `DeduplicatingAnalyzer(inner, max_cache_size=256)` — LRU cache wrapper; SHA-256 keyed; `None` never cached; thread-safe.
- Structured LLM output — `LLMFailureAnalyzer` and `OllamaFailureAnalyzer` now request JSON from the model and parse it into `## Exact Why / ## Evidence / ## Targeted Fix / ## Code Changes` sections. Graceful fallback to raw text.
- Context budget — `max_context_chars: int = 8000` on both OpenAI-compat and Ollama analyzers; trims traceback from the top to stay within budget.

### 0.6.0

**New features — Phase 2 OTel integration**

- `OtelLogRenderer` — emits all 6 lifecycle events as OTel log records via `opentelemetry._logs`. Failures are `ERROR` severity with structured attributes (`error.type`, `code.filepath`, `error.stack_trace`, etc.). Stage events are `DEBUG`; story and LLM events are `INFO`. Automatically correlates `trace_id`/`span_id` from the ambient OTel context (works seamlessly alongside `OtelRenderer`). Requires `[otel]` extra.
- `OtelMetricsRenderer` — emits four OTel instruments via `opentelemetry.metrics`: `narrative.stage.duration` (Histogram), `narrative.story.duration` (Histogram), `narrative.story.failures` (Counter), `narrative.llm.analysis_latency` (Histogram). Accepts a custom `MeterProvider` for test/multi-tenant isolation. Requires `[otel]` extra.
- `RuntimeNarrativeMiddleware(propagate_trace_context=True)` — extracts W3C `traceparent`/`tracestate` headers via `opentelemetry.propagate.extract()` before entering each request's story context. Makes `OtelRenderer` story spans children of the upstream trace instead of orphaned roots. Silently no-ops when `opentelemetry` is not installed. Pass `propagate_trace_context=False` to opt out.

### 0.5.0

**New features — Observability renderers and stage metadata**

- `OtelRenderer` — maps narrative events to OpenTelemetry spans. Each story is a root span; each stage is a child span. `FailureOccurred` sets status `ERROR` and structured attributes (`error.type`, `code.filepath`, etc.) on the root span. `LLMAnalysisReady` adds a span event with the analysis text. Requires the new `[otel]` extra (`opentelemetry-api>=1.20.0`, `opentelemetry-sdk>=1.20.0`).
  - `exclude_stages: set[str]` — skip specific stage spans entirely. Failures on excluded stages still mark the root span `ERROR`.
  - `min_duration_ms: float` — suppress stage spans below the duration threshold (abandoned, never exported). Defaults to `0.0` (no filtering).
  - `max_attribute_length: int` — truncate long string attributes (default 8192).
- `PrometheusRenderer` — emits four metrics via `prometheus-client`. Requires the new `[prometheus]` extra.
  - `narrative_story_duration_seconds` — Histogram, labels `story_name` + `success`
  - `narrative_stage_duration_seconds` — Histogram, labels `story_name` + `stage_name`
  - `narrative_story_failures_total` — Counter, labels `story_name` + `error_type`
  - `narrative_story_total` — Counter, labels `story_name` + `success`
  - Accepts a custom `CollectorRegistry` for test/multi-tenant isolation.
- `StageStarted` and `StageCompleted` events now carry `stage_index: int` (0-based position in the story's stage list) and `parent_stage_name: str | None` (set for nested stages). Both default to `0`/`None` — backwards compatible with existing renderers.

### 0.4.0

**New features — Phase 2 Auto-instrumentation**

- `@narrative_stage(name=None)` — per-method/function stage decorator. When used inside `@narrative_class`, the custom name overrides the default `ClassName.method_name` and the method is not double-wrapped (detected via `_narrative_stage_name` sentinel). When `name` is omitted, the function name is title-cased (`validate_order` → `"Validate Order"`). Works standalone on any sync or async function.
- `@narrative_class(instrument_classmethods=True)` — opt-in instrumentation of `@classmethod` methods. Accesses `__func__` to wrap the underlying function, then re-applies `classmethod()`. Respects `@no_stage` and `@narrative_stage` overrides on the inner function.
- `@narrative_class(instrument_staticmethods=True)` — same pattern for `@staticmethod` methods. Both flags default to `False` — zero breaking change for existing `@narrative_class` usage.

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