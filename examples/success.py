"""Success path using story()/stage() context managers directly.

Shows the minimal API: no decorators, no LLM analyzer, just a story with
three stages that all complete successfully. total_stages gives the renderer
accurate progress percentages.

Run:
    uv run python examples/success.py
"""
from runtime_narrative import stage, story


with story("Import Customers", total_stages=3):
    with stage("Load CSV"):
        rows = ["alice", "bob"]

    with stage("Validate Data"):
        if not rows:
            raise ValueError("No rows found")

    with stage("Insert Records"):
        inserted_count = len(rows)
        print(f"Inserted {inserted_count} records")
