from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from functools import partial
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..failure import FailureSummary


def _build_prompt(
    *,
    story_name: str,
    stage_name: str,
    failure: FailureSummary,
    stage_timeline: str,
    progress_percent: int,
    include_traceback_lines: int,
) -> str:
    traceback_lines = failure.traceback_text.strip().splitlines()
    traceback_excerpt = "\n".join(traceback_lines[-include_traceback_lines:])
    return (
        "You are debugging a Python runtime stage failure.\n"
        "Return concise markdown with exactly four sections:\n"
        "1) Exact Why\n"
        "2) Evidence\n"
        "3) Targeted Fix\n\n"
        "4) Code Changes\n\n"
        "Constraints:\n"
        "- Do not be generic.\n"
        "- Point to the exact failing statement and mechanism.\n"
        "- Mention assumptions only if uncertain.\n\n"
        "Code Changes format:\n"
        "- Provide minimal edit-ready snippets.\n"
        "- Include file path, old line, and new line when possible.\n"
        "- Prefer small targeted diffs over full-file rewrites.\n\n"
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
        f"{traceback_excerpt}\n"
    )


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

        return text or None


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

        return text or None

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
