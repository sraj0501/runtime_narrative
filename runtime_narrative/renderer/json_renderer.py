from __future__ import annotations

import json
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
            }
            if getattr(event, "traceback_text", None) is not None:
                payload["traceback_text"] = event.traceback_text
            self._dump(payload)

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
            })


__all__ = ["JsonRenderer"]
