"""Render a narrated, animated, captioned YouTube tutorial from repo examples.

Run on Windows with the bundled workspace Python (Pillow) and FFmpeg:
    python marketing/build_episode_01_video.py

The export is deliberately ignored by Git because an MP4 is large. This source
file is the editable video project: change a scene, then render again.
"""

from __future__ import annotations

import json
import math
import subprocess
import textwrap
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "marketing" / "video_outputs" / "episode_01"
FRAMES = OUT / "frames"
W, H = 1280, 720
FPS = 30

BG = "#0b1020"
PANEL = "#141d31"
PANEL2 = "#101827"
WHITE = "#f1f5ff"
MUTED = "#9eacc5"
CYAN = "#4de1d4"
BLUE = "#6fa8ff"
AMBER = "#ffcd70"
RED = "#ff7788"
GREEN = "#79e2a3"
FONT_DIR = Path("C:/Windows/Fonts")
REG = FONT_DIR / "segoeui.ttf"
BOLD = FONT_DIR / "segoeuib.ttf"
MONO = FONT_DIR / "consola.ttf"


# Each text item is narrated as a separate audio unit and becomes a precisely
# timed caption. Visual text is intentionally concise enough for 720p playback.
SCENES = [
    {
        "chapter": "01 / THE PROBLEM", "title": "Python errors need a timeline",
        "subtitle": "From a bare traceback to a readable execution story",
        "kind": "hero", "items": ["WHERE did it fail?", "WHAT had finished?", "WHAT should I inspect?"],
        "say": [
            "When a Python job fails, the traceback gives you a file and a line number. That is useful, but it is only part of the story.",
            "For a multi step workflow, I also want to know what already finished, which named operation failed, and how far the job got.",
            "In this tutorial we will add that context to a small customer import, then follow a nested database call. Everything in the core demo runs locally, without an AI service.",
        ],
    },
    {
        "chapter": "01 / THE PROBLEM", "title": "The familiar traceback",
        "subtitle": "A deliberate failure in marketing/before_runtime_narrative.py",
        "kind": "terminal", "items": [
            "$ python marketing/before_runtime_narrative.py",
            "Loading CSV...", "Validating data...", "Inserting records...", "Traceback (most recent call last):",
            "  ... in insert", '    raise ValueError("duplicate customer id")',
            "ValueError: duplicate customer id",
        ],
        "say": [
            "Here is the baseline example. It loads a tiny list of customers, validates it, and deliberately raises a duplicate customer ID error during insertion.",
            "The traceback correctly points to the failing line. However, the progress messages are unstructured, so they are harder to scan or combine across a larger application.",
            "Now let us ask a more operational question: which steps completed, and can the error report name the step that failed?",
        ],
    },
    {
        "chapter": "01 / THE PROBLEM", "title": "What the traceback leaves open",
        "subtitle": "The gap is execution context, not the exception itself",
        "kind": "cards", "items": ["Named stage", "Completed work", "Progress", "Short diagnosis"],
        "say": [
            "A line number tells us where Python raised the exception. It does not automatically give us a timeline of named business steps.",
            "We can write custom log statements around every step, but that takes maintenance, and the output format often changes from one job to another.",
            "Runtime Narrative gives those boundaries a consistent model: one story around the unit of work, and stages inside it. We will see exactly what that means in code.",
        ],
    },
    {
        "chapter": "01 / THE PROBLEM", "title": "The same failure, now as a story",
        "subtitle": "Two completed stages; the third stage failed",
        "kind": "timeline", "items": ["Load CSV|done", "Validate Data|done", "Insert Records|failed"],
        "say": [
            "The instrumented example still raises Value Error, duplicate customer ID. Runtime Narrative adds a named stage timeline around it.",
            "Load CSV completed. Validate Data completed. Insert Records failed. In this three stage example, the report shows two of three stages complete, or sixty six percent.",
            "The comparison is about the debugging experience. The two example files express the workflow differently; I am not claiming they are identical source code.",
        ],
    },
    {
        "chapter": "02 / THE MODEL", "title": "Our route through the API",
        "subtitle": "One small example, then one failure, then a nested call",
        "kind": "steps", "items": ["1  Install", "2  story() + stage()", "3  Read success", "4  Read failure", "5  Follow a child story"],
        "say": [
            "We will start with the two core context managers, story and stage. Then we will compare a successful run with a deliberate failure.",
            "After that, we will use decorators around existing functions and look at a child story inside an API request.",
            "I will leave optional AI analysis and production integrations for later videos. The goal here is a clear mental model you can use in your own script today.",
        ],
    },
    {
        "chapter": "02 / THE MODEL", "title": "Install the core package",
        "subtitle": "No account, key, or paid service for the core walkthrough",
        "kind": "terminal", "items": [
            "$ pip install runtime-narrative", "", "# In the source repository:",
            "$ uv sync --group dev --extra console", "$ uv run python examples/success.py",
        ],
        "say": [
            "For your own Python project, install the package with pip install runtime narrative. The package name uses a hyphen.",
            "The examples in this repository use U V for dependency management. That is a convenience for running the source checkout, not a requirement for users of the package.",
            "The core example needs no model credentials. We will begin with the successful import in examples slash success dot py.",
        ],
    },
    {
        "chapter": "02 / THE MODEL", "title": "A story names the whole job",
        "subtitle": "Choose a name someone debugging the job would recognize",
        "kind": "code", "items": [
            "from runtime_narrative import story, stage", "",
            'with story("Import Customers", total_stages=3):',
            '    with stage("Load CSV"):', '        rows = ["alice", "bob"]',
            "    # more stages follow...",
        ],
        "say": [
            "The outer story names one unit of work. Here, that is Import Customers. In another application, it might be an HTTP request or a background job.",
            "Total stages tells the renderer that we expect three steps, so progress has a useful denominator.",
            "This is an ordinary Python context manager. It wraps your existing code. It does not replace your functions, your logger, or normal exception handling.",
        ],
    },
    {
        "chapter": "02 / THE MODEL", "title": "Stages name the steps",
        "subtitle": "Put the work you want timed and reported inside each block",
        "kind": "code", "items": [
            'with story("Import Customers", total_stages=3):',
            '    with stage("Load CSV"):', '        rows = ["alice", "bob"]',
            '    with stage("Validate Data"):', '        if not rows: raise ValueError("No rows found")',
            '    with stage("Insert Records"):', '        print(f"Inserted {len(rows)} records")',
        ],
        "say": [
            "Inside the story, each stage names a meaningful step. The names matter because they become the timeline someone reads after a run.",
            "Choose phrases like Load CSV, Validate Data, and Insert Records, rather than vague names like step one or do work.",
            "A stage needs an active story. Its body is still your Python code. If that body raises an exception, the stage can report failure while the exception continues outward.",
        ],
    },
    {
        "chapter": "03 / SUCCESS", "title": "Run the successful example",
        "subtitle": "examples/success.py uses story() and stage() directly",
        "kind": "terminal", "items": [
            "$ uv run python examples/success.py", "Story started: Import Customers",
            "  Stage completed: Load CSV", "  Stage completed: Validate Data",
            "Inserted 2 records", "  Stage completed: Insert Records",
            "Story ended: SUCCESS",
        ],
        "say": [
            "The first run succeeds. Notice how the story starts, each named stage starts and completes, and then the story ends successfully.",
            "The line Inserted two records is the example's own print statement. The surrounding stage events come from Runtime Narrative.",
            "The actual console output includes timestamps, short story identifiers, and durations. I have shortened it on this slide so we can focus on the structure. Tiny examples may show durations near zero.",
        ],
    },
    {
        "chapter": "03 / SUCCESS", "title": "Read the output in layers",
        "subtitle": "A concise, scan-friendly hierarchy",
        "kind": "cards", "items": ["Story = job", "Stage = step", "Duration = time", "Status = result"],
        "say": [
            "Read the output from the outside in. The story is the job we care about, and the stages are the steps inside it.",
            "Each stage gets a result and a duration. The story gets its own final result. That gives a compact answer to what ran and how long it took.",
            "You can keep your normal application output alongside these events. Runtime Narrative is adding structure to the workflow, not asking you to remove all other logs.",
        ],
    },
    {
        "chapter": "03 / SUCCESS", "title": "Context manager or decorator?",
        "subtitle": "Both express the same story and stage boundaries",
        "kind": "split", "items": [
            "CONTEXT MANAGER|with story(\"Import\"):\n    with stage(\"Load CSV\"):\n        rows = load_csv()",
            "DECORATOR|@runtime_narrative_stage(\"Load CSV\")\ndef load_csv():\n    ...",
        ],
        "say": [
            "Context managers fit a subsection inside a function. You can mark only the block of work that deserves a stage name.",
            "Decorators fit existing functions. The basic failure example uses one story decorator on run, and a stage decorator on each helper.",
            "Pick whichever makes your code clearer. In either form, the important decision is where the boundary sits and what human readable name you give it.",
        ],
    },
    {
        "chapter": "04 / FAILURE", "title": "Now force a real failure",
        "subtitle": "examples/basic.py deliberately raises in Insert Records",
        "kind": "code", "items": [
            '@runtime_narrative_stage("Insert Records")',
            'def insert(rows: list[str]) -> None:',
            '    raise ValueError("duplicate customer id")', "",
            '@runtime_narrative_story("Import Customers")',
            'def run() -> None:',
            '    rows = load_csv(); validate(rows); insert(rows)',
        ],
        "say": [
            "This example intentionally fails in the insert function. Its stage decorator names that function's work Insert Records.",
            "The run function has a story decorator. It calls the load, validate, and insert helpers in sequence, just as a small real import might.",
            "The failure is not simulated by the renderer. Python actually raises a Value Error, and the library observes it at the stage and story boundaries.",
        ],
    },
    {
        "chapter": "04 / FAILURE", "title": "The failure report",
        "subtitle": "Condensed from the actual console output of examples/basic.py",
        "kind": "terminal", "items": [
            "$ uv run python examples/basic.py", "[FAIL] Failure detected", "Story: Import Customers",
            "Stage: Insert Records", "Error: ValueError - duplicate customer id",
            'Code: raise ValueError("duplicate customer id")',
            "Progress: 66% (2 / 3)", "Story ended: FAILED",
        ],
        "say": [
            "Here is the condensed report. The story is Import Customers. The failed stage is Insert Records. The exception is Value Error, duplicate customer ID.",
            "The full output also shows the source location, code context, a stack summary, the stage timeline, and progress. None of those require an AI model.",
            "For this example, two of three stages completed before the failure. The progress line reports sixty six percent, followed by two out of three.",
        ],
    },
    {
        "chapter": "04 / FAILURE", "title": "Three useful views of one error",
        "subtitle": "Location, timeline, and progress answer different questions",
        "kind": "cards", "items": ["WHERE?\nSource line", "WHEN?\nStage timeline", "HOW FAR?\n2 of 3 complete"],
        "say": [
            "The source line answers where the error was raised. The stage timeline answers what happened before it. Progress answers how far this specific workflow got.",
            "The stack summary compresses the application call path, but it does not claim to discover a hidden root cause. In this example, the code explicitly raises the Value Error shown on screen.",
            "This distinction matters. The deterministic report organizes facts already available at runtime. Optional model analysis is a separate feature and a separate decision.",
        ],
    },
    {
        "chapter": "04 / FAILURE", "title": "Exceptions still propagate",
        "subtitle": "The surrounding application keeps control of handling",
        "kind": "code", "items": [
            "try:", "    run()", "except Exception:",
            "    pass  # deliberate demo failure only", "",
            "# Your application should handle or re-raise", "# exceptions according to its own policy.",
        ],
        "say": [
            "Runtime Narrative reports the failure, but it does not silently turn that failure into success. The exception still leaves the story unless something outside catches it.",
            "At the bottom of this demonstration file, a broad except catches the deliberate failure so the video can show one clean report without a second traceback.",
            "That except and pass is only for this controlled demo. In an application, let your framework or your own error policy decide whether to handle, retry, or re raise.",
        ],
    },
    {
        "chapter": "05 / NESTING", "title": "One request can contain another story",
        "subtitle": "A parent API request calls a child database helper",
        "kind": "tree", "items": ["POST /orders", "Validate Input", "Persist Order", "DB: INSERT INTO orders ...", "Acquire Connection", "Execute Query", "Notify"],
        "say": [
            "A real workflow often calls another unit of work. Imagine an API request that validates an order, writes it to a database, and then sends a notification.",
            "The database helper can open its own story inside the request story. That produces a child story, with its own stages and timing.",
            "In the console renderer, the child is indented under the parent. This makes a call tree easier to read without flattening every operation into one long list.",
        ],
    },
    {
        "chapter": "05 / NESTING", "title": "The async nesting pattern",
        "subtitle": "examples/substory_db_call.py",
        "kind": "code", "items": [
            'async with story("POST /orders"):',
            '    async with stage("Persist Order"):',
            '        await execute_query("INSERT INTO orders ...")', "",
            "async def execute_query(sql):",
            '    async with story(f"DB: {sql}"):',
            '        async with stage("Execute Query"): ...',
        ],
        "say": [
            "Here is the shape of the actual async example, shortened for legibility. The outer story names the request. A stage names the persistence step.",
            "The execute query helper opens a second story. It does not receive a parent ID as an argument; the active story is carried in Python context.",
            "Sync and async code use the same conceptual model. With async renderers, use the async context form so awaited stage events are handled correctly.",
        ],
    },
    {
        "chapter": "05 / NESTING", "title": "Separate IDs; one root",
        "subtitle": "The relationship is explicit in the emitted events",
        "kind": "tree", "items": ["API story: 9ca94c", "parent=None", "DB story: a9a3b8", "parent=9ca94c", "shared root_story_id=True", "renderers inherited=True"],
        "say": [
            "The example prints the relationship at the end. The API story and database story have different story IDs. The child's parent ID points to the API story.",
            "Both share a root story ID, which lets a renderer reconstruct the family. The helper also inherits renderers from its parent in this example.",
            "The short IDs on this slide are sample run values. Yours will be different each time, but the parent child relationship should stay the same.",
        ],
    },
    {
        "chapter": "06 / OPERATING SAFELY", "title": "Lean first; rich when needed",
        "subtitle": "Diagnostics are configurable and local variables are opt-in",
        "kind": "split", "items": [
            "LEAN|Exception type\nSource location\nCode context\nStage timeline",
            "RICH|Additional local variables\nExplicit redaction rules\nMore context to review\nUse with care",
        ],
        "say": [
            "The failure we just read uses lean diagnostics. It already includes the exception, source context, and stage timeline.",
            "Rich diagnostics can also capture local variables when the line of code is not enough. That is opt in, and it needs careful redaction rules.",
            "The diagnostics configuration example uses synthetic payment data to demonstrate redacted local values. We will cover the options in detail in a later episode.",
        ],
    },
    {
        "chapter": "06 / OPERATING SAFELY", "title": "Know the redaction boundary",
        "subtitle": "Keep real secrets and customer data out of recordings",
        "kind": "cards", "items": ["Local values\ncan be redacted", "Exception text\nmay still expose data", "Log fields\nneed review"],
        "say": [
            "Here is an important boundary: redacting captured local variables does not automatically rewrite arbitrary exception messages or log fields.",
            "That means you should not put real customer data, credentials, or private tokens into a demo run and assume every output channel is safe.",
            "For this video, the examples use synthetic data. Before publishing your own runs, review both the screen and the exported captions for sensitive information.",
        ],
    },
    {
        "chapter": "07 / YOUR TURN", "title": "Try it in your own small script",
        "subtitle": "One story, two stages, one deliberate test error",
        "kind": "steps", "items": ["1  Wrap the unit of work in story()", "2  Name two meaningful stages", "3  Run the success path", "4  Raise a test error in stage two", "5  Read the location and timeline"],
        "say": [
            "Now try the same pattern in a small script you already understand. Wrap one unit of work in a story and give two steps clear stage names.",
            "Run it once successfully. Then raise a deliberate test error in the second stage and compare the report with the usual traceback.",
            "Pay attention to what Runtime Narrative actually adds: the named boundary, the completion state, and the timeline. Keep the example data fake, especially if you plan to record the result.",
        ],
    },
    {
        "chapter": "07 / YOUR TURN", "title": "The next layer is integration",
        "subtitle": "From tiny script to request, job, and service",
        "kind": "hero", "items": ["FastAPI request", "Background job", "Optional analysis"],
        "say": [
            "You now have the core model: a story names the unit of work, stages name its steps, and a failure report ties the exception to that timeline.",
            "Nested stories let a helper become its own timed unit while remaining connected to its parent. Optional analysis and framework integrations build on these same ideas.",
            "The documentation and every example used here are linked in the video description. In the next tutorial, we will apply this model to a real Fast API request. Thanks for watching.",
        ],
    },
]


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str,
         size: int, color: str = WHITE, bold: bool = False,
         mono: bool = False) -> None:
    path = MONO if mono else BOLD if bold else REG
    draw.text(xy, value, font=font(path, size), fill=color)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
            fill: str, radius: int = 20, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def fit_lines(draw: ImageDraw.ImageDraw, value: str, max_width: int,
              size: int, bold: bool = False) -> list[str]:
    face = font(BOLD if bold else REG, size)
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=face)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_scene(scene: dict, index: int) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    # Atmospheric grid and glow, all original artwork from code.
    for x in range(0, W, 64):
        d.line((x, 0, x, H), fill="#111b2e", width=1)
    for y in range(0, H, 64):
        d.line((0, y, W, y), fill="#111b2e", width=1)
    d.ellipse((935, -245, 1460, 285), fill="#112b43")
    d.ellipse((-320, 520, 235, 1050), fill="#162139")
    d.rectangle((0, 0, W, 8), fill=CYAN)
    text(d, (72, 31), "RUNTIME NARRATIVE", 19, CYAN, bold=True)
    text(d, (1013, 32), f"EPISODE 01  /  {index:02d}", 17, MUTED, mono=True)
    text(d, (72, 81), scene["chapter"], 17, AMBER, bold=True)
    title = fit_lines(d, scene["title"], 1120, 44, bold=True)
    for row, line in enumerate(title[:2]):
        text(d, (70, 111 + row * 51), line, 44, WHITE, bold=True)
    sub_y = 175 if len(title) == 1 else 214
    text(d, (73, sub_y), scene["subtitle"], 20, MUTED)
    top = 223 if len(title) == 1 else 263
    bottom = 627
    kind = scene["kind"]
    items = scene["items"]
    if kind == "terminal" or kind == "code":
        rounded(d, (71, top, 1209, bottom), PANEL2, 21, "#31415d")
        d.rounded_rectangle((71, top, 1209, top + 52), radius=20, fill="#1d2a43")
        d.rectangle((71, top + 33, 1209, top + 52), fill="#1d2a43")
        for j, color in enumerate((RED, AMBER, GREEN)):
            d.ellipse((96 + 25 * j, top + 19, 107 + 25 * j, top + 30), fill=color)
        text(d, (200, top + 15), "terminal" if kind == "terminal" else "python", 16, MUTED, mono=True)
        size = 22 if max(map(len, items), default=0) < 67 else 19
        row_height = 39 if len(items) <= 8 else 35
        for j, line in enumerate(items[:9]):
            color = RED if "FAIL" in line or "ValueError" in line or "FAILED" in line else GREEN if "completed" in line or "SUCCESS" in line else CYAN if line.startswith("$") or line.startswith("with ") or line.startswith("async ") else WHITE
            text(d, (98, top + 71 + j * row_height), line, size, color, mono=True)
    elif kind == "timeline":
        for j, item in enumerate(items):
            label, status = item.split("|")
            y = top + 13 + j * 122
            fill = "#16322f" if status == "done" else "#432334"
            outline = GREEN if status == "done" else RED
            rounded(d, (100, y, 1180, y + 96), fill, 19, outline)
            d.ellipse((133, y + 27, 175, y + 69), fill=outline)
            text(d, (206, y + 23), label, 30, WHITE, bold=True)
            text(d, (955, y + 32), "COMPLETED" if status == "done" else "FAILED", 19, outline, bold=True)
    elif kind == "cards":
        n = len(items)
        cols = 2 if n == 4 else 3
        rows = math.ceil(n / cols)
        gap = 18
        card_w = (1138 - gap * (cols - 1)) // cols
        card_h = (bottom - top - gap * (rows - 1)) // rows
        for j, item in enumerate(items):
            col, row = j % cols, j // cols
            x, y = 71 + col * (card_w + gap), top + row * (card_h + gap)
            rounded(d, (x, y, x + card_w, y + card_h), PANEL, 22, "#2b4361")
            d.rounded_rectangle((x + 22, y + 24, x + 32, y + card_h - 24), radius=4, fill=[CYAN, BLUE, AMBER, GREEN][j % 4])
            for k, line in enumerate(item.split("\n")):
                text(d, (x + 55, y + card_h // 2 - 20 + k * 35), line, 24 if cols == 3 else 29, WHITE if k == 0 else MUTED, bold=k == 0)
    elif kind == "steps":
        step_h = (bottom - top - 32) // 5
        for j, item in enumerate(items):
            y = top + j * step_h
            rounded(d, (72, y, 1208, y + step_h - 8), PANEL if j % 2 == 0 else PANEL2, 15, "#263951")
            text(d, (105, y + 11), item, 25, CYAN if j == 0 else WHITE, bold=j == 0)
    elif kind == "split":
        gap = 20
        cw = (1138 - gap) // 2
        for j, item in enumerate(items):
            heading, body = item.split("|", 1)
            x = 71 + j * (cw + gap)
            rounded(d, (x, top, x + cw, bottom), PANEL, 21, CYAN if j == 0 else BLUE)
            text(d, (x + 28, top + 28), heading, 20, CYAN if j == 0 else BLUE, bold=True)
            for k, line in enumerate(body.split("\n")):
                text(d, (x + 28, top + 96 + k * 48), line, 20 if len(line) > 40 else 23, WHITE, mono="(" in line or "def " in line)
    elif kind == "tree":
        rounded(d, (71, top, 1209, bottom), PANEL, 20, "#2b4361")
        if len(items) == 7:
            coords = [(115, top + 26, CYAN), (167, top + 84, WHITE), (167, top + 140, WHITE),
                      (252, top + 196, AMBER), (305, top + 252, WHITE), (305, top + 308, WHITE),
                      (167, top + 355, WHITE)]
            for (x, y, color), item in zip(coords, items):
                text(d, (x, y), ("● " if color in (CYAN, AMBER) else "└ ") + item, 24, color, bold=color != WHITE)
        else:
            for j, item in enumerate(items):
                x = 114 if j in (0, 1, 4, 5) else 668
                y = top + 40 + (j % 2) * 105 + (j // 4) * 220
                if j in (2, 3):
                    y = top + 245 + (j % 2) * 100
                text(d, (x, y), item, 27 if j in (0, 2) else 22, CYAN if j == 0 else AMBER if j == 2 else WHITE, bold=j in (0, 2))
    else:  # hero
        rounded(d, (71, top, 1209, bottom), PANEL2, 24, "#2e4a67")
        for j, item in enumerate(items):
            y = top + 39 + j * 110
            rounded(d, (115, y, 1165, y + 80), "#1c2b43", 18, "#325270")
            d.ellipse((146, y + 24, 178, y + 56), fill=[CYAN, BLUE, AMBER][j])
            text(d, (208, y + 22), item, 29, WHITE, bold=True)
    d.line((72, 661, 1208, 661), fill="#3a4d69", width=2)
    d.rectangle((72, 658, 72 + int(1136 * index / len(SCENES)), 664), fill=CYAN)
    text(d, (72, 674), "runtime-narrative.netlify.app", 17, MUTED)
    text(d, (1075, 674), f"{index:02d} / {len(SCENES):02d}", 17, MUTED, mono=True)
    return im


def draw_thumbnail() -> Image.Image:
    """A separate high-contrast YouTube thumbnail, readable when small."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.ellipse((730, -260, 1510, 520), fill="#12344b")
    d.rectangle((0, 0, W, 14), fill=CYAN)
    text(d, (78, 53), "RUNTIME NARRATIVE  /  EPISODE 01", 28, AMBER, bold=True)
    text(d, (70, 116), "TRACEBACK", 103, RED, bold=True)
    text(d, (70, 235), "→ STORY", 111, CYAN, bold=True)
    rounded(d, (74, 404, 1199, 640), PANEL, 25, "#3a536f")
    text(d, (107, 433), "ValueError: duplicate customer id", 34, MUTED, mono=True)
    d.line((107, 501, 1155, 501), fill="#38506b", width=2)
    for j, (label, color) in enumerate((("LOAD CSV  DONE", GREEN), ("VALIDATE  DONE", GREEN),
                                        ("INSERT  FAILED", RED))):
        x = 107 + j * 352
        rounded(d, (x, 530, x + 320, 605), "#203247", 16, color)
        text(d, (x + 17, 549), label, 24, color, bold=True)
    return im


def format_srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def synthesize_chunks(chunks: list[dict]) -> None:
    """Generate a fully offline voice track using FFmpeg's built-in Flite."""
    (OUT / "speech_manifest.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for item in chunks:
        wav = Path(item["path"])
        txt = wav.with_suffix(".txt")
        txt.write_text(item["text"], encoding="utf-8")
        relative = txt.relative_to(OUT).as_posix()
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"flite=textfile={relative}:voice=slt",
            "-ar", "22050", "-ac", "1", str(wav),
        ], cwd=OUT, check=True)


def merge_wavs(paths: list[Path], destination: Path) -> tuple[list[tuple[float, float]], float]:
    starts_ends: list[tuple[float, float]] = []
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
    sample_rate = params.framerate
    block = params.nchannels * params.sampwidth
    cursor = 0
    with wave.open(str(destination), "wb") as out:
        out.setparams(params)
        for j, path in enumerate(paths):
            with wave.open(str(path), "rb") as source:
                assert source.getparams()[:3] == params[:3], "Speech formats changed"
                payload = source.readframes(source.getnframes())
                frames = source.getnframes()
            start = cursor / sample_rate
            out.writeframes(payload)
            cursor += frames
            end = cursor / sample_rate
            starts_ends.append((start, end))
            gap = 0.36 if j < len(paths) - 1 else 0.65
            padding = round(sample_rate * gap)
            out.writeframes(b"\x00" * (padding * block))
            cursor += padding
    return starts_ends, cursor / sample_rate


def render() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    speech = OUT / "speech"
    speech.mkdir(exist_ok=True)
    chunks = []
    for i, scene in enumerate(SCENES, 1):
        image = draw_scene(scene, i)
        image.save(FRAMES / f"scene_{i:02d}.png", optimize=True)
        for j, line in enumerate(scene["say"], 1):
            chunks.append({"path": str(speech / f"scene_{i:02d}_{j:02d}.wav"), "text": line})
    synthesize_chunks(chunks)
    all_srt = []
    chapter_times = []
    clip_list = []
    global_cursor = 0.0
    caption_id = 1
    prev_chapter = ""
    for i, scene in enumerate(SCENES, 1):
        chapter = scene["chapter"]
        if chapter != prev_chapter:
            chapter_times.append((global_cursor, chapter))
            prev_chapter = chapter
        paths = [speech / f"scene_{i:02d}_{j:02d}.wav" for j in range(1, len(scene["say"]) + 1)]
        wav_path = OUT / f"scene_{i:02d}.wav"
        spans, duration = merge_wavs(paths, wav_path)
        for line, (start, end) in zip(scene["say"], spans):
            caption = "\n".join(textwrap.wrap(line, width=62))
            all_srt.append(f"{caption_id}\n{format_srt_time(global_cursor + start)} --> {format_srt_time(global_cursor + end)}\n{caption}\n")
            caption_id += 1
        clip_path = OUT / f"scene_{i:02d}.mp4"
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1",
            "-framerate", str(FPS), "-i", str(FRAMES / f"scene_{i:02d}.png"),
            "-i", str(wav_path), "-vf",
            "scale=1344:756,zoompan=z='min(zoom+0.0001,1.045)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s=1280x720:fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(clip_path),
        ]
        print(f"Rendering scene {i:02d}/{len(SCENES)}: {scene['title']} ({duration:.1f}s)", flush=True)
        subprocess.run(command, check=True)
        clip_list.append(clip_path)
        # H.264 clips end on a video-frame boundary, rather than the exact WAV
        # duration. Probe the rendered clip so SRT timing follows the MP4.
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
                               check=True, text=True, capture_output=True)
        global_cursor += float(probe.stdout.strip())
    concat = OUT / "clips.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clip_list), encoding="utf-8")
    final = OUT / "runtime_narrative_episode_01.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
    (OUT / "runtime_narrative_episode_01.srt").write_text("\n".join(all_srt), encoding="utf-8")
    (OUT / "chapters.txt").write_text("\n".join(f"{format_srt_time(t)[:-4].replace(',', ':')} {name}" for t, name in chapter_times) + "\n", encoding="utf-8")
    draw_thumbnail().save(OUT / "thumbnail.png")
    print(f"Done: {final} ({global_cursor / 60:.1f} minutes)")


if __name__ == "__main__":
    render()
