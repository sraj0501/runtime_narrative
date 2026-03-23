from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Mapping

from .failure import FailureSummary, _build_exception_chain, _infer_exact_cause

_ENV_ENVIRONMENT = "RUNTIME_NARRATIVE_ENV"
_ENV_FAILURE_DIAGNOSTICS = "RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS"
_ENV_ALLOW_RICH_IN_PRODUCTION = "RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION"

_DEFAULT_REDACT_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "session",
    "credential",
)


@dataclass(frozen=True)
class FailureDiagnosticsConfig:
    """Controls failure attachment depth (lean vs rich) and frame selection."""

    runtime_environment: str = "development"
    failure_diagnostics: str = "lean"
    allow_rich_in_production: bool = False
    app_roots: tuple[str, ...] = ()
    max_traceback_chars: int | None = 12_000
    production_traceback_cap: int = 8_000
    max_locals_per_frame: int = 12
    max_local_value_len: int = 200
    max_local_depth: int = 2
    max_frames_with_locals: int = 2
    snippet_context_lines: int = 2

    @classmethod
    def merge(
        cls,
        base: FailureDiagnosticsConfig,
        *,
        runtime_environment: str | None = None,
        failure_diagnostics: str | None = None,
        allow_rich_in_production: bool | None = None,
        app_roots: tuple[str, ...] | None = None,
    ) -> FailureDiagnosticsConfig:
        return cls(
            runtime_environment=runtime_environment if runtime_environment is not None else base.runtime_environment,
            failure_diagnostics=failure_diagnostics if failure_diagnostics is not None else base.failure_diagnostics,
            allow_rich_in_production=(
                allow_rich_in_production if allow_rich_in_production is not None else base.allow_rich_in_production
            ),
            app_roots=app_roots if app_roots is not None else base.app_roots,
            max_traceback_chars=base.max_traceback_chars,
            production_traceback_cap=base.production_traceback_cap,
            max_locals_per_frame=base.max_locals_per_frame,
            max_local_value_len=base.max_local_value_len,
            max_local_depth=base.max_local_depth,
            max_frames_with_locals=base.max_frames_with_locals,
            snippet_context_lines=base.snippet_context_lines,
        )

    @classmethod
    def from_env(cls) -> FailureDiagnosticsConfig:
        env = (os.environ.get(_ENV_ENVIRONMENT) or "development").strip().lower()
        diag = (os.environ.get(_ENV_FAILURE_DIAGNOSTICS) or "lean").strip().lower()
        allow_raw = os.environ.get(_ENV_ALLOW_RICH_IN_PRODUCTION, "").strip().lower()
        allow_rich = allow_raw in ("1", "true", "yes", "on")
        if diag not in ("lean", "rich"):
            diag = "lean"
        return cls(
            runtime_environment=env,
            failure_diagnostics=diag,
            allow_rich_in_production=allow_rich,
        )


def effective_diagnostics_mode(config: FailureDiagnosticsConfig) -> str:
    """Return ``lean`` or ``rich`` after applying production safeguards."""
    mode = config.failure_diagnostics
    if mode not in ("lean", "rich"):
        mode = "lean"
    if mode == "rich" and config.runtime_environment == "production" and not config.allow_rich_in_production:
        return "lean"
    return mode


