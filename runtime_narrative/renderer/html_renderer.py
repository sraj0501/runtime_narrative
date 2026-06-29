from __future__ import annotations

import html
from pathlib import Path
from typing import Any

__all__ = ["HtmlReportRenderer"]

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #f6f8fa; color: #24292f; padding: 2rem; }
.card { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: .25rem; }
h2 { font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: #57606a; text-transform: uppercase; letter-spacing: .04em; }
.meta { font-size: .875rem; color: #57606a; margin-top: .25rem; }
.badge { display: inline-block; padding: .2em .6em; border-radius: 4px; font-size: .8rem; font-weight: 600; letter-spacing: .03em; }
.badge-success { background: #dafbe1; color: #1a7f37; }
.badge-fail    { background: #ffebe9; color: #cf222e; }
.stage-row { display: flex; align-items: center; gap: .75rem; padding: .5rem 0; border-bottom: 1px solid #f0f0f0; }
.stage-row:last-child { border-bottom: none; }
.stage-name { flex: 0 0 220px; font-size: .875rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stage-bar-wrap { flex: 1; background: #f0f0f0; border-radius: 4px; height: 12px; overflow: hidden; }
.stage-bar { height: 100%; border-radius: 4px; }
.bar-ok   { background: #2da44e; }
.bar-fail { background: #cf222e; }
.stage-dur { flex: 0 0 60px; text-align: right; font-size: .8rem; color: #57606a; }
.stage-status { flex: 0 0 18px; text-align: center; font-size: .85rem; }
.failure-block { background: #ffebe9; border: 1px solid #ffcecb; border-radius: 6px; padding: 1rem; }
.failure-block h3 { font-size: .9rem; font-weight: 600; margin-bottom: .5rem; color: #cf222e; }
.kv { font-size: .875rem; margin-bottom: .3rem; }
.kv b { color: #24292f; }
pre { font-family: ui-monospace, monospace; font-size: .8rem; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: .75rem; overflow-x: auto; white-space: pre-wrap; margin-top: .75rem; }
.llm-block { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 1rem; margin-top: 1rem; }
.llm-block h3 { font-size: .9rem; font-weight: 600; margin-bottom: .5rem; color: #0969da; }
"""


def _e(v: Any) -> str:
    return html.escape(str(v) if v is not None else "")


class HtmlReportRenderer:
    """Renderer that writes a self-contained HTML report on StoryCompleted.

    Usage::

        async with story("My Pipeline", renderers=[HtmlReportRenderer("report.html")]):
            ...
    """

    def __init__(
        self,
        path: str | Path,
        *,
        open_browser: bool = False,
    ) -> None:
        self._path = Path(path)
        self._open_browser = open_browser
        self._events: list[Any] = []

    def handle(self, event: object) -> None:
        self._events.append(event)
        if type(event).__name__ == "StoryCompleted":
            self._write()

    def _write(self) -> None:
        self._path.write_text(self._render(), encoding="utf-8")
        if self._open_browser:
            import webbrowser
            webbrowser.open(self._path.as_uri())

    def _render(self) -> str:
        started = next((e for e in self._events if type(e).__name__ == "StoryStarted"), None)
        completed = next((e for e in self._events if type(e).__name__ == "StoryCompleted"), None)
        failure = next((e for e in self._events if type(e).__name__ == "FailureOccurred"), None)
        llm_ready = next((e for e in self._events if type(e).__name__ == "LLMAnalysisReady"), None)

        stage_pairs: list[tuple[Any, Any]] = []
        starts: dict[str, Any] = {}
        for e in self._events:
            if type(e).__name__ == "StageStarted":
                starts[e.stage_name] = e
            elif type(e).__name__ == "StageCompleted":
                stage_pairs.append((starts.get(e.stage_name), e))

        story_name = _e(getattr(started, "story_name", "Story")) if started else "Story"
        success = getattr(completed, "success", True) if completed else True

        total_dur = 0.0
        if started and completed:
            ts = getattr(started, "timestamp", None)
            tc = getattr(completed, "timestamp", None)
            if ts and tc:
                total_dur = (tc - ts).total_seconds()

        max_dur = max((getattr(c, "duration_seconds", 0) or 0 for _, c in stage_pairs), default=1.0) or 1.0

        badge_cls = "badge-success" if success else "badge-fail"
        badge_txt = "SUCCESS" if success else "FAILED"

        stages_html = ""
        for _, comp in stage_pairs:
            dur = getattr(comp, "duration_seconds", 0) or 0
            pct = max(1, int(dur / max_dur * 100))
            failed = (
                failure is not None
                and getattr(failure, "stage_name", None) == comp.stage_name
            )
            bar_cls = "bar-fail" if failed else "bar-ok"
            icon = "✗" if failed else "✓"
            stages_html += (
                f'<div class="stage-row">'
                f'<span class="stage-name">{_e(comp.stage_name)}</span>'
                f'<div class="stage-bar-wrap">'
                f'<div class="stage-bar {bar_cls}" style="width:{pct}%"></div>'
                f'</div>'
                f'<span class="stage-dur">{dur:.3f}s</span>'
                f'<span class="stage-status">{icon}</span>'
                f'</div>\n'
            )

        failure_html = ""
        if failure:
            tb = _e(getattr(failure, "traceback_text", "") or "")
            llm_text = (
                _e(getattr(failure, "llm_analysis", None))
                or (_e(getattr(llm_ready, "llm_analysis", None)) if llm_ready else "")
            )
            llm_block = (
                f'<div class="llm-block"><h3>LLM Analysis</h3><pre>{llm_text}</pre></div>'
                if llm_text
                else ""
            )
            failure_html = f"""
<div class="card">
  <h2>Failure Detail</h2>
  <div class="failure-block">
    <h3>{_e(failure.error_type)}: {_e(failure.error_message)}</h3>
    <p class="kv"><b>Stage:</b> {_e(failure.stage_name)}</p>
    <p class="kv"><b>Location:</b> {_e(failure.filename)}:{_e(failure.lineno)} ({_e(failure.function)})</p>
    <p class="kv"><b>Code:</b> <code>{_e(failure.source_line)}</code></p>
    <pre>{tb}</pre>
  </div>
  {llm_block}
</div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Story: {story_name}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="card">
  <h1>{story_name} <span class="badge {badge_cls}">{badge_txt}</span></h1>
  <p class="meta">Duration: {total_dur:.3f}s &nbsp;·&nbsp; {len(stage_pairs)} stage(s)</p>
</div>
<div class="card">
  <h2>Stage Timeline</h2>
  {stages_html or "<p class='meta'>No stages recorded.</p>"}
</div>
{failure_html}
</body>
</html>"""
