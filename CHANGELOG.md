# Changelog

All notable changes to `runtime-narrative` are documented here.

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
