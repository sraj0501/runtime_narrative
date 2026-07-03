from __future__ import annotations

import dataclasses
import json
import os

import pytest

from runtime_narrative import stage, story
from runtime_narrative.diagnostics import (
    FailureDiagnosticsConfig,
    build_enriched_failure,
    effective_diagnostics_mode,
)
from runtime_narrative.events import FailureOccurred
from tests.conftest import CapturingRenderer


def test_effective_diagnostics_mode_rich_in_dev() -> None:
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")
    assert effective_diagnostics_mode(cfg) == "rich"


def test_effective_diagnostics_mode_rich_forced_lean_in_production() -> None:
    cfg = FailureDiagnosticsConfig(
        runtime_environment="production",
        failure_diagnostics="rich",
        allow_rich_in_production=False,
    )
    assert effective_diagnostics_mode(cfg) == "lean"


def test_effective_diagnostics_mode_rich_allowed_in_production() -> None:
    cfg = FailureDiagnosticsConfig(
        runtime_environment="production",
        failure_diagnostics="rich",
        allow_rich_in_production=True,
    )
    assert effective_diagnostics_mode(cfg) == "rich"


def test_effective_diagnostics_mode_invalid_mode_raises() -> None:
    base = FailureDiagnosticsConfig()
    with pytest.raises(ValueError, match="Invalid failure_diagnostics"):
        dataclasses.replace(base, failure_diagnostics="bogus")  # type: ignore[misc]


def test_merge_preserves_limits_and_overrides_flags() -> None:
    base = FailureDiagnosticsConfig(
        runtime_environment="development",
        failure_diagnostics="lean",
        max_local_value_len=99,
    )
    merged = FailureDiagnosticsConfig.merge(
        base,
        runtime_environment="staging",
        failure_diagnostics="rich",
        app_roots=("/tmp",),
    )
    assert merged.runtime_environment == "staging"
    assert merged.failure_diagnostics == "rich"
    assert merged.app_roots == ("/tmp",)
    assert merged.max_local_value_len == 99


def test_from_env_reads_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_NARRATIVE_ENV", "PRODUCTION")
    monkeypatch.setenv("RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS", "RICH")
    monkeypatch.setenv("RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION", "1")
    cfg = FailureDiagnosticsConfig.from_env()
    assert cfg.runtime_environment == "production"
    assert cfg.failure_diagnostics == "rich"
    assert cfg.allow_rich_in_production is True


def test_from_env_invalid_diag_defaults_lean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_NARRATIVE_FAILURE_DIAGNOSTICS", "verbose")
    cfg = FailureDiagnosticsConfig.from_env()
    assert cfg.failure_diagnostics == "lean"


def test_build_enriched_failure_no_traceback() -> None:
    cfg = FailureDiagnosticsConfig()
    exc = RuntimeError("synthetic")
    exc.__traceback__ = None
    enriched = build_enriched_failure(RuntimeError, exc, None, config=cfg)
    assert enriched.summary.error_type == "RuntimeError"
    assert enriched.stack_frames == []
    assert enriched.diagnostics_mode == "lean"
    assert enriched.locals_by_frame is None


def test_build_enriched_failure_rich_includes_locals() -> None:
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")

    def inner() -> None:
        user = "alice"
        payload = {"password": "secret", "ok": 1}
        raise ValueError("boom")

    try:
        inner()
    except ValueError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.diagnostics_mode == "rich"
    assert enriched.locals_by_frame is not None
    all_locals = {k: v for block in enriched.locals_by_frame.values() for k, v in block["locals"].items()}
    assert "user" in all_locals
    assert "alice" in all_locals["user"]
    assert any("<redacted>" in v for v in all_locals.values() if isinstance(v, str))


def test_build_enriched_failure_top_level_secret_local_redacted() -> None:
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")

    def inner() -> None:
        api_token = "super-secret"
        raise RuntimeError("x")

    try:
        inner()
    except RuntimeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    redacted_any = any(
        block["locals"].get("api_token") == "<redacted>" for block in enriched.locals_by_frame.values()
    )
    assert redacted_any
    assert enriched.redaction_removed_keys >= 1


def test_build_enriched_failure_production_truncates_traceback() -> None:
    # Long exception message inflates formatted traceback
    msg = "x" * 20_000
    cfg = FailureDiagnosticsConfig(
        runtime_environment="production",
        failure_diagnostics="lean",
        production_traceback_cap=500,
    )
    try:
        raise ValueError(msg)
    except ValueError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.traceback_truncated is True
    assert len(enriched.summary.traceback_text) < len(msg) + 500
    assert "truncated" in enriched.summary.traceback_text.lower()


