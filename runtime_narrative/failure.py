from __future__ import annotations

import traceback
from dataclasses import dataclass
from types import TracebackType


@dataclass
class FailureSummary:
    error_type: str
    error_message: str
    filename: str
    lineno: int
    function: str
    source_line: str
    exception_chain: str
    exact_cause: str
    traceback_text: str


def _build_exception_chain(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    depth = 0
    while current is not None and depth < 5:
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
        depth += 1
    return " <- ".join(parts)


def _infer_exact_cause(error_type: str, message: str, source_line: str) -> str:
    line = source_line.strip()
    if line.startswith("raise "):
        return f"The code explicitly raises {error_type} here with message: {message}"
    return f"The statement `{line}` raised {error_type}: {message}"


def summarize_exception(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> FailureSummary:
    extracted = traceback.extract_tb(tb) if tb else []
    if extracted:
        frame = extracted[-1]
        filename = frame.filename
        lineno = frame.lineno
        function = frame.name
        source_line = frame.line or "<source unavailable>"
    else:
        filename = "<unknown>"
        lineno = 0
        function = "<unknown>"
        source_line = "<source unavailable>"

    return FailureSummary(
        error_type=exc_type.__name__,
        error_message=str(exc),
        filename=filename,
        lineno=lineno,
        function=function,
        source_line=source_line,
        exception_chain=_build_exception_chain(exc),
        exact_cause=_infer_exact_cause(exc_type.__name__, str(exc), source_line),
        traceback_text="".join(traceback.format_exception(exc_type, exc, tb)),
    )
