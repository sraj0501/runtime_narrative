"""Tests for Phase 6.4 extended redaction: regex patterns and callback."""

from __future__ import annotations

import pytest

from runtime_narrative import story
from runtime_narrative.diagnostics import FailureDiagnosticsConfig
from runtime_narrative.events import FailureOccurred
from tests.conftest import CapturingRenderer


def _failure_event(renderer: CapturingRenderer) -> FailureOccurred:
    """Return the first FailureOccurred event from a capturing renderer."""
    return next(e for e in renderer.events if isinstance(e, FailureOccurred))


def _all_locals(failure: FailureOccurred) -> dict[str, str]:
    """Flatten locals_by_frame into a single key->value dict."""
    return {
        k: v
        for frame in (failure.locals_by_frame or {}).values()
        for k, v in frame["locals"].items()
    }


# ---------------------------------------------------------------------------
# 1. Pattern redaction
# ---------------------------------------------------------------------------


def test_pattern_redaction() -> None:
    """redact_patterns=("^internal_",) redacts internal_key but not user_id."""
    renderer = CapturingRenderer()
    config = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("^internal_",),
    )

    def failing() -> None:
        internal_key = "secret value"  # noqa: F841
        user_id = "u123"  # noqa: F841
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with story("s", renderers=[renderer], diagnostics_config=config):
            failing()

    failure = _failure_event(renderer)
    locs = _all_locals(failure)
    assert "internal_key" in locs, "internal_key should be present in captured locals"
    assert locs["internal_key"] == "<redacted>", "internal_key should be redacted by pattern"
    assert "user_id" in locs, "user_id should be present in captured locals"
    assert locs["user_id"] != "<redacted>", "user_id should NOT be redacted"


# ---------------------------------------------------------------------------
# 2. Callback redaction
# ---------------------------------------------------------------------------


def test_callback_redaction() -> None:
    """redact_callback=lambda k: k.startswith('corp_') redacts corp_data but not public_data."""
    renderer = CapturingRenderer()
    config = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_callback=lambda k: k.startswith("corp_"),
    )

    def failing() -> None:
        corp_data = "internal payload"  # noqa: F841
        public_data = "open value"  # noqa: F841
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with story("s", renderers=[renderer], diagnostics_config=config):
            failing()

    failure = _failure_event(renderer)
    locs = _all_locals(failure)
    assert "corp_data" in locs, "corp_data should be present in captured locals"
    assert locs["corp_data"] == "<redacted>", "corp_data should be redacted by callback"
    assert "public_data" in locs, "public_data should be present in captured locals"
    assert locs["public_data"] != "<redacted>", "public_data should NOT be redacted"


# ---------------------------------------------------------------------------
# 3. Pattern matching is case-insensitive
# ---------------------------------------------------------------------------


def test_pattern_case_insensitive() -> None:
    """redact_patterns=('SENSITIVE',) matches sensitive_field (lowercase in var name)."""
    renderer = CapturingRenderer()
    config = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("SENSITIVE",),
    )

    def failing() -> None:
        sensitive_field = "hidden data"  # noqa: F841
        safe_field = "visible data"  # noqa: F841
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with story("s", renderers=[renderer], diagnostics_config=config):
            failing()

    failure = _failure_event(renderer)
    locs = _all_locals(failure)
    assert "sensitive_field" in locs
    assert locs["sensitive_field"] == "<redacted>", "pattern should match case-insensitively"
    assert "safe_field" in locs
    assert locs["safe_field"] != "<redacted>"


# ---------------------------------------------------------------------------
# 4. Callback exception safety
# ---------------------------------------------------------------------------


def test_callback_exception_safety() -> None:
    """A callback that raises RuntimeError does NOT crash the story; key stays un-redacted."""

    def bad_callback(name: str) -> bool:
        raise RuntimeError("callback exploded")

    renderer = CapturingRenderer()
    config = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_callback=bad_callback,
    )

    def failing() -> None:
        normal_data = "should survive"  # noqa: F841
        raise ValueError("boom")

    # The story must complete without raising from the callback.
    with pytest.raises(ValueError):
        with story("s", renderers=[renderer], diagnostics_config=config):
            failing()

    failure = _failure_event(renderer)
    locs = _all_locals(failure)
    # Key should NOT be redacted because callback raised (returns False on error)
    assert "normal_data" in locs
    assert locs["normal_data"] != "<redacted>", (
        "key should not be redacted when callback raises"
    )


# ---------------------------------------------------------------------------
# 5. Existing keyword redaction still works when redact_patterns is set
# ---------------------------------------------------------------------------


def test_existing_keyword_redaction_unaffected_by_patterns() -> None:
    """The default 'password' keyword is still redacted even when redact_patterns is set."""
    renderer = CapturingRenderer()
    config = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("^internal_",),
    )

    def failing() -> None:
        password = "hunter2"  # noqa: F841
        safe_value = "visible"  # noqa: F841
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with story("s", renderers=[renderer], diagnostics_config=config):
            failing()

    failure = _failure_event(renderer)
    locs = _all_locals(failure)
    assert "password" in locs
    assert locs["password"] == "<redacted>", "default keyword 'password' must still be redacted"
    assert "safe_value" in locs
    assert locs["safe_value"] != "<redacted>"


# ---------------------------------------------------------------------------
# 6. merge() preserves and overrides new fields
# ---------------------------------------------------------------------------


def test_merge_preserves_redact_patterns() -> None:
    """merge() with no override keeps base.redact_patterns."""
    base = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("^internal_",),
    )
    merged = FailureDiagnosticsConfig.merge(base)
    assert merged.redact_patterns == ("^internal_",)


def test_merge_overrides_redact_patterns() -> None:
    """merge() with explicit redact_patterns replaces base value."""
    base = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("^old_",),
    )
    merged = FailureDiagnosticsConfig.merge(base, redact_patterns=("^new_",))
    assert merged.redact_patterns == ("^new_",)


def test_merge_preserves_redact_callback() -> None:
    """merge() with no override keeps base.redact_callback."""
    cb = lambda k: k.startswith("corp_")  # noqa: E731
    base = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_callback=cb,
    )
    merged = FailureDiagnosticsConfig.merge(base)
    assert merged.redact_callback is cb


def test_merge_overrides_redact_callback() -> None:
    """merge() with explicit redact_callback replaces base value."""
    cb_old = lambda k: False  # noqa: E731
    cb_new = lambda k: k.startswith("corp_")  # noqa: E731
    base = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_callback=cb_old,
    )
    merged = FailureDiagnosticsConfig.merge(base, redact_callback=cb_new)
    assert merged.redact_callback is cb_new


def test_merge_cross_field_independence() -> None:
    """Overriding redact_patterns leaves redact_callback intact and vice versa."""
    cb = lambda k: k.startswith("corp_")  # noqa: E731
    base = FailureDiagnosticsConfig(
        failure_diagnostics="rich",
        redact_patterns=("^internal_",),
        redact_callback=cb,
    )

    # Override only patterns — callback must be preserved.
    merged_p = FailureDiagnosticsConfig.merge(base, redact_patterns=("^other_",))
    assert merged_p.redact_patterns == ("^other_",)
    assert merged_p.redact_callback is cb

    # Override only callback — patterns must be preserved.
    cb2 = lambda k: False  # noqa: E731
    merged_c = FailureDiagnosticsConfig.merge(base, redact_callback=cb2)
    assert merged_c.redact_patterns == ("^internal_",)
    assert merged_c.redact_callback is cb2
