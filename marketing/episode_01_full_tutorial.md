# Episode 1 recording script — From traceback to story

**Working title:** Python errors with context: runtime-narrative from zero to your first story  
**Target:** 30–35 minutes after editing  
**Format:** editor + terminal + your voice; no camera or slides required  
**Viewer outcome:** they can wrap a Python workflow in `story()` and `stage()`, read a narrated failure, use decorators, and recognize a nested story.

Use the [creator guide](youtube_creator_guide.md) for recording and editing setup. Record the five sections below as separate clips. The time ranges are planning targets, not promises; replace them with actual timestamps in the final YouTube description. Work from the repository root. Before recording, run `uv sync --group dev --extra console` and rehearse the commands once. Open the named files in your editor before pressing Record.

## Clip 1 — The problem and the result (about 4 minutes)

**Screen:** terminal, then `marketing/before_runtime_narrative.py`, then `examples/basic.py`. Make the terminal wide enough that the failure details do not wrap.

**Say:**

> "When a Python job fails, the traceback tells me where it stopped. It often does not tell me what the job had already finished or which business step was in progress. Here's a tiny customer import that fails while inserting records. First I'll run it without any narrative structure."

Run `uv run python marketing/before_runtime_narrative.py`. **Expected:** it prints three progress messages and a raw `ValueError: duplicate customer id` traceback; the command exits nonzero. Pause for a beat so the viewer can read it. Do not claim the traceback is useless; point out exactly what it lacks: a named stage timeline, completion state, and a concise failure summary.

**Say:**

> "The error is real and the line number is useful. What is missing is the execution story. Now I'll run another example with the same failure message, this time with named stages. The two files express the workflow differently; I am comparing the debugging experience, not claiming they are byte-for-byte identical."

Run `uv run python examples/basic.py`. **Expected:** two completed stages, `Insert Records` as the failed stage, a source snippet, stack summary, timeline, and `66%` progress. The example catches the exception after narration, so it does not add a second raw traceback. Point at those lines in that order. Avoid reading the whole output aloud.

**Transition:** "Let's build the mental model behind that output, starting with the smallest possible API."

## Clip 2 — Install and the two core concepts (about 5 minutes)

