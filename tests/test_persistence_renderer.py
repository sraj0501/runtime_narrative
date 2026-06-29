from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from runtime_narrative import stage, story
from runtime_narrative.events import (
    FailureOccurred,
    LLMAnalysisReady,
    StageCompleted,
    StageStarted,
    StoryCompleted,
    StoryStarted,
)
from runtime_narrative.renderer.persistence_renderer import SqliteStoryRenderer


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _renderer(tmp_path: Path, name: str = "test.db") -> tuple[SqliteStoryRenderer, str]:
    db_path = str(tmp_path / name)
    return SqliteStoryRenderer(db_path=db_path), db_path


def _query(db_path: str, sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _make_failure(
    story_id: str = "s1",
    stage_name: str = "Step 1",
    error_type: str = "ValueError",
    error_message: str = "bad value",
) -> FailureOccurred:
    return FailureOccurred(
        story_id=story_id,
        story_name="My Story",
        stage_name=stage_name,
        error_type=error_type,
        error_message=error_message,
        filename="test.py",
        lineno=42,
        function="test_fn",
        source_line="raise ValueError('bad value')",
        exception_chain="",
        exact_cause=f"{error_type}: {error_message}",
        llm_analysis=None,
        stage_timeline=f"{stage_name}=failed",
        progress_percent=0,
        completed_stages=0,
        total_stages=1,
        timestamp=datetime.now(),
        traceback_text="Traceback (most recent call last): ...",
    )


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_story_row_created_on_story_started(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="abc123", story_name="My Story", timestamp=now))
    renderer.close()

    rows = _query(db_path, "SELECT story_id, name, started_at FROM stories WHERE story_id = ?", ("abc123",))
    assert len(rows) == 1
    assert rows[0][0] == "abc123"
    assert rows[0][1] == "My Story"
    assert rows[0][2] == now.isoformat()


def test_story_started_insert_or_ignore_is_idempotent(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="dup", story_name="Dup Story", timestamp=now))
    renderer.handle(StoryStarted(story_id="dup", story_name="Dup Story", timestamp=now))
    renderer.close()

    rows = _query(db_path, "SELECT count(*) FROM stories WHERE story_id = ?", ("dup",))
    assert rows[0][0] == 1