def _norm_roots(roots: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for r in roots:
        try:
            out.append(os.path.realpath(os.path.abspath(r)))
        except OSError:
            continue
    return out


def _classify_frame(filename: str, app_norms: list[str]) -> str:
    norm = filename.replace("\\", "/")
    if "site-packages" in norm:
        return "site_packages"
    try:
        real = os.path.realpath(os.path.abspath(filename))
    except OSError:
        real = filename
    prefix = sys.prefix.replace("\\", "/")
    real_slash = real.replace("\\", "/")
    if real_slash.startswith(prefix) and "site-packages" not in real_slash:
        return "stdlib"
    for root in app_norms:
        root_slash = root.replace("\\", "/")
        r_slash = real.replace("\\", "/")
        if r_slash == root_slash or r_slash.startswith(root_slash + "/"):
            return "app"
    return "other"


def _read_source_snippet(filename: str, lineno: int, context: int) -> str | None:
    if lineno <= 0 or not filename or not os.path.isfile(filename):
        return None
    try:
        with open(filename, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None
    start = max(0, lineno - 1 - context)
    end = min(len(lines), lineno + context)
    chunk = lines[start:end]
    out_lines: list[str] = []
    for i, line in enumerate(chunk, start=start + 1):
        prefix = ">" if i == lineno else " "
        out_lines.append(f"{prefix} {i:4d} | {line.rstrip()}"[: 500])
    return "\n".join(out_lines) if out_lines else None


def _truncate_tb(text: str, cap: int | None) -> tuple[str, bool]:
    if cap is None or len(text) <= cap:
        return text, False
    return text[: cap - 20] + "\n... [traceback truncated]", True


def _serialize_value(value: Any, *, max_len: int, depth: int, max_depth: int) -> str:
    if depth > max_depth:
        return "<max depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)
    if isinstance(value, str):
        s = value if len(value) <= max_len else value[: max_len - 3] + "..."
        return repr(s)
    if isinstance(value, bytes):
        if len(value) > 64:
            return f"<bytes len={len(value)}>"
        return repr(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]" if isinstance(value, list) else "()"
        if depth >= max_depth:
            return f"<{type(value).__name__} len={len(value)}>"
        inner = ", ".join(_serialize_value(v, max_len=max_len, depth=depth + 1, max_depth=max_depth) for v in value[:5])
        suffix = ", ..." if len(value) > 5 else ""
        bracket = "[]" if isinstance(value, list) else "()"
        return bracket[0] + inner + suffix + bracket[1]
    if isinstance(value, dict):
        if not value:
            return "{}"
        if depth >= max_depth:
            return f"<dict len={len(value)}>"
        parts: list[str] = []
        for k, v in list(value.items())[:5]:
            key_repr = _serialize_value(k, max_len=40, depth=depth + 1, max_depth=max_depth)
            if _should_redact_key(str(k)):
                parts.append(f"{key_repr}: <redacted>")
            else:
                parts.append(
                    f"{key_repr}: "
                    f"{_serialize_value(v, max_len=max_len, depth=depth + 1, max_depth=max_depth)}"
                )
        suffix = ", ..." if len(value) > 5 else ""
        return "{" + ", ".join(parts) + suffix + "}"
    try:
        r = repr(value)
    except Exception:
        return f"<{type(value).__name__}>"
    return r if len(r) <= max_len else r[: max_len - 3] + "..."


def _should_redact_key(name: str) -> bool:
    lower = name.lower()
    return any(sub in lower for sub in _DEFAULT_REDACT_SUBSTRINGS)


def _capture_locals_mapping(
    locals_map: Mapping[str, Any],
    *,
    max_keys: int,
    max_len: int,
    max_depth: int,
) -> tuple[dict[str, str], int]:
    redacted = 0
    out: dict[str, str] = {}
    count = 0
    for key in sorted(locals_map.keys()):
        if key.startswith("_") and key not in ("__traceback__",):
            continue
        if count >= max_keys:
            break
        if _should_redact_key(key):
            out[key] = "<redacted>"
            redacted += 1
            count += 1
            continue
        try:
            out[key] = _serialize_value(locals_map[key], max_len=max_len, depth=0, max_depth=max_depth)
        except Exception:
            out[key] = f"<{type(locals_map[key]).__name__}>"
        count += 1
    return out, redacted


@dataclass
class EnrichedFailure:
    """Structured failure data for ``FailureOccurred`` and analyzers."""

    summary: FailureSummary
    diagnostics_mode: str
    primary_frame_reason: str
    stack_frames: list[dict[str, Any]]
    source_snippet: str | None
    compressed_stack_summary: str
    hidden_frame_count: int
    traceback_truncated: bool
    locals_by_frame: dict[str, Any] | None
    redaction_removed_keys: int


def build_enriched_failure(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
    *,
    config: FailureDiagnosticsConfig,
) -> EnrichedFailure:
    import traceback

    mode = effective_diagnostics_mode(config)
    app_norms = _norm_roots(config.app_roots) if config.app_roots else _norm_roots((os.getcwd(),))

    stack_frames: list[dict[str, Any]] = []
    frame_objs: list[Any] = []
    if tb is not None:
        for fr, ln in traceback.walk_tb(tb):
            frame_objs.append(fr)
        extracted = traceback.extract_tb(tb)
        for i, entry in enumerate(extracted):
            kind = _classify_frame(entry.filename, app_norms)
            stack_frames.append(
                {
                    "index": i,
                    "filename": entry.filename,
                    "lineno": entry.lineno,
                    "function": entry.name,
                    "kind": kind,
                    "line": entry.line,
                }
            )
    else:
        extracted = []

    primary_idx = len(extracted) - 1
    primary_reason = "leaf"
    if extracted:
        for i in range(len(extracted) - 1, -1, -1):
            if stack_frames[i]["kind"] == "app":
                primary_idx = i
                primary_reason = "innermost_app"
                break
        else:
            for i in range(len(extracted) - 1, -1, -1):
                if stack_frames[i]["kind"] not in ("site_packages", "stdlib"):
                    primary_idx = i
                    primary_reason = "innermost_non_stdlib"
                    break

    if extracted:
        pf = extracted[primary_idx]
        filename = pf.filename
        lineno = pf.lineno
        function = pf.name
        source_line = pf.line or "<source unavailable>"
    else:
        filename = "<unknown>"
        lineno = 0
        function = "<unknown>"
        source_line = "<source unavailable>"

    full_tb = "".join(traceback.format_exception(exc_type, exc, tb))
    truncated = False
    tb_out = full_tb
    if config.runtime_environment == "production":
        tb_out, truncated = _truncate_tb(full_tb, config.production_traceback_cap)
    elif config.max_traceback_chars is not None:
        tb_out, truncated = _truncate_tb(full_tb, config.max_traceback_chars)

    summary = FailureSummary(
        error_type=exc_type.__name__,
        error_message=str(exc),
        filename=filename,
        lineno=lineno,
        function=function,
        source_line=source_line,
        exception_chain=_build_exception_chain(exc),
        exact_cause=_infer_exact_cause(exc_type.__name__, str(exc), source_line),
        traceback_text=tb_out,
    )

    snippet = _read_source_snippet(filename, lineno, config.snippet_context_lines)
    for sf in stack_frames:
        sf["is_primary"] = sf["index"] == primary_idx

    app_visible = sum(1 for sf in stack_frames if sf["kind"] == "app")
    hidden = max(0, len(stack_frames) - app_visible)
    compressed = f"{app_visible} app frame(s), {hidden} other/hidden in full stack ({len(stack_frames)} total)"

    locals_by_frame: dict[str, Any] | None = None
    redaction_total = 0
    if mode == "rich" and frame_objs and extracted and len(frame_objs) == len(extracted):
        locals_by_frame = {}
        # Walk from primary outward (include primary first)
        indices_to_capture: list[int] = []
        for offset in range(config.max_frames_with_locals):
            idx = primary_idx - offset
            if idx < 0:
                break
            indices_to_capture.append(idx)
        for idx in indices_to_capture:
            fr = frame_objs[idx]
            label = f"frame_{idx}"
            locs, red = _capture_locals_mapping(
                fr.f_locals,
                max_keys=config.max_locals_per_frame,
                max_len=config.max_local_value_len,
                max_depth=config.max_local_depth,
            )
            redaction_total += red
            meta = stack_frames[idx]
            locals_by_frame[label] = {
                "filename": meta["filename"],
                "lineno": meta["lineno"],
                "function": meta["function"],
                "locals": locs,
            }

    return EnrichedFailure(
        summary=summary,
        diagnostics_mode=mode,
        primary_frame_reason=primary_reason,
        stack_frames=stack_frames,
        source_snippet=snippet,
        compressed_stack_summary=compressed,
        hidden_frame_count=hidden,
        traceback_truncated=truncated,
        locals_by_frame=locals_by_frame,
        redaction_removed_keys=redaction_total,
    )