**Screen:** the [installation page](https://runtime-narrative.netlify.app/docs/installation.html), then `examples/success.py` in the editor. Show the command `pip install runtime-narrative` as text; the repo is already prepared, so do not spend recording time downloading dependencies.

**Say:**

> "`story()` names one unit of work: an import, an HTTP request, a background job. `stage()` names a step inside that work. They are Python context managers, so they wrap existing code rather than replacing your functions or logger. The core install is `pip install runtime-narrative`. In this repository I use `uv` only to run the included examples; it is not required for someone using the package in their own project."

Walk through `examples/success.py` slowly: `with story("Import Customers", total_stages=3)`, then three `with stage(...)` blocks. Point out that `stage()` needs an active story, that `total_stages=3` declares the expected count, and that normal Python exceptions still propagate unless the caller catches them. Do not introduce renderers or LLMs yet.

**Say:**

> "The names are the key design choice. Use names someone on call would recognize: `Load CSV`, `Validate Data`, `Insert Records`. The code inside each block remains your code. `runtime-narrative` records the boundaries and duration."

## Clip 3 — Read a successful story, then a failure (about 10 minutes)

**Screen:** editor above terminal, with `examples/success.py` visible. Run `uv run python examples/success.py`.

**Expected:** `Story started`, start/completion for each stage, `Inserted 2 records`, and `Story ended: SUCCESS`. Explain the story ID tag, stage durations, and successful completion. Durations can be near zero in this tiny example. The console's glyphs may be Unicode or ASCII depending on terminal encoding; the meaning is the same.

**Say:**

> "On success I can tell what ran and how long it took without writing six separate log statements. The `Inserted 2 records` line is the example's own `print`; the stage events around it come from the library."

Switch to `examples/basic.py`. Show the four decorators before running it: one `@runtime_narrative_story` on `run()`, three `@runtime_narrative_stage`s on helper functions. These are a second way to express the same story/stage boundaries; explain when decorators are convenient (existing functions) and when context managers are convenient (a subsection inside a function). Run `uv run python examples/basic.py`.

Pause on the output and explain, one at a time:

1. `Stage: Insert Records` identifies the business step that failed.
2. `Location` and `Code` point to the line that raised the error.
3. `Stack summary` compresses the call path; it is not an LLM response.
4. `Stage timeline` records two completed stages and one failed stage.
5. `Progress: 66% (2 / 3)` is based on completed versus registered stages in this example.

**Say:**

> "None of this required a model, API key, or external service. This diagnosis is the deterministic layer. The exception still propagates out of the story by default. In this demo, the outer `try/except` catches it after the failure has been narrated. In an application, the surrounding framework or caller can still handle it normally."

Pause and show the `try/except` at the bottom of `examples/basic.py`. Do **not** teach broad `except Exception: pass` as an application pattern; it is only there to keep a deliberate demo failure from printing an extra traceback.

**Transition:** "A story is useful for one job; nested stories show where the job called another unit of work."

## Clip 4 — Follow a nested call (about 6 minutes)

**Screen:** `examples/substory_db_call.py`. Point to the parent `async with story("POST /orders")`, `async with stage("Persist Order")`, and the helper's child `async with story(f"DB: {sql}")`. Then run `uv run python examples/substory_db_call.py`.

**Expected:** an indented parent/child tree and final lines showing the DB story's `parent_story_id`, shared `root_story_id`, and inherited renderers. Parent and child have **different story IDs**; the shared root links them. Do not say one ID is reused across the family.

**Say:**

> "I did not pass the parent ID into `execute_query`. The active story is carried in Python context. Opening a new story inside it creates a child, and the renderer can show the call tree. Each story still has its own timing and success result. This is useful when an API request calls a database helper or a job launches a subtask."

Point out the `async with` form. The sync and async APIs share the same story/stage model; async renderers need the async context path for awaited stage events. Keep the explanation to that one sentence and leave deep async integration for Episode 2.

## Clip 5 — What to try next and close (about 5 minutes)

**Screen:** `examples/diagnostics_config.py`, the [online docs](https://runtime-narrative.netlify.app/), then a terminal with a compact recap of the four commands. Do not run an LLM demo in Episode 1; it adds a model setup dependency and deserves its own episode.

**Say:**

> "The default failure detail is lean. If the error message and source line still do not explain the bug, rich diagnostics can capture locals. That is opt-in, and this example uses synthetic payment data plus explicit redaction rules. Notice the important boundary: redacting local variables does not rewrite arbitrary exception messages or log fields. Never record with real customer data or secrets on screen."

You may run `uv run python examples/diagnostics_config.py` as a preview. It prints lean, rich, and production examples in that order; zoom in on `card_number = <redacted>`, `cvv = <redacted>`, and `Diagnostics: lean` in production. Say that Episode 3 will explain how to configure this and add optional LLM analysis. If the first four clips have already reached 30 minutes, skip this run and keep the spoken preview.

**Close with:**

> "You can now add one `story()` around a unit of work, mark its steps with `stage()`, and read the success or failure timeline. Try the same thing on a small script you already own: give the story a meaningful name, add two stages, and deliberately raise a test error in the second stage. The package, working examples, and full docs are linked below. Next time I'll put the same model around a real FastAPI request."

## Recording command card

```text
uv sync --group dev --extra console                 # rehearse before recording
uv run python marketing/before_runtime_narrative.py # intentional nonzero exit
uv run python examples/basic.py                     # deliberate failure, caught by example
uv run python examples/success.py                   # successful context-manager workflow
uv run python examples/substory_db_call.py          # async parent/child stories
uv run python examples/diagnostics_config.py        # optional preview, synthetic data
```

## Ready-to-edit YouTube metadata

**Title:** Python errors with context: runtime-narrative from zero to your first story

**Description draft:**

> In this full tutorial, we turn a Python traceback into a named execution story. You'll use `story()` and `stage()`, compare context managers with decorators, read a narrated failure, and follow a nested DB call. The core walkthrough needs no LLM account or paid service. Recorded against runtime-narrative 1.5.4.  
>  
> Documentation: https://runtime-narrative.netlify.app/  
> Source and examples: https://github.com/sraj0501/runtime_narrative  
> Install: https://pypi.org/project/runtime-narrative/  
>  
> Chapters: add actual `00:00`-starting timestamps **after** editing.

**Thumbnail brief:** A two-column image using the website's dark theme. Left: a dense raw traceback with the word `WHERE?`; right: three named stage rows and one highlighted `Insert Records` failure with `WHAT FAILED`. Main text, no more than five words: **"TRACEBACK → STORY"**. A face photo is optional; a readable terminal comparison is more relevant to this video.

**End-screen text:** "Next: runtime-narrative in FastAPI" and the documentation URL. Add the actual Episode 2 link only once that video exists.