def test_stage_row_created_on_stage_started(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Step 1", timestamp=now, stage_index=0))
    renderer.close()

    rows = _query(
        db_path,
        "SELECT stage_name, stage_index, completed, failed FROM stages WHERE story_id = ?",
        ("s1",),
    )
    assert len(rows) == 1
    assert rows[0][0] == "Step 1"
    assert rows[0][1] == 0
    assert rows[0][2] == 0
    assert rows[0][3] == 0


def test_stage_updated_on_stage_completed(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Step 1", timestamp=now, stage_index=0))
    renderer.handle(
        StageCompleted(
            story_id="s1",
            stage_name="Step 1",
            timestamp=now + timedelta(seconds=1),
            duration_seconds=1.0,
            stage_index=0,
        )
    )
    renderer.close()

    rows = _query(
        db_path,
        "SELECT stage_name, duration_seconds, completed FROM stages WHERE story_id = ?",
        ("s1",),
    )
    assert len(rows) == 1
    assert rows[0][1] == pytest.approx(1.0)
    assert rows[0][2] == 1  # completed flag set


def test_stage_completed_targets_most_recent_uncommitted_row(tmp_path: Path) -> None:
    """When two stages share the same name, StageCompleted must update the latest row."""
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    # First occurrence — completed
    renderer.handle(StageStarted(story_id="s1", stage_name="Retry", timestamp=now, stage_index=0))
    renderer.handle(
        StageCompleted(story_id="s1", stage_name="Retry", timestamp=now + timedelta(seconds=1), duration_seconds=1.0, stage_index=0)
    )
    # Second occurrence — still in-progress
    renderer.handle(StageStarted(story_id="s1", stage_name="Retry", timestamp=now + timedelta(seconds=2), stage_index=1))
    renderer.close()

    rows = _query(db_path, "SELECT completed FROM stages WHERE story_id = ? ORDER BY id", ("s1",))
    assert rows[0][0] == 1  # first row completed
    assert rows[1][0] == 0  # second row still open


def test_failure_row_created_llm_analysis_starts_null(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Step 1", timestamp=now, stage_index=0))
    renderer.handle(_make_failure("s1", "Step 1"))
    renderer.close()

    rows = _query(
        db_path,
        "SELECT error_type, error_message, llm_analysis FROM failures WHERE story_id = ?",
        ("s1",),
    )
    assert len(rows) == 1
    assert rows[0][0] == "ValueError"
    assert rows[0][1] == "bad value"
    assert rows[0][2] is None  # llm_analysis must start as NULL


def test_failure_marks_stage_failed(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Step 1", timestamp=now, stage_index=0))
    renderer.handle(_make_failure("s1", "Step 1"))
    renderer.close()

    rows = _query(db_path, "SELECT failed FROM stages WHERE story_id = ? AND stage_name = ?", ("s1", "Step 1"))
    assert len(rows) == 1
    assert rows[0][0] == 1


def test_llm_analysis_ready_updates_failure(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Step 1", timestamp=now, stage_index=0))
    renderer.handle(_make_failure("s1", "Step 1"))
    renderer.handle(
        LLMAnalysisReady(
            story_id="s1",
            story_name="S",
            stage_name="Step 1",
            llm_analysis="root cause: bad value was passed",
            timestamp=now + timedelta(seconds=1),
        )
    )
    renderer.close()

    rows = _query(db_path, "SELECT llm_analysis FROM failures WHERE story_id = ?", ("s1",))
    assert len(rows) == 1
    assert rows[0][0] == "root cause: bad value was passed"


def test_story_completed_sets_success_and_duration(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(
        StoryCompleted(
            story_id="s1",
            story_name="S",
            success=True,
            progress_percent=100,
            completed_stages=1,
            total_stages=1,
            timestamp=now + timedelta(seconds=2),
        )
    )
    renderer.close()

    rows = _query(db_path, "SELECT success, duration_seconds FROM stories WHERE story_id = ?", ("s1",))
    assert len(rows) == 1
    assert rows[0][0] == 1  # success=True → 1
    assert rows[0][1] == pytest.approx(2.0, abs=0.05)


def test_story_completed_failure_sets_success_false(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()
    renderer.handle(StoryStarted(story_id="s1", story_name="S", timestamp=now))
    renderer.handle(
        StoryCompleted(
            story_id="s1",
            story_name="S",
            success=False,
            progress_percent=0,
            completed_stages=0,
            total_stages=1,
            timestamp=now + timedelta(seconds=1),
        )
    )
    renderer.close()

    rows = _query(db_path, "SELECT success FROM stories WHERE story_id = ?", ("s1",))
    assert rows[0][0] == 0  # success=False → 0


def test_two_stories_do_not_interfere(tmp_path: Path) -> None:
    renderer, db_path = _renderer(tmp_path)
    now = datetime.now()

    # Story 1 — succeeds
    renderer.handle(StoryStarted(story_id="s1", story_name="Story One", timestamp=now))
    renderer.handle(StageStarted(story_id="s1", stage_name="Stage A", timestamp=now, stage_index=0))
    renderer.handle(StageCompleted(
        story_id="s1", stage_name="Stage A",
        timestamp=now + timedelta(seconds=1), duration_seconds=1.0, stage_index=0,
    ))
    renderer.handle(StoryCompleted(
        story_id="s1", story_name="Story One", success=True,
        progress_percent=100, completed_stages=1, total_stages=1,
        timestamp=now + timedelta(seconds=1),
    ))

    # Story 2 — fails
    renderer.handle(StoryStarted(story_id="s2", story_name="Story Two", timestamp=now))
    renderer.handle(StageStarted(story_id="s2", stage_name="Stage B", timestamp=now, stage_index=0))
    renderer.handle(_make_failure("s2", "Stage B"))
    renderer.handle(StoryCompleted(
        story_id="s2", story_name="Story Two", success=False,
        progress_percent=0, completed_stages=0, total_stages=1,
        timestamp=now + timedelta(seconds=3),
    ))
    renderer.close()

    # Each story has exactly one row in stories
    assert len(_query(db_path, "SELECT 1 FROM stories WHERE story_id = ?", ("s1",))) == 1
    assert len(_query(db_path, "SELECT 1 FROM stories WHERE story_id = ?", ("s2",))) == 1

    # Stages are isolated
    s1_stages = _query(db_path, "SELECT stage_name FROM stages WHERE story_id = ?", ("s1",))
    s2_stages = _query(db_path, "SELECT stage_name FROM stages WHERE story_id = ?", ("s2",))
    assert s1_stages == [("Stage A",)]
    assert s2_stages == [("Stage B",)]

    # Failures are isolated
    assert len(_query(db_path, "SELECT 1 FROM failures WHERE story_id = ?", ("s1",))) == 0
    assert len(_query(db_path, "SELECT 1 FROM failures WHERE story_id = ?", ("s2",))) == 1

    # Success flags are independent
    s1_success = _query(db_path, "SELECT success FROM stories WHERE story_id = ?", ("s1",))
    s2_success = _query(db_path, "SELECT success FROM stories WHERE story_id = ?", ("s2",))
    assert s1_success[0][0] == 1
    assert s2_success[0][0] == 0


def test_full_round_trip_success(tmp_path: Path) -> None:
    """Run a real story with SqliteStoryRenderer and assert the db reflects it."""
    db_path = str(tmp_path / "roundtrip_ok.db")
    renderer = SqliteStoryRenderer(db_path=db_path)

    with story("Round Trip", renderers=[renderer]):
        with stage("Step A"):
            pass
        with stage("Step B"):
            pass

    renderer.close()

    stories = _query(db_path, "SELECT name, success, duration_seconds FROM stories")
    assert len(stories) == 1
    assert stories[0][0] == "Round Trip"
    assert stories[0][1] == 1  # success
    assert stories[0][2] is not None and stories[0][2] >= 0.0

    stages_rows = _query(db_path, "SELECT stage_name, completed, failed FROM stages ORDER BY id")
    assert len(stages_rows) == 2
    assert stages_rows[0] == ("Step A", 1, 0)
    assert stages_rows[1] == ("Step B", 1, 0)

    failures = _query(db_path, "SELECT 1 FROM failures")
    assert len(failures) == 0


def test_full_round_trip_failure(tmp_path: Path) -> None:
    """Run a real failing story and assert failure row and stage flags are correct."""
    db_path = str(tmp_path / "roundtrip_fail.db")
    renderer = SqliteStoryRenderer(db_path=db_path)

    with pytest.raises(RuntimeError):
        with story("Failing Story", renderers=[renderer]):
            with stage("Good Step"):
                pass
            with stage("Bad Step"):
                raise RuntimeError("something went wrong")

    renderer.close()

    stories = _query(db_path, "SELECT name, success FROM stories")
    assert len(stories) == 1
    assert stories[0][0] == "Failing Story"
    assert stories[0][1] == 0  # not success

    stages_rows = _query(db_path, "SELECT stage_name, completed, failed FROM stages ORDER BY id")
    assert len(stages_rows) == 2
    good_name, good_completed, good_failed = stages_rows[0]
    bad_name, bad_completed, bad_failed = stages_rows[1]

    assert good_name == "Good Step"
    assert good_completed == 1
    assert good_failed == 0

    assert bad_name == "Bad Step"
    assert bad_failed == 1  # updated by FailureOccurred handler

    failures = _query(db_path, "SELECT error_type, error_message FROM failures")
    assert len(failures) == 1
    assert failures[0][0] == "RuntimeError"
    assert failures[0][1] == "something went wrong"
