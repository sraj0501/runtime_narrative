# runtime_narrative

Model your application's execution as **human-readable stories** instead of scattered log lines.

When something fails, instead of a raw traceback you get:

```
❌ Failure detected
Story:    Create Customer
Stage:    Validate Input
Error:    ValueError - invalid email
Location: handlers.py:24 (validate_customer)
Code:     if "@" not in payload.email:
Progress: 33% (1 / 3 stages completed)
Recent stages: Validate Input=failed (0.001s)
```

## Installation

```bash
# Core only (zero dependencies)
pip install runtime-narrative

# With colored console output
pip install "runtime-narrative[console]"

# With FastAPI middleware
pip install "runtime-narrative[fastapi]"

# Everything
pip install "runtime-narrative[all]"
```

## Quick start

```python
from runtime_narrative import story, stage

with story("Import Customers"):
    with stage("Load CSV"):
        load_file()

    with stage("Validate Data"):
        validate()

    with stage("Insert Records"):
        insert()
```

## FastAPI — middleware (recommended)

Add middleware once and every request gets a story automatically.
Route handlers only need to declare stages:

```python
from runtime_narrative import RuntimeNarrativeMiddleware, stage

app.add_middleware(RuntimeNarrativeMiddleware)

@app.post("/customers")
async def create_customer(payload: CustomerIn):
    with stage("Validate Input"):
        ...
    with stage("Insert Into Database"):
        ...
    with stage("Build Response"):
        return {"ok": True}
```

## FastAPI — decorator style

```python
from runtime_narrative import runtime_narrative_story, runtime_narrative_stage

@app.post("/customers")
@runtime_narrative_story("Create Customer")
async def create_customer(payload: CustomerIn):
    return await _save(payload)

@runtime_narrative_stage("Save to Database")
async def _save(payload):
    ...
```

## Structured JSON output

Pipe one JSON object per lifecycle event to stdout, a file, or any stream:

```python
from runtime_narrative import RuntimeNarrativeMiddleware, JsonRenderer

app.add_middleware(RuntimeNarrativeMiddleware, renderers=[JsonRenderer()])
```

Output (one line per event):
```json
{"event": "StoryStarted", "story_id": "...", "story_name": "POST /customers", "timestamp": "..."}
{"event": "StageStarted", "story_id": "...", "stage_name": "Validate Input", "timestamp": "..."}
{"event": "StageCompleted", "story_id": "...", "stage_name": "Validate Input", "duration_seconds": 0.001, "timestamp": "..."}
{"event": "StoryCompleted", "story_id": "...", "success": true, "progress": {"percent": 100, ...}, "timestamp": "..."}
```

Write to a file instead of stdout:

```python
JsonRenderer(output=open("runtime_narrative.log", "a"))
```

## LLM failure analysis

Plug in any LLM backend — model name and endpoint are always required (no defaults).

**OpenAI-compatible backends** (vLLM, llama.cpp `--server`, LM Studio, Ollama OpenAI mode):

```python
from runtime_narrative import LLMFailureAnalyzer, story

analyzer = LLMFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:8000/v1/chat/completions",
)

with story("Process Orders", failure_analyzer=analyzer):
    ...
```

**Ollama native API:**

```python
from runtime_narrative import OllamaFailureAnalyzer, story

analyzer = OllamaFailureAnalyzer(
    model="llama3",
    endpoint="http://localhost:11434/api/generate",
)

with story("Process Orders", failure_analyzer=analyzer):
    ...
```

Falls back silently if the endpoint is unavailable.

## Custom renderer

Implement a single `handle` method to receive all lifecycle events:

```python
class MyRenderer:
    def handle(self, event):
        print(event.__class__.__name__, event.__dict__)

with story("My Story", renderers=[MyRenderer()]):
    ...
```

Events: `StoryStarted`, `StageStarted`, `StageCompleted`, `FailureOccurred`, `StoryCompleted`.

## License

MIT
