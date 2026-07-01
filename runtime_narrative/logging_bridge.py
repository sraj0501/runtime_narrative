from __future__ import annotations

import logging
from datetime import datetime

from .context import current_stage_stack, current_story
from .events import LogRecorded

_STANDARD_LOG_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message",
    "asctime",
}


def _extract_extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Return caller-supplied `extra={...}` fields from a LogRecord.

    Anything set via `logger.warning("msg", extra={"order_id": "..."})` shows
    up as extra attributes on the record; standard LogRecord attributes are
    excluded so only the caller's own fields remain.
    """
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_LOG_RECORD_ATTRS}


class NarrativeLogHandler(logging.Handler):
    """Routes captured stdlib log records into the active story's event pipeline.

    Attach to any logger to fold its output into the same renderers already
    consuming story()/stage() events, instead of a second, disconnected log
    stream::

        logging.getLogger().addHandler(NarrativeLogHandler(level=logging.WARNING))

    Each captured record is emitted as a ``LogRecorded`` event carrying the
    active story_id/root_story_id/stage_name, so a renderer can show which
    call a log line belongs to. When no story is active, records are passed
    to ``fallback`` (if given) so logs outside a story() are never dropped.
    """

    def __init__(self, level: int = logging.WARNING, fallback: logging.Handler | None = None) -> None:
        super().__init__(level=level)
        self._fallback = fallback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            runtime = current_story.get()
            if runtime is None:
                if self._fallback is not None:
                    self._fallback.emit(record)
                return
            stack = current_stage_stack.get()
            runtime.emit(
                LogRecorded(
                    story_id=runtime.story_id,
                    story_name=runtime.name,
                    root_story_id=runtime.root_story_id,
                    stage_name=stack[-1].name if stack else "",
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    timestamp=datetime.fromtimestamp(record.created),
                    exc_text=self.format(record) if record.exc_info else None,
                    fields=_extract_extra_fields(record),
                )
            )
        except Exception:
            self.handleError(record)


__all__ = ["NarrativeLogHandler"]
