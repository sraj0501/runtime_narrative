"""Demonstrates dry_run=True — verify instrumentation wiring without side effects.

With dry_run=True, exceptions raised inside stage bodies are suppressed and the
stage is still marked completed. The story always completes with success=True.
Use this to confirm that all stages are instrumented before running the real pipeline.

Run:
    uv run python examples/dry_run_mode.py
"""
from runtime_narrative import stage, story


def expensive_db_write(records: list) -> int:
    raise NotImplementedError("this would write to the real database")


def send_email(to: str, body: str) -> None:
    raise ConnectionError("this would connect to the SMTP server")


print("=== dry_run=True — side effects suppressed, instrumentation verified ===")

with story("Nightly Report", dry_run=True, total_stages=3):
    with stage("Fetch Records"):
        records = [{"id": i} for i in range(10)]

    with stage("Write to Database"):
        expensive_db_write(records)  # exception suppressed in dry_run mode

    with stage("Send Summary Email"):
        send_email("ops@example.com", "Report complete")  # also suppressed

print("\nAll stages wired correctly. Remove dry_run=True to run for real.")

print("\n=== dry_run=False — normal execution ===")

try:
    with story("Nightly Report", dry_run=False, total_stages=3):
        with stage("Fetch Records"):
            records = [{"id": i} for i in range(10)]

        with stage("Write to Database"):
            expensive_db_write(records)  # raises, story fails here

        with stage("Send Summary Email"):
            send_email("ops@example.com", "Report complete")
except NotImplementedError:
    pass