def test_primary_prefers_innermost_app_over_stdlib_leaf() -> None:
    """Leaf frame may be stdlib (e.g. json); primary should be caller in app code."""

    cfg = FailureDiagnosticsConfig(
        runtime_environment="development",
        failure_diagnostics="lean",
        app_roots=(os.path.abspath(os.path.dirname(__file__)),),
    )

    def trigger() -> None:
        json.loads("not valid json {{{")

    try:
        trigger()
    except json.JSONDecodeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.primary_frame_reason == "innermost_app"
    assert "test_diagnostics.py" in enriched.summary.filename.replace("\\", "/")
    assert enriched.summary.function == "trigger"
    kinds = [f["kind"] for f in enriched.stack_frames]
    assert "app" in kinds
    primary_rows = [f for f in enriched.stack_frames if f.get("is_primary")]
    assert len(primary_rows) == 1
    assert primary_rows[0]["kind"] == "app"


def test_max_traceback_chars_non_production() -> None:
    cfg = FailureDiagnosticsConfig(
        runtime_environment="development",
        failure_diagnostics="lean",
        max_traceback_chars=400,
    )
    msg = "y" * 5000
    try:
        raise RuntimeError(msg)
    except RuntimeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.traceback_truncated is True
    assert len(enriched.summary.traceback_text) <= 450


# ── T5: Deep exception chain (> 5 levels) doesn't crash ──────────────────────

def test_deep_exception_chain_does_not_blow_up() -> None:
    """Chains deeper than the 5-level cap in _build_exception_chain must not raise."""
    cfg = FailureDiagnosticsConfig()

    def raise_chain(depth: int) -> None:
        if depth == 0:
            raise ValueError("root cause")
        try:
            raise_chain(depth - 1)
        except Exception as inner:
            raise RuntimeError(f"level {depth}") from inner

    try:
        raise_chain(8)
    except RuntimeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.summary.error_type == "RuntimeError"
    assert enriched.summary.exception_chain  # non-empty string
    # Chain is truncated to 5 but must contain at least the outermost error
    assert "RuntimeError" in enriched.summary.exception_chain


# ── T6: story(app_roots=...) threads correctly to primary frame classifier ────

def test_story_app_roots_kwarg_classifies_caller_as_innermost_app() -> None:
    cap = CapturingRenderer()
    tests_dir = os.path.abspath(os.path.dirname(__file__))

    def raise_via_stdlib() -> None:
        json.loads("invalid {{{")

    with pytest.raises(json.JSONDecodeError):
        with story("S", renderers=[cap], app_roots=(tests_dir,)):
            with stage("Parse"):
                raise_via_stdlib()

    fail = next(e for e in cap.events if isinstance(e, FailureOccurred))
    assert fail.primary_frame_reason == "innermost_app"
    kinds = [f["kind"] for f in fail.stack_frames]
    assert "app" in kinds


def test_compressed_stack_summary_counts_app_frames() -> None:
    cfg = FailureDiagnosticsConfig()

    def a() -> None:
        b()

    def b() -> None:
        raise OSError("nope")

    try:
        a()
    except OSError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert "app frame" in enriched.compressed_stack_summary
    assert str(len(enriched.stack_frames)) in enriched.compressed_stack_summary


# ── Operand-type-mismatch exact_cause enhancement ─────────────────────────────

def test_exact_cause_names_operands_on_type_mismatch_in_rich_mode() -> None:
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")

    def inner() -> None:
        item = {"price": 29.99}
        promo = {"buy": 1, "get": 1}
        item["price"] * promo  # noqa: B018 - deliberately triggers TypeError

    try:
        inner()
    except TypeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    cause = enriched.summary.exact_cause
    assert "item['price']" in cause
    assert "29.99" in cause
    assert "promo" in cause
    assert "{'buy': 1, 'get': 1}" in cause
    assert "float" in cause and "dict" in cause
    # Must stay plain ASCII -- this string also flows into JSON/OTel, not just
    # a Unicode-aware console.
    assert all(ord(c) < 128 for c in cause)


def test_exact_cause_falls_back_to_generic_in_lean_mode() -> None:
    """The enhancement only fires in rich mode -- lean mode never inspects locals."""
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="lean")

    def inner() -> None:
        item = {"price": 29.99}
        promo = {"buy": 1, "get": 1}
        item["price"] * promo  # noqa: B018

    try:
        inner()
    except TypeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    assert enriched.summary.exact_cause.startswith("The statement `")


def test_exact_cause_redacts_operand_named_like_a_secret() -> None:
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")

    def inner() -> None:
        api_token = {"scope": "read"}
        1.5 * api_token  # noqa: B018

    try:
        inner()
    except TypeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    cause = enriched.summary.exact_cause
    assert "redacted" in cause
    assert "scope" not in cause


def test_exact_cause_falls_back_when_operand_not_a_simple_expression() -> None:
    """Function calls / complex expressions aren't safely resolvable -- the
    enhancement should still fire (naming the expression text) without
    evaluating anything, and never raise."""
    cfg = FailureDiagnosticsConfig(runtime_environment="development", failure_diagnostics="rich")

    def get_promo() -> dict:
        return {"buy": 1}

    def inner() -> None:
        price = 10.0
        price * get_promo()  # noqa: B018

    try:
        inner()
    except TypeError as e:
        enriched = build_enriched_failure(type(e), e, e.__traceback__, config=cfg)

    cause = enriched.summary.exact_cause
    assert "get_promo()" in cause
    assert "price" in cause
