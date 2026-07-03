from __future__ import annotations

from runtime_narrative.failure import summarize_exception


def test_summarize_exception_extracts_leaf_frame() -> None:
    def inner() -> None:
        raise KeyError("missing")

    try:
        inner()
    except KeyError as e:
        summary = summarize_exception(type(e), e, e.__traceback__)

    assert summary.error_type == "KeyError"
    assert "missing" in summary.error_message
    assert summary.function == "inner"
    assert "KeyError" in summary.exception_chain
    assert "inner" in summary.traceback_text


def test_exception_chain_respects_suppress_context() -> None:
    """`raise X from None` must stop the chain, matching Python's own traceback
    output. Naively following __context__ would surface unrelated exceptions
    (e.g. cleanup/cancellation noise) that the raiser deliberately hid."""
    def inner() -> None:
        try:
            raise ValueError("unrelated cleanup noise")
        except ValueError:
            raise TypeError("the real error") from None

    try:
        inner()
    except TypeError as e:
        summary = summarize_exception(type(e), e, e.__traceback__)

    assert summary.exception_chain == "TypeError: the real error"
    assert "ValueError" not in summary.exception_chain


def test_exception_chain_follows_explicit_cause_even_with_suppress_context() -> None:
    """`raise X from Y` always shows Y — __suppress_context__ only governs
    the implicit __context__ fallback, never an explicit __cause__."""
    def inner() -> None:
        try:
            raise ValueError("root cause")
        except ValueError as root:
            raise TypeError("wrapped") from root

    try:
        inner()
    except TypeError as e:
        summary = summarize_exception(type(e), e, e.__traceback__)

    assert summary.exception_chain == "TypeError: wrapped <- ValueError: root cause"
