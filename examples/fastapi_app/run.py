from __future__ import annotations

import os
import sys

import typer
import uvicorn


def _secho(text: str, *, fg=None, bold: bool = False, nl: bool = True) -> None:
    try:
        typer.secho(text, fg=fg, bold=bold, nl=nl)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
        typer.secho(safe, fg=fg, bold=bold, nl=nl)


def main() -> None:
    host = os.getenv("RUNTIME_NARRATIVE_HOST", "127.0.0.1")
    port = int(os.getenv("RUNTIME_NARRATIVE_PORT", "8000"))
    reload_enabled = os.getenv("RUNTIME_NARRATIVE_RELOAD", "1") == "1"
    pid = os.getpid()

    _secho("▶ FastAPI Process: ", fg=typer.colors.GREEN, bold=True, nl=False)
    _secho(str(pid), fg=typer.colors.BRIGHT_WHITE)
    _secho("▶ FastAPI Host: ", fg=typer.colors.GREEN, bold=True, nl=False)
    _secho(host, fg=typer.colors.BRIGHT_WHITE)
    _secho("▶ FastAPI Port: ", fg=typer.colors.GREEN, bold=True, nl=False)
    _secho(str(port), fg=typer.colors.BRIGHT_WHITE)
    _secho("▶ FastAPI URL: ", fg=typer.colors.GREEN, bold=True, nl=False)
    _secho(f"http://{host}:{port}", fg=typer.colors.BRIGHT_WHITE)

    # Suppress uvicorn INFO noise and rely on runtime_narrative logs from app lifespan/handlers.
    uvicorn.run(
        "examples.fastapi_app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
