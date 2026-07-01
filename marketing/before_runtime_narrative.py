"""Cold-open contrast piece for the flagship YouTube video.

This is the exact same "Import Customers" pipeline as examples/basic.py,
written the way most of us actually ship it: print statements, no story/stage
boundaries, and a bare traceback when something goes wrong. Record this
running first, then cut straight to examples/basic.py for the "after" shot.

Run:
    uv run python marketing/before_runtime_narrative.py
"""


def load_csv() -> list[str]:
    print("Loading CSV...")
    return ["alice", "bob"]


def validate(rows: list[str]) -> None:
    print("Validating data...")
    if not rows:
        raise ValueError("No rows found")


def insert(rows: list[str]) -> None:
    print("Inserting records...")
    raise ValueError("duplicate customer id")


def run() -> None:
    rows = load_csv()
    validate(rows)
    insert(rows)


run()
