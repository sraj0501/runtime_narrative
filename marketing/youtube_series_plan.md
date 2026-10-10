# Long-form YouTube series: runtime-narrative in practice

Audience: Python developers who know functions and exceptions but have never used this library. Format: screen recording plus narration, no facecam required. Aim for one complete learner outcome per video, roughly 25–40 minutes each. The exact length should follow the demo, not a quota.

| Episode | Working title and target | What the viewer will build or understand | Repo material to show |
|---|---|---|---|
| 1 | **From traceback to story** · 30–35 min | Install, create a `story`, add `stage`s, read success/failure output, use decorators, and understand nested stories. | [`episode_01_full_tutorial.md`](episode_01_full_tutorial.md), `marketing/before_runtime_narrative.py`, `examples/success.py`, `examples/basic.py`, `examples/substory_db_call.py` |
| 2 | **Instrument a real FastAPI app** · 30–40 min | Add middleware, see request stories, stage an API route, attach an outcome, and follow a request through the DB helper. | `examples/fastapi_app/`, `examples/middleware_skip_if.py`, `examples/fastapi_ugly_traceback_demo.py` |
| 3 | **Failure diagnostics and optional LLM analysis** · 30–40 min | Compare lean/rich modes, explain redaction and production defaults, then run an optional local Ollama analysis and background mode. | `examples/diagnostics_config.py`, `examples/basic_ollama.py`, `examples/background_analysis.py`, `examples/anthropic_analyzer.py` |
| 4 | **Instrument existing code without rewriting it** · 25–35 min | Use function/class/module instrumentation and fold existing `logging` calls into the story stream. | `examples/narrative_class.py`, `examples/instrument_module.py`, `examples/auto_instrument.py`, `examples/logging_bridge.py`, `examples/structured_log_routing.py` |
| 5 | **Where the events go: renderers and persistence** · 30–40 min | Explain the event model; generate JSON, HTML and SQLite output; query the CLI; introduce OTel/Prometheus as downstream integrations. | `examples/html_report.py`, `examples/sqlite_persistence.py`, `examples/otel_tracing.py`, `runtime_narrative/events.py`, `website/docs/renderers.html` |
| 6 | **Test and operate a narrated workflow** · 25–35 min | Assert events with `StoryRecorder`, use task groups and explicit failure recording, and explain when `dry_run` and traceback suppression are appropriate. | `examples/story_recorder.py`, `examples/task_group.py`, `examples/saga_record_failure.py`, `examples/dry_run_mode.py`, `website/docs/testing.html` |

## Teaching rules across the series

- Show the actual file before each run; then pause on the specific output line that proves the point. Each episode should have at least one success path and one controlled failure or comparison.
- Say clearly when behavior is deterministic. LLM analysis is optional and its answer can be wrong; the story and diagnostics work without it.
- Do not imply `dry_run=True` prevents side effects: it suppresses exceptions raised inside stage bodies, but those bodies still execute.
- Do not imply all secrets are redacted. Rich-mode local-variable redaction does not sanitize arbitrary exception messages or `logging` extra fields.
- Use a real terminal when showing the human-readable console renderer. The FastAPI middleware selects JSON by default when stdout is not a TTY; the first episode's direct `story()` examples use the console renderer.
- Include the [live docs](https://runtime-narrative.netlify.app/), [GitHub repo](https://github.com/sraj0501/runtime_narrative), and [PyPI package](https://pypi.org/project/runtime-narrative/) in every description.

## Suggested production order

Record Episode 1 first and publish it after an Unlisted review. The existing [flagship script](youtube_flagship_script.md) can become a shorter overview later; it covers too many features too quickly for a first detailed tutorial. Use comments on Episode 1 to decide whether Episode 2 should spend more time on FastAPI setup or on reading trace output.
