from __future__ import annotations
import hashlib
import re
import shutil
import sys
import textwrap
from typing import Any

try:
    import typer
except ImportError:  # pragma: no cover
    typer = None

try:
    import structlog
except ImportError:  # pragma: no cover
    structlog = None

from . import RenderProtocol

_STORY_COLOR_PALETTE = (
    "CYAN", "MAGENTA", "YELLOW", "BLUE", "GREEN",
    "BRIGHT_CYAN", "BRIGHT_MAGENTA", "BRIGHT_YELLOW", "BRIGHT_BLUE", "BRIGHT_GREEN",
)


def _short_id(story_id: str | None) -> str:
    if not story_id:
        return "------"
    return story_id.replace("-", "")[:6]


def _color_for_id(story_id: str | None):
    if not story_id or typer is None:
        return None
    idx = int(hashlib.sha1(story_id.encode()).hexdigest(), 16) % len(_STORY_COLOR_PALETTE)
    return getattr(typer.colors, _STORY_COLOR_PALETTE[idx], None)


def _stdout_supports_unicode() -> bool:
    try:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        "▶✔❌".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class ConsoleRenderer:
    def __init__(
        self,
        *,
        log_renderer: Any = None,
        level_icons: dict[str, str] | None = None,
    ) -> None:
        if _stdout_supports_unicode():
            self._glyph_arrow = "▶"
            self._glyph_check = "✔"
            self._glyph_cross = "❌"
        else:
            self._glyph_arrow = ">"
            self._glyph_check = "[ok]"
            self._glyph_cross = "[FAIL]"
        # story_id -> indent level of that story's own Story started/ended lines
        self._story_base_indent: dict[str, int] = {}
        # story_id -> stack of currently open stage names, for indent depth
        self._stage_stacks: dict[str, list[str]] = {}

        # LogRecorded rendering: any callable matching structlog's renderer
        # signature (logger, name, event_dict) -> str. Defaults to structlog's
        # own default console style (colors auto-disabled on non-TTY) when the
        # optional `structlog` extra is installed; otherwise falls back to a
        # plain "LEVEL message key=value ..." line with no external dependency.
        if log_renderer is not None:
            self._log_renderer = log_renderer
        elif structlog is not None:
            self._log_renderer = structlog.dev.ConsoleRenderer(colors=_stdout_supports_unicode())
        else:
            self._log_renderer = None
        # level (lowercase) -> prefix string (e.g. an emoji), prepended to the
        # message before rendering. Empty by default -- the default style is
        # whatever `log_renderer` produces on its own.
        self._level_icons = level_icons or {}

    def _story_base(self, story_id: str) -> int:
        return self._story_base_indent.get(story_id, 0)

    def _open_stage_depth(self, story_id: str) -> int:
        return len(self._stage_stacks.get(story_id, []))

    @staticmethod
    def _indent(level: int) -> str:
        return "  " * max(0, level)

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
            try:
                print(text, end="\n" if nl else "")
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
                safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
                print(safe, end="\n" if nl else "")
            return
        try:
            typer.secho(text, fg=fg, bold=bold, nl=nl)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
            typer.secho(safe, fg=fg, bold=bold, nl=nl)

    def _label(self, label: str, value: str, *, label_fg=None, value_fg=None) -> None:
        self._secho(f"{label} ", fg=label_fg, bold=True, nl=False)
        self._secho(value, fg=value_fg)

    @staticmethod
    def _story_tag(event: object) -> tuple[str, object]:
        """Return a "[short_id]" tag for *event* plus a color shared by the whole
        story family (root + any sub-stories), so concurrent/nested stories can
        be told apart visually without relying on a tree layout."""
        story_id = getattr(event, "story_id", "") or ""
        root_id = getattr(event, "root_story_id", "") or story_id
        return f"[{_short_id(story_id)}]", _color_for_id(root_id)

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
            parent_id = getattr(event, "parent_story_id", None)
            if parent_id is not None and parent_id in self._story_base_indent:
                base = self._story_base(parent_id) + self._open_stage_depth(parent_id) + 1
            else:
                base = 0
            self._story_base_indent[event.story_id] = base
            tag, color = self._story_tag(event)
            self._secho(f"{self._indent(base)}{tag} ", fg=color, bold=True, nl=False)
            self._secho(f"{self._glyph_arrow} Story started: ", fg=self._success_color, bold=True, nl=False)
            self._secho(event.story_name, fg=self._success_value_color, bold=True)
            return

        if event_name == "StageStarted":
            base = self._story_base(event.story_id)
            stack = self._stage_stacks.setdefault(event.story_id, [])
            indent = self._indent(base + len(stack) + 1)
            stack.append(event.stage_name)
            tag, color = self._story_tag(event)
            self._secho(f"{indent}{tag} ", fg=color, bold=True, nl=False)
            self._secho(f"{self._glyph_arrow} Stage started: ", fg=self._success_color, bold=True, nl=False)
            self._secho(event.stage_name, fg=self._success_value_color)
            return

        if event_name == "StageCompleted":
            base = self._story_base(event.story_id)
            stack = self._stage_stacks.get(event.story_id, [])
            indent = self._indent(base + len(stack))
            if stack:
                stack.pop()
            tag, color = self._story_tag(event)
            self._secho(f"{indent}{tag} ", fg=color, bold=True, nl=False)
            self._secho(f"{self._glyph_check} Stage completed: ", fg=self._success_color, bold=True, nl=False)
            self._secho(
                f"{event.stage_name} ({event.duration_seconds:.3f}s)",
                fg=self._success_value_color,
            )
            return

        if event_name == "LogRecorded":
            base = self._story_base(event.story_id)
            indent = self._indent(base + self._open_stage_depth(event.story_id))
            tag, color = self._story_tag(event)
            self._secho(f"{indent}{tag} ", fg=color, bold=True, nl=False)

            if self._log_renderer is not None:
                icon = self._level_icons.get(event.level.lower(), "")
                event_dict: dict[str, Any] = {
                    "event": f"{icon}{event.message}" if icon else event.message,
                    "level": event.level.lower(),
                    "timestamp": event.timestamp.isoformat(timespec="seconds"),
                }
                if event.logger_name:
                    event_dict["logger"] = event.logger_name
                if event.stage_name:
                    event_dict["stage"] = event.stage_name
                event_dict.update(getattr(event, "fields", {}) or {})
                self._secho(self._log_renderer(None, event.logger_name, event_dict))
            else:
                level = event.level.upper()
                noisy = level in ("WARNING", "ERROR", "CRITICAL")
                level_color = self._failure_color if noisy else color
                message_color = self._failure_value_color if noisy else None
                stage_part = f" [{event.stage_name}]" if event.stage_name else ""
                icon = self._level_icons.get(event.level.lower(), "")
                self._secho(f"{level}{stage_part} {event.logger_name}: ", fg=level_color, bold=True, nl=False)
                self._secho(f"{icon}{event.message}", fg=message_color)
                for k, v in (getattr(event, "fields", None) or {}).items():
                    self._secho(f"  {k}={v!r}", fg=message_color)

            if event.exc_text:
                for line in event.exc_text.splitlines():
                    self._secho(f"  {line}", fg=self._failure_value_color)
            return

        if event_name == "FailureOccurred":
            base = self._story_base(event.story_id)
            indent = self._indent(base + self._open_stage_depth(event.story_id))
            tag, color = self._story_tag(event)
            self._secho(f"\n{indent}{tag} ", fg=color, bold=True, nl=False)
            self._secho(f"{self._glyph_cross} Failure detected", fg=self._failure_color, bold=True)
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
                "Stage timeline:",
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
            base = self._story_base(event.story_id)
            indent = self._indent(base + self._open_stage_depth(event.story_id))
            tag, color = self._story_tag(event)
            self._secho(f"\n{indent}{tag}", fg=color, bold=True)
            self._render_box(
                "LLM Debug",
                event.llm_analysis,
                border_fg=self._failure_color,
                text_fg=self._failure_value_color,
                heading_fg=self._failure_heading_color,
            )
            return

        if event_name == "StoryCompleted":
            indent = self._indent(self._story_base(event.story_id))
            tag, tag_color = self._story_tag(event)
            state = "SUCCESS" if event.success else "FAILED"
            color = self._success_color if event.success else self._failure_color
            value_color = self._success_value_color if event.success else self._failure_value_color
            self._secho(f"{indent}{tag} ", fg=tag_color, bold=True, nl=False)
            self._secho(f"{self._glyph_arrow} Story ended: ", fg=color, bold=True, nl=False)
            duration = getattr(event, "duration_seconds", 0.0)
            self._secho(f"{state} ({duration:.3f}s)", fg=value_color, bold=True)
            self._story_base_indent.pop(event.story_id, None)
            self._stage_stacks.pop(event.story_id, None)


__all__ = ["ConsoleRenderer"]
