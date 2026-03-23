from __future__ import annotations
import re
import shutil
import textwrap

try:
    import typer
except ImportError:  # pragma: no cover
    typer = None

from . import RenderProtocol


class ConsoleRenderer:
    @property
    def _success_color(self):
        if typer:
            return typer.colors.GREEN
        return None

    @property
    def _success_value_color(self):
        if typer:
            return getattr(typer.colors, "BRIGHT_WHITE", typer.colors.WHITE)
        return None

    @property
    def _failure_color(self):
        if typer:
            return getattr(typer.colors, "BRIGHT_RED", typer.colors.RED)
        return None

    @property
    def _failure_value_color(self):
        if typer:
            return getattr(typer.colors, "BRIGHT_YELLOW", typer.colors.YELLOW)
        return None

    @property
    def _failure_heading_color(self):
        if typer:
            return getattr(typer.colors, "BRIGHT_WHITE", typer.colors.WHITE)
        return None

    @property
    def _fix_heading_color(self):
        if typer:
            return getattr(typer.colors, "BRIGHT_GREEN", typer.colors.GREEN)
        return None

    @staticmethod
    def _secho(text: str, *, fg=None, bold: bool = False, nl: bool = True) -> None:
        if typer is None:
            if nl:
                print(text)
            else:
                print(text, end="")
            return
        typer.secho(text, fg=fg, bold=bold, nl=nl)

    def _label(self, label: str, value: str, *, label_fg=None, value_fg=None) -> None:
        self._secho(f"{label} ", fg=label_fg, bold=True, nl=False)
        self._secho(value, fg=value_fg)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        fence_languages = {"python", "bash", "json", "yaml", "yml", "text"}
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            line = re.sub(r"^#{1,6}\s*", "", line)
            line = re.sub(r"^\s*[-*+]\s+", "", line)
            line = re.sub(r"^\s*\d+[.)]\s+", "", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            if line.lower() in fence_languages:
                continue
            if line:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    @staticmethod
    def _is_heading_line(line: str) -> bool:
        normalized = line.strip().rstrip(":")
        if not normalized:
            return False
        known = {"exact why", "evidence", "targeted fix", "targetted fix", "code changes"}
        if normalized.lower() in known:
            return True
        if len(normalized.split()) <= 4 and re.match(r"^[A-Za-z][A-Za-z\s/-]*$", normalized):
            return True
        return False

    @staticmethod
    def _is_fix_heading_line(line: str) -> bool:
        normalized = line.strip().rstrip(":").lower()
        return normalized in {"targeted fix", "targetted fix", "code changes"}

    def _render_box(self, title: str, text: str, *, border_fg=None, text_fg=None, heading_fg=None) -> None:
        terminal_width = shutil.get_terminal_size((100, 20)).columns
        width = max(60, min(110, terminal_width - 2))
        inner = width - 2
        content_width = max(10, inner - 2)

        title_chunk = f" {title} "
        if len(title_chunk) < inner:
            top = "+" + title_chunk + ("-" * (inner - len(title_chunk))) + "+"
        else:
            top = "+" + ("-" * inner) + "+"
        bottom = "+" + ("-" * inner) + "+"

        self._secho(top, fg=border_fg, bold=True)
        plain_text = self._strip_markdown(text)
        lines = plain_text.splitlines()
        first_section = True
        for paragraph in lines:
            is_heading = self._is_heading_line(paragraph)
            if is_heading and not first_section:
                self._secho("|", fg=border_fg, bold=True, nl=False)
                self._secho(f" {' '.ljust(content_width)} ", fg=text_fg, nl=False)
                self._secho("|", fg=border_fg, bold=True)
            if is_heading:
                first_section = False
            is_fix_heading = self._is_fix_heading_line(paragraph)
            line_fg = heading_fg if is_heading else text_fg
            if is_fix_heading:
                line_fg = self._fix_heading_color or heading_fg
            line_bold = is_heading
            wrapped = textwrap.wrap(paragraph, width=content_width) or [""]
            for line in wrapped:
                self._secho("|", fg=border_fg, bold=True, nl=False)
                display_line = f">> {line}" if is_fix_heading else line
                self._secho(f" {display_line.ljust(content_width)} ", fg=line_fg, bold=line_bold, nl=False)
                self._secho("|", fg=border_fg, bold=True)
        self._secho(bottom, fg=border_fg, bold=True)

    def handle(self, event: object) -> None:
        event_name = event.__class__.__name__

        if event_name == "StoryStarted":
            self._secho("▶ Stage started: ", fg=self._success_color, bold=True, nl=False)
            self._secho(event.story_name, fg=self._success_value_color, bold=True)
            return

        if event_name == "StageStarted":
            self._secho("▶ Stage started: ", fg=self._success_color, bold=True, nl=False)
            self._secho(event.stage_name, fg=self._success_value_color)
            return

        if event_name == "StageCompleted":
            self._secho("✔ Stage completed: ", fg=self._success_color, bold=True, nl=False)
            self._secho(
                f"{event.stage_name} ({event.duration_seconds:.3f}s)",
                fg=self._success_value_color,
            )
            return

        if event_name == "FailureOccurred":
            self._secho("\n❌ Failure detected", fg=self._failure_color, bold=True)
            self._label("Story:", event.story_name, label_fg=self._failure_color, value_fg=self._failure_value_color)
            self._label("Stage:", event.stage_name, label_fg=self._failure_color, value_fg=self._failure_value_color)
            self._label(
                "Error:",
                f"{event.error_type} - {event.error_message}",
                label_fg=self._failure_color,
                value_fg=self._failure_value_color,
            )
            self._label(
                "Location:",
                f"{event.filename}:{event.lineno} ({event.function})",
                label_fg=self._failure_color,
                value_fg=self._failure_value_color,
            )
            self._label("Code:", event.source_line, label_fg=self._failure_color, value_fg=self._failure_value_color)
            self._label(
                "Diagnostics:",
                f"{getattr(event, 'diagnostics_mode', 'lean')} (primary: {getattr(event, 'primary_frame_reason', 'leaf')})",
                label_fg=self._failure_color,
                value_fg=self._failure_value_color,
            )
            snippet = getattr(event, "source_snippet", None)
            if snippet:
                self._secho("Context:", fg=self._failure_color, bold=True)
                for line in snippet.splitlines():
                    self._secho(f"  {line}", fg=self._failure_value_color)
            summary = getattr(event, "compressed_stack_summary", "")
            if summary:
                self._label(
                    "Stack summary:",
                    summary,
                    label_fg=self._failure_color,
                    value_fg=self._failure_value_color,
                )
            if getattr(event, "traceback_truncated", False):
                self._label(
                    "Traceback:",
                    "truncated for environment limits",
                    label_fg=self._failure_color,
                    value_fg=self._failure_value_color,
                )
            locals_by_frame = getattr(event, "locals_by_frame", None)
            if locals_by_frame:
                self._secho("Locals (rich diagnostics):", fg=self._failure_color, bold=True)
                for label, payload in locals_by_frame.items():
                    locs = payload.get("locals", {})
                    where = f"{payload.get('filename')}:{payload.get('lineno')} in {payload.get('function')}"
                    self._secho(f"  {label} — {where}", fg=self._failure_heading_color)
                    for k, v in locs.items():
                        self._secho(f"    {k} = {v}", fg=self._failure_value_color)
                removed = getattr(event, "redaction_removed_keys", 0)
                if removed:
                    self._label("Redacted keys:", str(removed), label_fg=self._failure_color, value_fg=self._failure_value_color)
            if not event.llm_analysis:
                self._label(
                    "What happened:",
                    event.exception_chain,
                    label_fg=self._failure_color,
                    value_fg=self._failure_value_color,
                )
                self._label(
                    "Why (exact):",
                    event.exact_cause,
                    label_fg=self._failure_color,
                    value_fg=self._failure_value_color,
                )
            if event.llm_analysis:
                self._secho("")
                self._render_box(
                    "LLM Debug",
                    event.llm_analysis,
                    border_fg=self._failure_color,
                    text_fg=self._failure_value_color,
                    heading_fg=self._failure_heading_color,
                )
            self._label(
                "Recent stages:",
                event.stage_timeline,
                label_fg=self._failure_color,
                value_fg=self._failure_value_color,
            )
            self._label(
                "Progress:",
                f"{event.progress_percent}% ({event.completed_stages} / {event.total_stages})",
                label_fg=self._failure_color,
                value_fg=self._failure_value_color,
            )
            return

        if event_name == "LLMAnalysisReady":
            self._secho("")
            self._render_box(
                "LLM Debug",
                event.llm_analysis,
                border_fg=self._failure_color,
                text_fg=self._failure_value_color,
                heading_fg=self._failure_heading_color,
            )
            return

        if event_name == "StoryCompleted":
            state = "SUCCESS" if event.success else "FAILED"
            color = self._success_color if event.success else self._failure_color
            value_color = self._success_value_color if event.success else self._failure_value_color
            self._secho("▶ Story ended: ", fg=color, bold=True, nl=False)
            self._secho(state, fg=value_color, bold=True)


__all__ = ["ConsoleRenderer"]
