from runtime_narrative import stage, story


with story("Import Customers"):
    with stage("Load CSV"):
        rows = ["alice", "bob"]

    with stage("Validate Data"):
        if not rows:
            raise ValueError("No rows found")

    with stage("Insert Records"):
        inserted_count = len(rows)
        print(f"Inserted {inserted_count} records")
