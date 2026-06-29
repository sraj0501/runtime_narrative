from __future__ import annotations

import argparse
import os
import sqlite3
import sys


# ------------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------------


def _open_db(db_path: str) -> sqlite3.Connection:
    """Open the SQLite database, printing an error and exiting if it does not exist."""
    if not os.path.exists(db_path):
        print(f"Error: database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(db_path)


# ------------------------------------------------------------------
# Sub-commands
# ------------------------------------------------------------------


def _cmd_failures(args: argparse.Namespace) -> None:
    """List recent failures from the SQLite database."""
    conn = _open_db(args.db)

    sql = """
        SELECT f.story_id, s.name, f.stage_name, f.error_type, f.error_message, f.occurred_at
        FROM failures f
        LEFT JOIN stories s ON f.story_id = s.story_id
        WHERE 1=1
    """
    params: list = []

    if args.stage:
        sql += " AND f.stage_name = ?"
        params.append(args.stage)

    if args.story:
        sql += " AND s.name LIKE ?"
        params.append(args.story)

    sql += " ORDER BY f.id DESC LIMIT ?"
    params.append(args.last)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        print("No failures found.")
        return

    headers = ["story_id", "story_name", "stage_name", "error_type", "error_message", "occurred_at"]
    print("  ".join(headers))
    print("-" * 90)
    for row in rows:
        story_id_short = (row[0] or "")[:8]
        story_name = row[1] or ""
        stage_name = row[2] or ""
        error_type = row[3] or ""
        error_message = (row[4] or "")[:50]
        occurred_at = row[5] or ""
        print(f"{story_id_short}  {story_name}  {stage_name}  {error_type}  {error_message}  {occurred_at}")


def _cmd_story(args: argparse.Namespace) -> None:
    """Show details for a specific story."""
    conn = _open_db(args.db)

    story_row = conn.execute(
        "SELECT story_id, name, success, duration_seconds, started_at, completed_at"
        " FROM stories WHERE story_id = ?",
        (args.story_id,),
    ).fetchone()

    if story_row is None:
        print(f"Error: story not found: {args.story_id}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    story_id, name, success, duration_seconds, started_at, completed_at = story_row
    success_str = "success" if success else "failed"
    duration_str = f"{duration_seconds:.3f}s" if duration_seconds is not None else "n/a"

    print(f"Story: {name}")
    print(f"  ID:       {story_id}")
    print(f"  Status:   {success_str}")
    print(f"  Duration: {duration_str}")
    print(f"  Started:  {started_at}")
    print(f"  Ended:    {completed_at}")
    print()

    stages = conn.execute(
        "SELECT stage_name, duration_seconds, completed, failed"
        " FROM stages WHERE story_id = ? ORDER BY id",
        (story_id,),
    ).fetchall()

    if stages:
        print("Stages:")
        print(f"  {'name':<30} {'duration':>10} {'status'}")
        print("  " + "-" * 55)
        for stage_name, stage_dur, stage_completed, stage_failed in stages:
            dur_str = f"{stage_dur:.3f}s" if stage_dur is not None else "n/a"
            if stage_failed:
                status = "failed"
            elif stage_completed:
                status = "completed"
            else:
                status = "in-progress"
            print(f"  {stage_name:<30} {dur_str:>10} {status}")
        print()

    failures = conn.execute(
        "SELECT stage_name, error_type, error_message, filename, lineno,"
        " function, traceback_text, llm_analysis, occurred_at"
        " FROM failures WHERE story_id = ? ORDER BY id",
        (story_id,),
    ).fetchall()
    conn.close()

    if failures:
        print("Failures:")
        for fail in failures:
            f_stage, f_error_type, f_error_message, f_file, f_lineno, f_func, _f_tb, f_llm, f_at = fail
            print(f"  Stage:    {f_stage}")
            print(f"  Error:    {f_error_type}: {f_error_message}")
            print(f"  Location: {f_file}:{f_lineno} in {f_func}")
            if f_at:
                print(f"  Time:     {f_at}")
            if f_llm:
                print(f"  Analysis: {f_llm}")
            print()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="runtime-narrative",
        description="runtime-narrative CLI — inspect persisted story data",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # failures sub-command
    failures_parser = subparsers.add_parser("failures", help="List recent failures from the SQLite db")
    failures_parser.add_argument(
        "--db",
        default="runtime_narrative.db",
        metavar="PATH",
        help="Path to SQLite database (default: runtime_narrative.db)",
    )
    failures_parser.add_argument(
        "--last",
        type=int,
        default=10,
        metavar="N",
        help="Number of failures to show (default: 10)",
    )
    failures_parser.add_argument(
        "--stage",
        default=None,
        metavar="STAGE_NAME",
        help="Filter by exact stage name",
    )
    failures_parser.add_argument(
        "--story",
        default=None,
        metavar="STORY_NAME",
        help="Filter by story name (SQL LIKE pattern, e.g. 'Import %%')",
    )

    # story sub-command
    story_parser = subparsers.add_parser("story", help="Show details for a specific story")
    story_parser.add_argument("story_id", help="Story ID to look up")
    story_parser.add_argument(
        "--db",
        default="runtime_narrative.db",
        metavar="PATH",
        help="Path to SQLite database (default: runtime_narrative.db)",
    )

    args = parser.parse_args()

    if args.command == "failures":
        _cmd_failures(args)
    elif args.command == "story":
        _cmd_story(args)


if __name__ == "__main__":
    main()
