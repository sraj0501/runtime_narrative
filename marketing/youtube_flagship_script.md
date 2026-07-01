# Flagship video script — "Your logs are lying to you"

Target length: 16-18 minutes. Format: screen recording + facecam voiceover (talking-head
optional at hook/CTA, screen-only for demos). Every demo command below is a real file in
this repo — run them exactly as written while recording, don't retype code on camera.

**Before recording — one-time setup:**
```bash
uv sync --group dev --extra console
```
The `console` extra gives you the colored `▶ / ✔ / ❌` glyphs (not the ASCII `>` / `[ok]` /
`[FAIL]` fallback) — record with it installed, it looks dramatically better on camera.
`--group dev` already pulls in `fastapi`, `uvicorn`, `pydantic`, and `typer` for the demo app.

Record from a real terminal window, not through a pipe or redirected output —
`RuntimeNarrativeMiddleware` auto-detects a non-interactive stdout (CI, a pipe) and switches
to `JsonRenderer` by default, so a real TTY is what gets you the colored console output in
Demo 4.

Working directory for every command: repo root.

**Fastest way to run this whole script live:** `uv run python marketing/run_flagship_demo.py`
walks through every beat below in order, pausing for Enter between each one so you can record
in a single take instead of juggling ~15 separate terminal commands. It starts/stops the
FastAPI server and fires the HTTP calls for you. The manual command list further down is for
scripting/editing reference, or if you'd rather drive each step by hand.

---

## 0:00–0:45 — Cold open (hook)

**[SCREEN: terminal, split or sequential]**

> Run: `uv run python marketing/before_runtime_narrative.py`

**VOICEOVER:**
> "It's 2am. Something broke in production. Here's what your logs tell you."

Let it print the bare traceback. Pause on it for 2 full seconds — don't talk over it.

> "A file path, a line number, and an exception name you already knew. It doesn't tell you
> *why* it happened, what ran right before it, or what to actually do about it. You're about
> to grep through logs for the next twenty minutes."

**[SCREEN: cut immediately]**

> Run: `uv run python examples/basic.py`

Let the full colored output print — story start, two green stage checkmarks, then the red
failure box with source snippet and stack summary.

> "Same exact bug. Same three lines of business logic. This is `runtime-narrative` — and by
> the end of this video you'll know exactly how to get this out of a one-line pip install."

---

## 0:45–2:15 — The problem, stated precisely

**[SCREEN: talking head or slides — no terminal]**

> "Two things are broken about how most of us debug Python in production.
>
> First: logging is manual and inconsistent. Every developer decides on their own what's
> worth a `logger.info` and what isn't, so the signal you need during an incident depends on
> whether someone remembered to log it six months ago.
>
> Second: even when you do have a traceback, it's context-free. It shows you the crash site,
> not the story leading up to it — what stage of the pipeline you were in, what completed
> successfully right before, how far through the job you got.
>
> `runtime-narrative` fixes both by giving you a structure to hang execution on: **stories**
> made of **stages**."

---

## 2:15–3:30 — What it is, install

**[SCREEN: README.md top of file, then terminal]**

> "A story is one logical unit of work — importing a file, handling a request, running a
> job. A stage is one step inside it. You wrap your existing code in `story()` and `stage()`
> context managers — no rewrite required."

