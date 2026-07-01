from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import IO


class JsonRenderer:
    """Renderer that emits one JSON object per event to a file-like output (default: stdout)."""

    def __init__(self, output: IO[str] | None = None, indent: int | None = None):
        self._output = output or sys.stdout
        self._indent = indent

    def _dump(self, data: dict) -> None:
        self._output.write(json.dumps(data, default=str, indent=self._indent) + "\n")
        if hasattr(self._output, "flush"):
            self._output.flush()

    def handle(self, event: object) -> None:
        event_name = event.__class__.__name__

        if event_name == "StoryStarted":
            self._dump({
                "event": "StoryStarted",
                "story_id": event.story_id,
                "story_name": event.story_name,
                "timestamp": event.timestamp.isoformat(),
                "parent_story_id": getattr(event, "parent_story_id", None),
                "root_story_id": getattr(event, "root_story_id", ""),
            })

        elif event_name == "StageStarted":
            self._dump({
                "event": "StageStarted",
                "story_id": event.story_id,
                "stage_name": event.stage_name,
                "timestamp": event.timestamp.isoformat(),
            })

        elif event_name == "StageCompleted":
            self._dump({
                "event": "StageCompleted",
                "story_id": event.story_id,
                "stage_name": event.stage_name,
                "duration_seconds": event.duration_seconds,
                "timestamp": event.timestamp.isoformat(),
                "root_story_id": getattr(event, "root_story_id", ""),
            })

        elif event_name == "LogRecorded":
            self._dump({
                "event": "LogRecorded",
                "story_id": event.story_id,
                "story_name": event.story_name,
                "root_story_id": event.root_story_id,
                "stage_name": event.stage_name,
                "level": event.level,
                "logger_name": event.logger_name,
                "message": event.message,
                "timestamp": event.timestamp.isoformat(),
                "exc_text": event.exc_text,
            })

        elif event_name == "FailureOccurred":
            payload = {
                "event": "FailureOccurred",
                "story_id": event.story_id,
                "story_name": event.story_name,
                "stage_name": event.stage_name,
                "error_type": event.error_type,
                "error_message": event.error_message,
                "location": {
                    "filename": event.filename,
                    "lineno": event.lineno,
                    "function": event.function,
                    "source_line": event.source_line,
                },
                "exception_chain": event.exception_chain,
                "exact_cause": event.exact_cause,
                "llm_analysis": event.llm_analysis,
                "stage_timeline": event.stage_timeline,
                "progress": {
                    "percent": event.progress_percent,
                    "completed_stages": event.completed_stages,
                    "total_stages": event.total_stages,
                },
                "timestamp": event.timestamp.isoformat(),
                "diagnostics_mode": getattr(event, "diagnostics_mode", "lean"),
                "primary_frame_reason": getattr(event, "primary_frame_reason", "leaf"),
                "stack_frames": getattr(event, "stack_frames", []),
                "source_snippet": getattr(event, "source_snippet", None),
                "compressed_stack_summary": getattr(event, "compressed_stack_summary", ""),
                "hidden_frame_count": getattr(event, "hidden_frame_count", 0),
                "traceback_truncated": getattr(event, "traceback_truncated", False),
                "locals_by_frame": getattr(event, "locals_by_frame", None),
                "redaction_removed_keys": getattr(event, "redaction_removed_keys", 0),
                "parent_story_id": getattr(event, "parent_story_id", None),
                "root_story_id": getattr(event, "root_story_id", ""),
            }
            if getattr(event, "traceback_text", None) is not None:
                payload["traceback_text"] = event.traceback_text
            self._dump(payload)

        elif event_name == "LLMAnalysisReady":
            self._dump({
                "event": "LLMAnalysisReady",
                "story_id": event.story_id,
                "story_name": event.story_name,
                "stage_name": event.stage_name,
                "llm_analysis": event.llm_analysis,
                "timestamp": event.timestamp.isoformat(),
            })

        elif event_name == "StoryCompleted":
            self._dump({
                "event": "StoryCompleted",
                "story_id": event.story_id,
                "story_name": event.story_name,
                "success": event.success,
                "progress": {
                    "percent": event.progress_percent,
                    "completed_stages": event.completed_stages,
                    "total_stages": event.total_stages,
                },
                "timestamp": event.timestamp.isoformat(),
                "duration_seconds": getattr(event, "duration_seconds", 0.0),
                "parent_story_id": getattr(event, "parent_story_id", None),
                "root_story_id": getattr(event, "root_story_id", ""),
            })


class RotatingJsonRenderer(JsonRenderer):
    """JsonRenderer that rotates the output file when it reaches a size limit.

    Rotation follows the same naming convention as ``logging.handlers.RotatingFileHandler``:
    the active log is ``path``; rotated logs are ``path.1``, ``path.2``, ... up to
    ``backup_count``.  When the active file reaches ``max_bytes``, it is renamed to
    ``path.1`` (shifting older files) and a new ``path`` is opened.

    Args:
        path: Destination file path.
        max_bytes: Rotate when the file exceeds this size (bytes). 0 disables rotation.
        backup_count: Number of rotated files to keep (oldest is deleted on overflow).
        indent: Passed to ``json.dumps``; ``None`` produces compact single-line output.
    """

    def __init__(
        self,
        path: str | os.PathLike,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        indent: int | None = None,
    ):
        self._path = str(path)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._file = open(self._path, "a", encoding="utf-8")
        super().__init__(output=self._file, indent=indent)

    def _should_rotate(self) -> bool:
        if self._max_bytes <= 0:
            return False
        try:
            return os.path.getsize(self._path) >= self._max_bytes
        except OSError:
            return False

    def _do_rotate(self) -> None:
        self._file.flush()
        self._file.close()
        for i in range(self._backup_count - 1, 0, -1):
            src = f"{self._path}.{i}"
            dst = f"{self._path}.{i + 1}"
            if os.path.exists(src):
                try:
                    os.replace(src, dst)
                except OSError:
                    pass
        try:
            os.replace(self._path, f"{self._path}.1")
        except OSError:
            pass
        self._file = open(self._path, "a", encoding="utf-8")
        self._output = self._file

    def _dump(self, data: dict) -> None:
        if self._should_rotate():
            self._do_rotate()
        super()._dump(data)


__all__ = ["JsonRenderer", "RotatingJsonRenderer"]
