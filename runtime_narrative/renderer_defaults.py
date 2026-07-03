from __future__ import annotations

import os
import sys
from typing import IO

# Cache of already-opened rich-log file handles, keyed by path, so multiple
# calls to default_renderers() in the same process (e.g. separate Django sync
# and async middleware classes) share one open handle instead of racing to
# open the same path repeatedly.
_open_rich_log_files: dict[str, IO[str]] = {}


def _rich_log_file_path() -> str | None:
    return os.getenv("RUNTIME_NARRATIVE_RICH_LOG_FILE") or None


def _rich_log_console_enabled() -> bool:
    return os.getenv("RUNTIME_NARRATIVE_RICH_LOG_CONSOLE", "1").strip().lower() not in ("0", "false", "no")


def _open_rich_log_file(path: str) -> IO[str]:
    handle = _open_rich_log_files.get(path)
    if handle is None or handle.closed:
        handle = open(path, "a", encoding="utf-8")
        _open_rich_log_files[path] = handle
    return handle


def default_renderers() -> tuple:
    """Environment-driven default renderer selection, shared by every
    auto-instrumentation entry point (HTTP middleware, Django middleware,
    Celery tasks, gRPC interceptors) when no explicit ``renderers=`` is passed.

    Base selection (unchanged from prior versions -- no breaking change):

    - ``sys.stdout`` is a real TTY  -> ``ConsoleRenderer()`` to stdout (local dev).
    - otherwise (production / Docker / CI) -> ``JsonRenderer()`` to stdout.

    ``RUNTIME_NARRATIVE_RICH_LOG_FILE`` (path, optional):
        When set, a ``ConsoleRenderer`` writing the human-readable narrative is
        *added* on top of the base selection above -- so a non-interactive
        production process (JSON-only by default) also gets a rich,
        troubleshooting-friendly log file without losing the structured JSON
        stream. The file is opened once, in append mode, and kept open for
        the process lifetime.

    ``RUNTIME_NARRATIVE_RICH_LOG_CONSOLE`` (``"1"``/``"0"``, default ``"1"``):
        Only consulted when ``RUNTIME_NARRATIVE_RICH_LOG_FILE`` is set *and*
        stdout is a TTY. Set to ``"0"`` to stop also echoing the rich
        narrative to the terminal -- useful when you want it in the file only.
        Has no effect on the non-TTY (JSON) base selection.
    """
    is_tty = getattr(sys.stdout, "isatty", lambda: False)()
    rich_log_path = _rich_log_file_path()
    renderers: list[object] = []

    if is_tty:
        if rich_log_path is None or _rich_log_console_enabled():
            from .renderer.console import ConsoleRenderer
            renderers.append(ConsoleRenderer())
    else:
        from .renderer.json_renderer import JsonRenderer
        renderers.append(JsonRenderer())

    if rich_log_path is not None:
        from .renderer.console import ConsoleRenderer
        renderers.append(ConsoleRenderer(output=_open_rich_log_file(rich_log_path)))

    return tuple(renderers)


__all__ = ["default_renderers"]
