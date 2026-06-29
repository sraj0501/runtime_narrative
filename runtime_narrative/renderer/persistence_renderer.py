from __future__ import annotations

import sqlite3
from typing import Optional

__all__ = ["SqliteStoryRenderer"]

_DDL = """
CREATE TABLE IF NOT EXISTS stories (
    story_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    success INTEGER,
    duration_seconds REAL
);
CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    stage_index INTEGER DEFAULT 0,
    parent_stage_name TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    completed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    stage_name TEXT,
    error_type TEXT,
    error_message TEXT,
    filename TEXT,
    lineno INTEGER,
    function TEXT,
    source_line TEXT,
    traceback_text TEXT,
    exception_chain TEXT,
    llm_analysis TEXT,
    occurred_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_failures_story_id ON failures(story_id);
CREATE INDEX IF NOT EXISTS idx_stages_story_id ON stages(story_id);
"""


class SqliteStoryRenderer:
    """Sync renderer that persists all story events to a SQLite database (stdlib, no extras).

    The database connection is opened lazily on the first :meth:`handle` call so that
    constructing the renderer never blocks.

    Args:
        db_path: Path to the SQLite database file (created if it does not exist).
    """

    def __init__(self, db_path: str = "runtime_narrative.db") -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Internal helpers — sync because they are called from handle() which
    # must be sync per the renderer protocol.  sqlite3 is stdlib-only and
    # provides no async interface, so asyncio.to_thread is not applicable
    # here either.
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> sqlite3.Connection:
        """Return the active connection, opening it and creating tables on first call."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.executescript(_DDL)
            self._conn.commit()
        return self._conn

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def handle(self, event: object) -> None:  # sync — renderer protocol requirement
        conn = self._ensure_connected()
        event_name = event.__class__.__name__

        if event_name == "StoryStarted":
            conn.execute(
                "INSERT OR IGNORE INTO stories (story_id, name, started_at) VALUES (?, ?, ?)",
                (event.story_id, event.story_name, event.timestamp.isoformat()),
            )

        elif event_name == "StageStarted":
            conn.execute(
                """
                INSERT INTO stages
                    (story_id, stage_name, stage_index, parent_stage_name, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.story_id,
                    event.stage_name,
                    event.stage_index,
                    event.parent_stage_name,
                    event.timestamp.isoformat(),
                ),
            )

        elif event_name == "StageCompleted":
            conn.execute(
                """
                UPDATE stages
                SET completed_at = ?,
                    duration_seconds = ?,
                    completed = 1
                WHERE id = (
                    SELECT id FROM stages
                    WHERE story_id = ? AND stage_name = ? AND completed = 0
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (
                    event.timestamp.isoformat(),
                    event.duration_seconds,
                    event.story_id,
                    event.stage_name,
                ),
            )

        elif event_name == "FailureOccurred":
            conn.execute(
                """
                INSERT INTO failures (
                    story_id, stage_name, error_type, error_message,
                    filename, lineno, function, source_line,
                    traceback_text, exception_chain, llm_analysis, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    event.story_id,
                    event.stage_name,
                    event.error_type,
                    event.error_message,
                    event.filename,
                    event.lineno,
                    event.function,
                    event.source_line,
                    getattr(event, "traceback_text", None),
                    event.exception_chain,
                    event.llm_analysis,
                ),
            )
            # Mark the in-progress stage row as failed.
            conn.execute(
                """
                UPDATE stages
                SET failed = 1
                WHERE id = (
                    SELECT id FROM stages
                    WHERE story_id = ? AND stage_name = ? AND completed = 0
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (event.story_id, event.stage_name),
            )

        elif event_name == "LLMAnalysisReady":
            conn.execute(
                """
                UPDATE failures
                SET llm_analysis = ?
                WHERE story_id = ? AND llm_analysis IS NULL
                """,
                (event.llm_analysis, event.story_id),
            )

        elif event_name == "StoryCompleted":
            completed_at = event.timestamp.isoformat()
            conn.execute(
                """
                UPDATE stories
                SET completed_at = ?,
                    success = ?,
                    duration_seconds = (julianday(?) - julianday(started_at)) * 86400.0
                WHERE story_id = ?
                """,
                (completed_at, int(event.success), completed_at, event.story_id),
            )

        conn.commit()

    def close(self) -> None:  # sync — resource cleanup
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._conn = None

    def __del__(self) -> None:
        self.close()
