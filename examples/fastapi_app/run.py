from __future__ import annotations

import os

import typer
import uvicorn


def main() -> None:
    host = os.getenv("RUNTIME_NARRATIVE_HOST", "127.0.0.1")
    port = int(os.getenv("RUNTIME_NARRATIVE_PORT", "8000"))
    reload_enabled = os.getenv("RUNTIME_NARRATIVE_RELOAD", "1") == "1"
    pid = os.getpid()

    typer.secho("▶ FastAPI Process: ", fg=typer.colors.GREEN, bold=True, nl=False)
    typer.secho(str(pid), fg=typer.colors.BRIGHT_WHITE)
    typer.secho("▶ FastAPI Host: ", fg=typer.colors.GREEN, bold=True, nl=False)
    typer.secho(host, fg=typer.colors.BRIGHT_WHITE)
    typer.secho("▶ FastAPI Port: ", fg=typer.colors.GREEN, bold=True, nl=False)
    typer.secho(str(port), fg=typer.colors.BRIGHT_WHITE)
    typer.secho("▶ FastAPI URL: ", fg=typer.colors.GREEN, bold=True, nl=False)
    typer.secho(f"http://{host}:{port}", fg=typer.colors.BRIGHT_WHITE)

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