> Run: `pip install runtime-narrative` (show it, don't actually need to re-run if already installed)

> "It's a normal PyPI package, zero required dependencies beyond `python-dotenv`. Everything
> else — colored console output, FastAPI middleware, OpenTelemetry, Prometheus, LLM failure
> analysis — is an optional extra, so you only pull in what you use."

---

## 3:30–6:00 — Demo 1: the core API, success and failure

**[SCREEN: open examples/success.py in editor, walk through it, then run]**

> Show the code first: `story("Import Customers", total_stages=3)` wrapping three `stage()`
> blocks. Point out: **plain context managers, nothing exotic.**

> Run: `uv run python examples/success.py`

> "On the happy path it's quiet — three green checkmarks, durations, done. This is the
> 'lean by default' philosophy: you're not drowning in log lines when nothing's wrong."

**[SCREEN: open examples/basic.py, point out `@runtime_narrative_stage` / `@runtime_narrative_story`]**

> "Prefer decorators over context managers? Same thing, wraps existing functions with zero
> body changes."

> Run: `uv run python examples/basic.py`

> Walk through the failure box on screen, reading it out loud almost verbatim:
> "Exact file and line. The actual source line that raised. A compressed stack summary —
> 4 app frames, versus however many frames of framework noise a raw traceback would've
> shown you. This is what I mean by 'the story leading up to the crash,' not just the crash."

---

## 6:00–8:30 — Demo 2: rich diagnostics with automatic secret redaction

**[SCREEN: open examples/diagnostics_config.py in editor]**

> "Sometimes the exception message alone isn't enough — you need to see the actual local
> variables at the failure site. That's opt-in, because local variables can contain secrets."

> Run: `uv run python examples/diagnostics_config.py`

> Walk through the three printed sections live:
> 1. Lean mode (default) — no locals.
> 2. Rich mode — `card_number`, `cvv` show up in the failure output, but **redacted** —
>    point at the `[REDACTED]` values on screen. "I told it to capture locals, and it
>    still refused to print the card number. Redaction is on by default for the obvious stuff
>    — password, token, secret, api_key — and you can extend it with your own key patterns,
>    or a regex, or a callback, like `card_number`/`cvv`/`_ref` here."
> 3. Production mode — traceback capped at 8,000 characters, and note in voiceover that
>    setting `RUNTIME_NARRATIVE_ENV=production` **forces lean mode** even if you asked for
>    rich, unless you explicitly opt back in with `RUNTIME_NARRATIVE_ALLOW_RICH_IN_PRODUCTION=1`.

> "That last one matters: this library defaults to the *safe* choice in production, and
> makes you opt into the risk explicitly."

---

## 8:30–11:30 — Demo 3: LLM-powered root cause and fix

**[SCREEN: terminal — confirm Ollama is running locally, e.g. `ollama list`, before recording]**

> "Everything so far is deterministic — no AI involved. This next part is optional, and it's
> the part that turns a stack trace into an actual answer."

> Run:
> `RUNTIME_NARRATIVE_MODEL=llama3 uv run python examples/basic_ollama.py`

> While it runs (there'll be a couple seconds of latency — don't cut it, let the viewer feel
> that it's a real local call): "This is pointed at a local Ollama model, completely free,
> nothing leaves your machine. It also works against any OpenAI-compatible endpoint, or
> Anthropic's Claude API if you want frontier-model quality — same interface either way."

> When the box renders, read the "Exact Why" and "Targeted Fix" sections out loud.

> "That's not a canned message. It's given the exact frame, the source snippet, and the stage
> timeline leading up to the failure, and asked for the specific cause and a specific fix —
> not 'check your database connection,' an actual diagnosis of *this* bug."

> Optional aside if time allows: mention `background_analysis=True` (point at
> `examples/background_analysis.py`) — "for latency-sensitive paths, the failure renders
> immediately and the LLM analysis streams in a few hundred milliseconds later as a separate
> event, so you're never blocking a request on a model call."

---

## 11:30–14:30 — Demo 4: production integration — FastAPI + call-tree tracing

**[SCREEN: open examples/fastapi_app/main.py, scroll through briefly]**

> "This is a real FastAPI app. Look at the middleware line —"

Point at:
```python
app.add_middleware(RuntimeNarrativeMiddleware, renderers=renderers, failure_analyzer=failure_analyzer)
```

> "One line. Every request becomes its own story automatically. Route handlers just declare
> stages — no context manager boilerplate in the handler itself."

> Run: `uv run python -m examples.fastapi_app.run`
> **[SCREEN: separate terminal]** `curl -X POST localhost:8000/customers -H "Content-Type: application/json" -d "{\"name\":\"Alice\",\"email\":\"bad-email\"}"`

> Show the validation failure rendered in the server terminal, tagged with the request's
> story.

> Small aside worth a sentence: "`renderers` here defaults to `None`, and the middleware picks
> `ConsoleRenderer` on a real terminal or `JsonRenderer` the moment stdout isn't a TTY — Docker,
> CI, a piped log collector — with zero config either way."

**[SCREEN: switch to examples/substory_db_call.py]**

> "Now the part I think is the most slept-on feature: sub-stories. If a story opens *inside*
> another already-active story — say, an API handler calling a DB helper — it auto-links as
> a child. No manual trace-ID plumbing."

> Run: `uv run python examples/substory_db_call.py`

> Point at the indented, `[short_id]`-tagged output tree on screen. "Same colored ID down the
> whole family, indented by nesting depth. This is a full call tree — for free — because
> `asyncio.Task` and thread-local context propagate it for you. It holds up under real
> concurrency: many callers sharing one DB helper never cross-link into each other's tree."

---

## 14:30–16:30 — Demo 5: bring your own renderer (ecosystem fly-through)

**[SCREEN: fast cuts, ~20-25 seconds per renderer — don't over-explain, this section is a montage]**

> "A renderer is just an object with a `handle(event)` method. Console is the default, but
> it's a drop-in list — here's the same failure, five different ways."

1. **JSON** — re-run the FastAPI app with `RUNTIME_NARRATIVE_JSON=1 uv run python -m examples.fastapi_app.run`, hit the same `curl` from Demo 4 — "same middleware, one env var, and now every event is a structured JSON line instead of colored text — for when you're shipping to a log aggregator instead of a terminal."
2. **HTML report** — `uv run python examples/html_report.py`, then open `examples_report.html` in a browser on screen — "a shareable, self-contained incident report, timeline bar chart included."
3. **OpenTelemetry** — `uv run python examples/otel_tracing.py` — "story becomes a root span, stage becomes a child span, if you're already on an OTel collector."
4. **Prometheus** — mention briefly, no need to run live — "duration histograms and failure counters, if metrics are your thing."
5. **Slack / webhook alerting** — `uv run python examples/alert_routing.py` — "fires only on failure, fans out to as many destinations as you want concurrently, filterable by exception type."

> "Same six lifecycle events, as many renderers listening as you want, mix and match.
> Nothing here required you to change how you write the story/stage code itself."

---

## 16:30–17:45 — Wrap-up and CTA

**[SCREEN: back to README.md top, or talking head]**

> "To recap: `story()` and `stage()` give your code structure without a rewrite. You get
> lean output when things work, forensic detail when they don't, optional LLM root-cause
> analysis when you want it, and it plugs into whatever you're already using downstream —
> console, JSON, OpenTelemetry, Prometheus, HTML, Slack.
>
> It's one `pip install runtime-narrative` away. Link's in the description, along with the
> full wiki covering every renderer and integration in depth.
>
> If this saved you twenty minutes of grepping through logs at some point in the future,
> that's the whole point — star the repo, it genuinely helps other people find it, and drop
> a comment if there's an integration you want covered next. See you in the next one."

**[END CARD: GitHub URL + PyPI URL + subscribe]**

---

## Reference sheet — exact commands used, in order

```bash
uv sync --group dev --extra console --extra fastapi
uv run python marketing/before_runtime_narrative.py
uv run python examples/basic.py
pip install runtime-narrative
uv run python examples/success.py
uv run python examples/basic.py
uv run python examples/diagnostics_config.py
RUNTIME_NARRATIVE_MODEL=llama3 uv run python examples/basic_ollama.py
uv run python -m examples.fastapi_app.run
curl -X POST localhost:8000/customers -H "Content-Type: application/json" -d "{\"name\":\"Alice\",\"email\":\"bad-email\"}"
uv run python examples/substory_db_call.py
RUNTIME_NARRATIVE_JSON=1 uv run python -m examples.fastapi_app.run
uv run python examples/html_report.py
uv run python examples/otel_tracing.py
uv run python examples/alert_routing.py
```

## Notes for editing

- Cold open and Demo 3 (LLM latency) are the two places where real wait time happens on
  camera — keep both, they build trust that this is a live, unscripted call rather than a
  canned mock.
- Lower-third text suggestions: `pip install runtime-narrative` (show once at ~2:45 and again
  on the end card), and the GitHub repo URL persistently in a corner during demos.
- If Ollama isn't available at record time, `examples/anthropic_analyzer.py` is a drop-in
  substitute for Demo 3 (requires `ANTHROPIC_API_KEY` and the `anthropic` extra) — same beat,
  same "Exact Why / Targeted Fix" box.
