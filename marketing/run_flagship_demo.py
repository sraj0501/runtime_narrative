"""Single-file rehearsal/recording runner for youtube_flagship_script.md.

Not a library example -- a presenter's tool. Run this one file while screen-recording
and it walks through every demo beat in order, pausing for you to narrate between steps.
Nothing here is pre-recorded or mocked: every command is the real example script, run live.

Run:
    uv run python marketing/run_flagship_demo.py

Requires (one-time):
    uv sync --group dev --extra console
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIVIDER = "=" * 78


def banner(title: str, subtitle: str = "") -> None:
    print(f"\n{DIVIDER}\n  {title}")
    if subtitle:
        print(f"  {subtitle}")
    print(DIVIDER)


def pause(prompt: str = "Press Enter to continue...") -> str:
    return input(f"\n>>> {prompt} ").strip()


def run(args: list[str], env: dict | None = None) -> None:
    subprocess.run(args, cwd=REPO_ROOT, env=env, check=False)


def start_server(extra_env: dict | None = None) -> subprocess.Popen | None:
    env = {**os.environ, "RUNTIME_NARRATIVE_RELOAD": "0", **(extra_env or {})}
    proc = subprocess.Popen(
        [sys.executable, "-m", "examples.fastapi_app.run"],
        cwd=REPO_ROOT,
        env=env,
    )
    for _ in range(40):
        if proc.poll() is not None:
            print("Server process exited before becoming ready -- skipping this beat.")
            return None
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=0.5)
            return proc
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.25)
    print("Server never became ready -- skipping this beat.")
    stop_server(proc)
    return None


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def http_call(method: str, path: str, payload: dict | None = None) -> None:
    url = f"http://127.0.0.1:8000{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    print(f"$ {method} {path}" + (f"  body={payload}" if payload else ""))
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  -> {resp.status} {resp.read().decode()}")
    except urllib.error.HTTPError as exc:
        print(f"  -> {exc.code} {exc.read().decode()}")
    except urllib.error.URLError as exc:
        print(f"  -> unreachable ({exc.reason}) -- is the server running?")


def main() -> None:
    banner("COLD OPEN -- THE PROBLEM", "marketing/before_runtime_narrative.py")
    pause("Narrate the pain, then run it.")
    run([sys.executable, "marketing/before_runtime_narrative.py"])

    banner("COLD OPEN -- THE FIX", "examples/basic.py")
    pause()
    run([sys.executable, "examples/basic.py"])

    banner("INSTALL", "pip install runtime-narrative")
    pause("Show the install line on screen (nothing to run).")

    banner("DEMO 1 -- SUCCESS PATH", "examples/success.py")
    pause()
    run([sys.executable, "examples/success.py"])

    banner("DEMO 2 -- RICH DIAGNOSTICS + REDACTION", "examples/diagnostics_config.py")
    pause()
    run([sys.executable, "examples/diagnostics_config.py"])

    banner("DEMO 3 -- LLM ROOT CAUSE ANALYSIS", "examples/basic_ollama.py (needs a running local Ollama)")
    model = pause("Ollama model name to use, blank to skip this beat:")
    if model:
        run([sys.executable, "examples/basic_ollama.py"], env={**os.environ, "RUNTIME_NARRATIVE_MODEL": model})
    else:
        print("Skipped -- see examples/anthropic_analyzer.py for a cloud-model alternative.")

    banner("DEMO 4 -- FASTAPI MIDDLEWARE", "examples/fastapi_app (console renderer)")
    pause("Starting the server...")
    server = start_server()
    if server:
        http_call("POST", "/customers", {"name": "Alice", "email": "bad-email"})
        pause("Failure box should have printed in this terminal above. Continue to the success calls.")
        http_call("POST", "/customers", {"name": "Alice", "email": "alice@example.com"})
        http_call("GET", "/customers")
        stop_server(server)

    banner("DEMO 4 -- SUB-STORY CALL TREE", "examples/substory_db_call.py")
    pause()
    run([sys.executable, "examples/substory_db_call.py"])

    banner("DEMO 5 -- JSON RENDERER", "examples/fastapi_app (RUNTIME_NARRATIVE_JSON=1)")
    pause("Starting the server in JSON mode...")
    server = start_server(extra_env={"RUNTIME_NARRATIVE_JSON": "1"})
    if server:
        http_call("POST", "/customers", {"name": "Alice", "email": "bad-email"})
        pause()
        stop_server(server)

    banner("DEMO 5 -- HTML REPORT", "examples/html_report.py")
    pause()
    run([sys.executable, "examples/html_report.py"])
    report = REPO_ROOT / "examples_report.html"
    if report.exists():
        webbrowser.open(report.as_uri())

    banner("DEMO 5 -- OPENTELEMETRY", "examples/otel_tracing.py (skips gracefully if extra not installed)")
    pause()
    run([sys.executable, "examples/otel_tracing.py"])

    banner("DEMO 5 -- ALERT ROUTING / SLACK WEBHOOK", "examples/alert_routing.py (needs network)")
    pause()
    run([sys.executable, "examples/alert_routing.py"])

    banner("WRAP UP", "pip install runtime-narrative -- link + wiki in description")
    pause("End recording.")


if __name__ == "__main__":
    main()
