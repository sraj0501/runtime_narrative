# Changelog

All notable changes to `runtime-narrative` are documented here.

---

## 1.2.0 — 2026-07-01

Structured log fields, customizable `ConsoleRenderer` styles, and per-story renderer routing. No breaking changes.

### Added
- **`LogRecorded.fields: dict[str, Any]`** — caller-supplied `extra={...}` fields from a captured `logging` call (e.g. `logger.warning("cache miss", extra={"order_id": "ORD-42"})`), extracted by `NarrativeLogHandler` and excluded of standard `LogRecord` attributes.
- **`structlog` optional extra** — when installed, `ConsoleRenderer` renders `LogRecorded` lines using `structlog.dev.ConsoleRenderer`'s own default style (colored level, timestamp, message, `key=value` fields). Falls back to a plain equivalent format with no hard dependency when `structlog` is absent.
- **`ConsoleRenderer(log_renderer=None, level_icons=None)`** — `log_renderer` accepts any callable matching structlog's renderer signature for full custom styling; `level_icons` maps a lowercase level name to a string prefix (e.g. an emoji) prepended to the message. Both empty/default by default — no behavior change unless configured.
- **`FilteredRenderer(predicate, renderer)`** (`runtime_narrative.renderer.filter_renderer`) — wraps any renderer, forwarding an event only when `predicate(event)` returns `True`. Since every event type carries `story_name`, this is the general mechanism for routing different story families (e.g. all `"GET ..."` request stories) to their own style or destination. Mirrors the wrapped renderer's sync/async `handle`.

---

## 1.1.0 — 2026-07-01

Sub-story tracing and stdlib `logging` capture. No breaking changes.

