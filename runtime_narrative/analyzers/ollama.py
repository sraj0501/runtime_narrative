from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from functools import partial
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..failure import FailureSummary


_SECTION_LABELS = {
    "exact_why": "Exact Why",
    "evidence": "Evidence",
    "targeted_fix": "Targeted Fix",
    "code_changes": "Code Changes",
}


def _parse_structured_response(text: str) -> str:
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_text = fence_match.group(1) if fence_match else text
    try:
        data = json.loads(json_text)
    except Exception:
        return text
    sections = [
        f"## {label}\n{data[key]}"
        for key, label in _SECTION_LABELS.items()
        if key in data
    ]
    if not sections:
        return text
    return "\n\n".join(sections)


def _build_prompt(
    *,
    story_name: str,
    stage_name: str,
    failure: FailureSummary,
    stage_timeline: str,
    progress_percent: int,
    include_traceback_lines: int,
    max_context_chars: int,
) -> str:
    instruction = (
        "You are debugging a Python runtime stage failure.\n"
        "Respond with a single JSON object with exactly these four keys:\n"
        "  \"exact_why\"    — the exact mechanism that caused the failure (specific, not generic)\n"
        "  \"evidence\"     — specific evidence from the traceback and code that proves the cause\n"
        "  \"targeted_fix\" — the minimal change that fixes the issue\n"
        "  \"code_changes\" — edit-ready snippets with file path, old line, new line when possible\n"
        "Constraints:\n"
        "- Do not be generic. Point to the exact failing statement and mechanism.\n"
        "- Return ONLY valid JSON — no markdown fences, no extra text.\n\n"
    )
    context_fields = (
        f"Story: {story_name}\n"
        f"Stage: {stage_name}\n"
        f"Error Type: {failure.error_type}\n"
        f"Error Message: {failure.error_message}\n"
        f"Location: {failure.filename}:{failure.lineno} ({failure.function})\n"
        f"Failing Code: {failure.source_line}\n"
        f"Exception Chain: {failure.exception_chain}\n"
        f"Progress: {progress_percent}%\n"
        f"Recent Stages: {stage_timeline}\n\n"
        "Traceback Excerpt:\n"
    )
    fixed_overhead = instruction + context_fields
    available = max_context_chars - len(fixed_overhead) - 200

    traceback_lines = failure.traceback_text.strip().splitlines()
    traceback_lines = traceback_lines[-include_traceback_lines:]

    if available <= 0:
        traceback_excerpt = "<traceback omitted — context budget exceeded>"
    else:
        full_traceback = "\n".join(traceback_lines)
        if len(full_traceback) > available:
            trimmed: list[str] = []
            char_count = 0
            for line in reversed(traceback_lines):
                line_len = len(line) + 1
                if char_count + line_len > available:
                    break
                trimmed.insert(0, line)
                char_count += line_len
            traceback_excerpt = "\n".join(trimmed)
        else:
            traceback_excerpt = full_traceback

    return fixed_overhead + traceback_excerpt + "\n"


@dataclass
class LLMFailureAnalyzer:
    """
    Failure analyzer for OpenAI-compatible endpoints.

    Works with any backend that serves the /v1/chat/completions API,
    including vLLM, llama.cpp (--server), LM Studio, Ollama (OpenAI mode), etc.

    Example::

        LLMFailureAnalyzer(
            model="llama3",
            endpoint="http://localhost:8000/v1/chat/completions",
        )
    """

    model: str
    endpoint: str
    timeout_seconds: float = 12.0
    include_traceback_lines: int = 30
    max_context_chars: int = 8000

    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        prompt = _build_prompt(
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
            include_traceback_lines=self.include_traceback_lines,
            max_context_chars=self.max_context_chars,
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (URLError, TimeoutError, Exception):
            return None

        try:
            parsed = json.loads(body)
            text = parsed["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

        return _parse_structured_response(text) or None

    async def analyze_failure_async(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        fn = partial(
            self.analyze_failure,
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
        )
        return await asyncio.to_thread(fn)


@dataclass
class OllamaFailureAnalyzer:
    """
    Failure analyzer using Ollama's native /api/generate endpoint.

    For OpenAI-compatible mode (Ollama >= 0.1.24), prefer LLMFailureAnalyzer
    with endpoint="http://localhost:11434/v1/chat/completions".

    Example::

        OllamaFailureAnalyzer(
            model="llama3",
            endpoint="http://localhost:11434/api/generate",
        )
    """

    model: str
    endpoint: str = "http://127.0.0.1:11434/api/generate"
    timeout_seconds: float = 12.0
    include_traceback_lines: int = 30
    max_context_chars: int = 8000

    def analyze_failure(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        prompt = _build_prompt(
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
            include_traceback_lines=self.include_traceback_lines,
            max_context_chars=self.max_context_chars,
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (URLError, TimeoutError, Exception):
            return None

        try:
            parsed = json.loads(body)
            text = parsed.get("response", "").strip()
        except Exception:
            return None

        return _parse_structured_response(text) or None

    async def analyze_failure_async(
        self,
        *,
        story_name: str,
        stage_name: str,
        failure: FailureSummary,
        stage_timeline: str,
        progress_percent: int,
    ) -> Optional[str]:
        fn = partial(
            self.analyze_failure,
            story_name=story_name,
            stage_name=stage_name,
            failure=failure,
            stage_timeline=stage_timeline,
            progress_percent=progress_percent,
        )
        return await asyncio.to_thread(fn)
