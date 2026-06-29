"""Demonstrates SqliteStoryRenderer — persistent story storage queryable via CLI.

Run the example:
    uv run python examples/sqlite_persistence.py

Then query stored data:
    uv run runtime-narrative failures --last 5
    uv run runtime-narrative failures --story "Export Pipeline"
    uv run runtime-narrative story 1
"""
from runtime_narrative import SqliteStoryRenderer, stage, story

DB = "examples_demo.db"
renderer = SqliteStoryRenderer(db_path=DB)

print("=== Running success story ===")
with story("Load Pipeline", renderers=[renderer], total_stages=2):
    with stage("Fetch Data"):
        rows = ["alice", "bob", "carol"]
    with stage("Write Output"):
        print(f"  Wrote {len(rows)} rows")

print("\n=== Running failure story ===")
try:
    with story("Export Pipeline", renderers=[renderer], total_stages=3):
        with stage("Build Export"):
            records = [{"name": r} for r in rows]
        with stage("Compress Archive"):
            compressed = records  # placeholder
        with stage("Upload to S3"):
            raise ConnectionError("S3 endpoint unreachable: connection timed out after 30s")
except ConnectionError:
    pass

print(f"\nStories saved to {DB!r}")
print("Query with:")
print("  uv run runtime-narrative failures")
print("  uv run runtime-narrative story 1")
