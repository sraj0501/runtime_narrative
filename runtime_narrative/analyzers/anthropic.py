from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None  # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

from ..failure import FailureSummary

__all__ = ["AnthropicFailureAnalyzer"]

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class AnthropicFailureAnalyzer:
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("RUNTIME_NARRATIVE_MODEL", _DEFAULT_MODEL))
    timeout_seconds: float = 30.0
    max_tokens: int = 1024
    system_prompt: str = "You are an expert Python debugging assistant. Be concise and specific."

    def __post_init__(self) -> None:
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package is required for AnthropicFailureAnalyzer. "
                "Install it with: pip install 'runtime-narrative[anthropic]'"
            )
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it or pass api_key= explicitly."
            )

    def _build_messages(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> list[dict]:
        content = (
            "You are debugging a Python runtime stage failure.\n"
            "Respond with a single JSON object with exactly these four keys:\n"
            '  "exact_why"    — the exact mechanism that caused the failure (specific, not generic)\n'
            '  "evidence"     — specific evidence from the traceback and code that proves the cause\n'
            '  "targeted_fix" — the minimal change that fixes the issue\n'
            '  "code_changes" — edit-ready snippets with file path, old line, new line when possible\n'
            "Constraints:\n"
            "- Do not be generic. Point to the exact failing statement and mechanism.\n"
            "- Return ONLY valid JSON — no markdown fences, no extra text.\n\n"
            f"Story: {story_name}\n"
            f"Stage: {stage_name}\n"
            f"Error Type: {failure.error_type}\n"
            f"Error Message: {failure.error_message}\n"
            f"Location: {failure.filename}:{failure.lineno} ({failure.function})\n"
            f"Failing Code: {failure.source_line}\n"
            f"Exception Chain: {failure.exception_chain}\n"
            f"Progress: {progress_percent}%\n"
            f"Recent Stages: {stage_timeline}\n\n"
            "Traceback:\n"
            f"{failure.traceback_text[-4000:]}"
        )
        return [{"role": "user", "content": content}]

    def _parse_response(self, text: str) -> str:
        stripped = text
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
        if fence_match:
            stripped = fence_match.group(1).strip()
        try:
            data = json.loads(stripped)
            parts = []
            if "exact_why" in data:
                parts.append(f"## Exact Why\n{data['exact_why']}")
            if "evidence" in data:
                parts.append(f"## Evidence\n{data['evidence']}")
            if "targeted_fix" in data:
                parts.append(f"## Targeted Fix\n{data['targeted_fix']}")
            if "code_changes" in data:
                parts.append(f"## Code Changes\n{data['code_changes']}")
            return "\n\n".join(parts) if parts else text
        except Exception:
            return text

    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        client = _anthropic.Anthropic(api_key=self.api_key)
        messages = self._build_messages(
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
        )
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=messages,
                timeout=self.timeout_seconds,
            )
            text = response.content[0].text.strip()
        except Exception:
            return None
        return self._parse_response(text) or None

    async def analyze_failure_async(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        client = _anthropic.AsyncAnthropic(api_key=self.api_key)
        messages = self._build_messages(
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
        )
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=messages,
                timeout=self.timeout_seconds,
            )
            text = response.content[0].text.strip()
        except Exception:
            return None
        return self._parse_response(text) or None