### Added
- **Sub-stories** — opening `story()` while another is already active (in the same sync/async context) now automatically links it as a sub-story: `renderers`, `diagnostics_config`, and `failure_analyzer` are inherited from the parent unless passed explicitly, and `parent_story_id` / `root_story_id` are set automatically. No new API — the existing `story()` primitive detects nesting via the same `ContextVar` mechanism `stage()` already uses for `parent_stage_name`.
- **`parent_story_id: str | None` and `root_story_id: str`** on `StoryStarted`, `StoryCompleted`, and `FailureOccurred` — lets any consumer reconstruct the full call tree (API call → DB sub-story → ...) from events alone.
- **`duration_seconds: float`** on `StoryCompleted` — total story elapsed time, previously only derivable by diffing `StoryStarted`/`StoryCompleted` timestamps yourself.
- **`LogRecorded` event + `NarrativeLogHandler`** (`runtime_narrative.logging_bridge`) — a standard `logging.Handler` that routes captured `logging.warning()`/`.error()` calls into the active story's event pipeline instead of a second, disconnected log stream. Falls back to an optional `fallback` handler when no story is active, so nothing is silently dropped. Both are exported at top level.
- **`ConsoleRenderer`**: every rendered line (including `LogRecorded`) is now tagged with `[short_id]` (first 6 characters of that event's `story_id`) and colored per story family (a root story and its sub-stories share one deterministic color), so concurrent/nested stories are identifiable when scanning or searching console output.
- **`ConsoleRenderer`**: lines are indented one level per stage/sub-story nesting depth, so the call tree renders visually in the log output without needing a separate tree/report renderer.
- **`OtelRenderer`**: sub-stories now become real child spans of their parent story's span (previously every `StoryStarted` produced an orphaned root span, even when nested).
- **`JsonRenderer`**: emits `LogRecorded` events and includes `parent_story_id`, `root_story_id`, and `duration_seconds` in `StoryStarted`/`StoryCompleted`/`FailureOccurred` payloads.

---

## 1.0.1 — 2026-07-01

Patch release addressing six usability issues (#19–#24). No breaking changes.

### Added
- **`has_active_story() -> bool`** — exported from `runtime_narrative`; cheap `ContextVar` probe returning `True` when a `story()` context is active in the current async/sync context.
- **`stage(name, optional=True)`** — no-op mode: silently skips stage registration and event emission when no story is active; fully instrumented when inside a story. Useful for library code that may or may not run under a story.
- **`StoryRuntime.record_failure(exc, *, stage_name=None)`** — async method that emits `FailureOccurred` (with full diagnostics) without owning exception propagation. Enables saga/rollback patterns where errors from compensating actions should be observed without re-raising.
- **`RuntimeNarrativeMiddleware(skip_if=callable)`** — optional predicate `Callable[[Request], bool]`; when it returns `True` for a request the middleware bypasses story wrapping entirely and calls `call_next` directly. Useful for health-check and readiness probe routes.
- **`story_name: str` field on `StageStarted` and `StageCompleted`** — populated automatically; renderers no longer need a `story_id → story_name` side table. Defaults to `""` for backward compatibility with code that constructs these events directly.
- **All event dataclasses + `Event` union type exported at top level** — `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`, `LLMAnalysisReady`, and `Event` are now part of the stable public API importable from `runtime_narrative`. Enables `isinstance` dispatch and IDE autocomplete in custom renderers.
- **`ConsoleRenderer` exported at top level** — `from runtime_narrative import ConsoleRenderer` now works without reaching into the subpackage.

---

## 1.0.0 — 2026-06-29

### Added
- **`SqliteStoryRenderer(path)`** — sync renderer that persists all six lifecycle events to a SQLite database. Three tables: `stories`, `stages`, `failures`. Story duration computed via SQLite `julianday` arithmetic. `LLMAnalysisReady` back-fills the `llm_analysis` column. Queryable via the `runtime-narrative` CLI.
- **`runtime-narrative` CLI** (`runtime_narrative/cli.py`, registered as a console script) — two sub-commands:
  - `runtime-narrative failures [--db PATH] [--last N] [--stage NAME] [--story NAME]` — tabular list of recent failures.
  - `runtime-narrative story STORY_ID [--db PATH]` — story header, stage table, and failure detail block.
- **`AlertRoutingRenderer(destinations, *, only_stories=None, only_error_types=None)`** — async renderer that fans out `FailureOccurred` events to configured destinations via `asyncio.gather`. Destination failures are logged to `stderr` and swallowed — they never crash the story.
  - **`HttpWebhookDestination(url, *, headers=None, timeout=10.0)`** — POST JSON payload to any HTTP endpoint via `asyncio.to_thread(urllib.request.urlopen, ...)`.
  - **`SlackWebhookDestination(webhook_url)`** — subclass of `HttpWebhookDestination`; posts a Block Kit payload (header + detail section; optional analysis section when `llm_analysis` is present).
- **`FailureDiagnosticsConfig.redact_patterns: tuple[str, ...]`** — additional regex patterns (case-insensitive `re.search`) matched against local variable key names during rich diagnostics capture.
- **`FailureDiagnosticsConfig.redact_callback: Callable[[str], bool] | None`** — custom predicate called per key name; `True` → redact. Exceptions from the callback are caught and treated as non-redact.
- Both new redaction fields flow through `merge()`, `_capture_locals_mapping`, and `_serialize_value`.

---

## 0.9.0 — 2026-06-29

### Added
- **`StoryRecorder`** (`runtime_narrative.testing`) — dual sync/async context manager for test assertions. Starts a story with a capturing renderer; exposes `events` list and four assertion methods: `assert_stages_completed(names)`, `assert_no_failure()`, `assert_stage_failed(stage_name, *, error_type=None)`, `assert_story_completed(*, success=None)`.
- **`HtmlReportRenderer(path)`** — renderer that writes a self-contained HTML report on `StoryCompleted`. Includes story header (name, duration, status badge), per-stage duration bar chart, and a failure detail section with traceback and optional LLM analysis.
- **`dry_run=False` on `story()`** — when `True`, stage bodies that raise exceptions have the exception suppressed and the stage is still marked completed. The story completes as `success=True`. Useful for verifying instrumentation wiring without executing expensive side effects. Works with both sync `with stage()` and `async with stage()`.

### Changed
- **5.4 stage timeline was already complete** — the full ordered stage timeline (not a 5-stage tail) has been present since v0.2.0. The roadmap item is now explicitly marked done.

---

## 0.8.0 — 2026-06-29

### Added
- **`RuntimeNarrativeDjangoMiddleware`** — async Django ASGI middleware (`[django]` extra required). Wraps every HTTP request in `async with story(...)`. Story name is `"METHOD /path"`. Auto-selects `ConsoleRenderer` on a TTY, `JsonRenderer` otherwise.
- **`RuntimeNarrativeDjangoSyncMiddleware`** — sync Django WSGI middleware. Same interface and story-naming as the async variant; uses `with story(...)` instead.
- **`NarrativeTask`** — Celery `Task` base class (`[celery]` extra required). Apply as `@app.task(base=NarrativeTask)`. Wraps each task execution in `with story("<task.name> [task_id=<id>]", ...)`. Class-level attributes (`narrative_renderers`, `narrative_failure_analyzer`, etc.) are overridable per task or globally via `connect_narrative`.
- **`connect_narrative(celery_app, *, renderers, failure_analyzer, ...)`** — sets `NarrativeTask` class-level defaults for all tasks in an app without requiring `base=NarrativeTask` on every task definition.
- **`NarrativeTaskGroup`** — async context manager for concurrent asyncio tasks under a shared story. `create_task(coro, *, name=None)` schedules work; tasks inherit the parent story context automatically via asyncio ContextVar copy. On exit, waits for all tasks and raises `NarrativeTaskGroupError` if any failed. Works on Python 3.9+, no extra dependencies.
- **`NarrativeTaskGroupError`** — raised by `NarrativeTaskGroup` when one or more tasks fail. `failed_tasks: dict[str, BaseException]` maps task name → exception.
- **`RuntimeNarrativeInterceptor`** — sync gRPC `ServerInterceptor` (`[grpc]` extra required). Wraps unary RPCs in `with story(method_path, ...)`.
- **`RuntimeNarrativeAsyncInterceptor`** — async gRPC `aio.ServerInterceptor`. Wraps each RPC in `async with story(method_path, ...)`.
- **`[django]` optional extra** — `django>=3.2`.
- **`[celery]` optional extra** — `celery>=5.0`.
- **`[grpc]` optional extra** — `grpcio>=1.50.0`.

---

## 0.7.0 — 2026-06-29

### Added
- **`FailureAnalyzer` protocol** (`runtime_narrative.analyzers.base`) — `@runtime_checkable` `typing.Protocol` defining the required `analyze_failure(*)` signature. All existing analyzers satisfy it structurally with no code changes required.
- **`AnthropicFailureAnalyzer`** — failure analyzer backed by Anthropic's API (`[anthropic]` extra required; `anthropic>=0.25.0`).
  - Defaults to `claude-haiku-4-5-20251001`; override via `model=` or `RUNTIME_NARRATIVE_MODEL` env var.
  - API key read from `ANTHROPIC_API_KEY`; override via `api_key=`.
  - `analyze_failure()` uses the sync `anthropic.Anthropic` client; `analyze_failure_async()` uses `anthropic.AsyncAnthropic` for non-blocking execution.
  - Both parse the model's JSON response into formatted `## Exact Why / ## Evidence / ## Targeted Fix / ## Code Changes` sections with graceful fallback to raw text.
- **`DeduplicatingAnalyzer`** — wrapper that caches LLM suggestions by a SHA-256 hash of `(error_type, filename, lineno, exception_chain)`.
  - `DeduplicatingAnalyzer(inner, max_cache_size=256)` wraps any existing analyzer.
  - LRU eviction when cache reaches `max_cache_size`.
  - `None` results (network errors, timeouts) are never cached — next call retries the model.
  - Thread-safe; async path delegates to `inner.analyze_failure_async()` if available, otherwise uses `asyncio.to_thread`.
- **Structured LLM output** — `LLMFailureAnalyzer` and `OllamaFailureAnalyzer` now request structured JSON (`exact_why`, `evidence`, `targeted_fix`, `code_changes`) instead of free-text markdown. Responses are parsed and reformatted into guaranteed `## Header\ncontent` sections. Gracefully falls back to raw text if the model returns non-JSON.
- **Context budget management** — `LLMFailureAnalyzer` and `OllamaFailureAnalyzer` now accept `max_context_chars: int = 8000`. Traceback excerpts are trimmed from the top (keeping the most recent frames) when the prompt would exceed the budget. If the budget is exhausted before any traceback fits, a `<traceback omitted>` marker is used instead.
- **`[anthropic]` optional extra** — `anthropic>=0.25.0`.

---

## 0.6.0 — 2026-06-29

### Added
- **`OtelLogRenderer`** — emits all 6 lifecycle events as OpenTelemetry log records via `opentelemetry._logs` API (`[otel]` extra required).
  - `StoryStarted` / `StoryCompleted` / `LLMAnalysisReady` → `INFO` severity.
  - `StageStarted` / `StageCompleted` → `DEBUG` severity.
  - `FailureOccurred` → `ERROR` severity with full diagnostics attributes: `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `narrative.exception_chain`, `narrative.exact_cause`, `error.stack_trace`.
  - Automatically correlates `trace_id` / `span_id` from the ambient OTel context so log records link to co-existing spans.
  - Accepts `logger_provider` and `logger_name` constructor kwargs for test/multi-tenant isolation.
- **`OtelMetricsRenderer`** — emits four OTel instruments via `opentelemetry.metrics` API (`[otel]` extra required).
  - `narrative.stage.duration` (Histogram, unit `s`, labels `story_name` + `stage_name`).
  - `narrative.story.duration` (Histogram, unit `s`, labels `story_name` + `success`).
  - `narrative.story.failures` (Counter, unit `1`, labels `story_name` + `error_type`).
  - `narrative.llm.analysis_latency` (Histogram, unit `s`, label `story_name`) — time from `FailureOccurred` to `LLMAnalysisReady`.
  - Accepts `meter_provider` and `meter_name` for isolation.
- **W3C traceparent propagation in `RuntimeNarrativeMiddleware`** — extracts incoming `traceparent` / `tracestate` headers via `opentelemetry.propagate.extract()` and attaches the extracted context before entering each request's story. This makes `OtelRenderer` story spans children of the upstream trace rather than orphaned roots. Automatically enabled when `opentelemetry-api` is installed; silently no-ops otherwise.
  - `propagate_trace_context: bool = True` — set to `False` to disable propagation while keeping OTel installed.

---

## 0.5.0 — 2026-06-29

### Added
- **`OtelRenderer`** — maps narrative events to OpenTelemetry spans (`[otel]` extra required).
  - Story → root span; stage → child span.
  - `FailureOccurred` sets span status `ERROR` with `error.type`, `error.message`, `code.filepath`, `code.lineno`, `code.function`, `error.stack_trace`, `narrative.exception_chain` attributes.
  - `LLMAnalysisReady` adds a `llm_analysis_ready` span event with `narrative.llm_analysis` attribute.
  - `exclude_stages: set[str]` — skip specific stage spans (failures on excluded stages still mark the root `ERROR`).
  - `min_duration_ms: float` — suppress stage spans below the threshold; defaults to `0.0` (disabled).
  - `max_attribute_length: int` — truncate long string attributes; defaults to `8192`.
- **`PrometheusRenderer`** — Prometheus metrics via `prometheus-client` (`[prometheus]` extra required).
  - `narrative_story_duration_seconds` — Histogram (`story_name`, `success`).
  - `narrative_stage_duration_seconds` — Histogram (`story_name`, `stage_name`).
  - `narrative_story_failures_total` — Counter (`story_name`, `error_type`).
  - `narrative_story_total` — Counter (`story_name`, `success`).
  - Accepts a custom `CollectorRegistry` for test/multi-tenant isolation.
- **`[otel]` optional extra** — `opentelemetry-api>=1.20.0`, `opentelemetry-sdk>=1.20.0`.
- **`[prometheus]` optional extra** — `prometheus-client>=0.19.0`.
- **Stage metadata on events** — `StageStarted` and `StageCompleted` now carry `stage_index: int` (0-based position in the story's stage list) and `parent_stage_name: str | None` (enclosing stage name for nested stages, `None` otherwise). Both fields default to `0`/`None` — no breaking changes for existing renderers.

---

## 0.4.0 — 2026-06-28

### Added
- **`@narrative_stage(name=None)`** — per-method/function stage decorator.
  - When used inside `@narrative_class`, the custom name overrides the default `ClassName.method_name` and the method is **not** double-wrapped (enforced via `_narrative_stage_name` sentinel).
  - When `name` is omitted, the function name is title-cased (`validate_order` → `"Validate Order"`).
  - Works on any sync or async function, standalone or nested inside a class.
- **`@narrative_class(instrument_classmethods=True)`** — opt-in instrumentation of `@classmethod` methods. Unwraps `__func__`, wraps it, then re-applies `classmethod()`. Respects `@no_stage` and `@narrative_stage` on the inner function.
- **`@narrative_class(instrument_staticmethods=True)`** — same pattern for `@staticmethod` methods.
- Both flags default to `False` — fully backwards-compatible with all existing `@narrative_class` usage.

---

## 0.3.0 — 2026-06-04

### Added
- **`@narrative_class`** — class decorator that wraps every public instance method as a stage. Stage name is `ClassName.method_name`. Skips names starting with `_`, `@no_stage`-marked methods, `@staticmethod`, `@classmethod`, `@property`, and inherited methods (apply the decorator to the base class separately).
- **`@no_stage`** — opt-out marker. Apply to any method or function to exclude it from `@narrative_class`, `instrument_module`, and `auto_instrument`.
- **`instrument_module(module)`** — instruments all public callables defined in a module in-place. Classes get `@narrative_class`; top-level functions are wrapped directly. Symbols imported from other modules are not touched.
- **`auto_instrument(app_roots=...)`** — registers a `sys.meta_path` import hook that instruments every app module on import. Only modules whose source path starts with `app_roots` (default: `cwd`) are instrumented — stdlib and installed packages are unaffected. Returns the finder for later removal via `sys.meta_path.remove(finder)`.

---

## 0.2.0

### Fixed
- `ConsoleRenderer` no longer crashes with `UnicodeEncodeError` on Windows cp1252 terminals. Non-UTF-8 terminals use ASCII glyphs (`>`, `[ok]`, `[FAIL]`) automatically. A secondary `try/except` in `_secho` handles any remaining encoding errors.
- Fixed a copy-paste bug where `StoryStarted` was logged as "Stage started" instead of "Story started".
- `emit()` and `emit_async()` now isolate renderer failures — a renderer that raises prints a warning to `stderr` and the next renderer continues uninterrupted.
- `JsonRenderer` now handles `LLMAnalysisReady` events (background analysis results were previously silently dropped).
- Progress percent is now accurate when stages are declared upfront via `story(total_stages=n)` or `runtime.set_total_stages(n)`.

### Added
- `RuntimeNarrativeMiddleware` auto-selects its renderer: `ConsoleRenderer` on a real TTY, `JsonRenderer` otherwise.
- `async with stage()` now dispatches through `emit_async()`, so async renderers receive stage events awaited.
- `FailureDiagnosticsConfig` raises `ValueError` immediately on invalid `failure_diagnostics` values.
- Stage timeline in failure reports now includes the full ordered history (previous 5-stage truncation removed).
- Custom redaction: `redact_extra` kwarg on `FailureDiagnosticsConfig`, `story()`, and `RuntimeNarrativeMiddleware`.
- `RotatingJsonRenderer(path, max_bytes=10_485_760, backup_count=5)`.
- `StoryRuntime` exported from the top-level package for type-hinting.

---

## 0.1.0

Initial release.

- `story()` / `stage()` — dual sync/async context managers
- `ConsoleRenderer` — rich terminal output
- `JsonRenderer` — one structured JSON object per lifecycle event
- Lean/rich failure diagnostics — source snippet, frame classification, local variable capture, secret redaction, production traceback caps
- `OllamaFailureAnalyzer` + `LLMFailureAnalyzer` — sync and async, background analysis mode
- `RuntimeNarrativeMiddleware` — FastAPI/Starlette request → story
- `@runtime_narrative_story` / `@runtime_narrative_stage` decorators
- Exception chain traversal, exact-cause inference
