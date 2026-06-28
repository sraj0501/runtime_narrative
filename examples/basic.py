"""Basic failure example using @runtime_narrative_story / @runtime_narrative_stage.

Run:
    uv run python examples/basic.py
"""
from runtime_narrative import runtime_narrative_stage, runtime_narrative_story


@runtime_narrative_stage("Load CSV")
def load_csv() -> list[str]:
    return ["alice", "bob"]


@runtime_narrative_stage("Validate Data")
def validate(rows: list[str]) -> None:
    if not rows:
        raise ValueError("No rows found")


@runtime_narrative_stage("Insert Records")
def insert(rows: list[str]) -> None:
    raise ValueError("duplicate customer id")


@runtime_narrative_story("Import Customers")
def run() -> None:
    rows = load_csv()
    validate(rows)
    insert(rows)


try:
    run()
except Exception:
    pass
