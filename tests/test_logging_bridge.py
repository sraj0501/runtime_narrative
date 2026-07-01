from __future__ import annotations

import logging

from runtime_narrative import stage, story
from runtime_narrative.logging_bridge import NarrativeLogHandler

from tests.conftest import CapturingRenderer


def _make_logger(handler: NarrativeLogHandler, name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers = [handler]
    logger.propagate = False
    return logger


def test_log_captured_inside_active_story_emits_log_recorded() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.inside")

    with story("API", renderers=[cap]) as runtime:
        with stage("Call DB"):
            logger.warning("slow query took too long")

    events = [e for e in cap.events if e.__class__.__name__ == "LogRecorded"]
    assert len(events) == 1
    assert events[0].story_id == runtime.story_id
    assert events[0].root_story_id == runtime.story_id
    assert events[0].stage_name == "Call DB"
    assert events[0].level == "WARNING"
    assert events[0].message == "slow query took too long"


def test_log_below_level_threshold_is_ignored() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.belowlevel")

    with story("API", renderers=[cap]):
        logger.info("just fyi")

    assert not [e for e in cap.events if e.__class__.__name__ == "LogRecorded"]


def test_log_outside_story_falls_back() -> None:
    fallback_calls: list[logging.LogRecord] = []

    class FallbackHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            fallback_calls.append(record)

    handler = NarrativeLogHandler(level=logging.WARNING, fallback=FallbackHandler())
    logger = _make_logger(handler, "rn.test.outside")

    logger.error("no story active")

    assert len(fallback_calls) == 1
    assert fallback_calls[0].getMessage() == "no story active"


def test_log_captures_exception_info() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.exc")

    with story("API", renderers=[cap]):
        try:
            raise ValueError("boom")
        except ValueError:
            logger.error("db call failed", exc_info=True)

    events = [e for e in cap.events if e.__class__.__name__ == "LogRecorded"]
    assert len(events) == 1
    assert events[0].exc_text is not None
    assert "ValueError: boom" in events[0].exc_text


def test_log_in_substory_carries_root_story_id_of_parent() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.substory")

    with story("API", renderers=[cap]) as api_runtime:
        with story("DB") as db_runtime:
            logger.warning("connection retry")

    events = [e for e in cap.events if e.__class__.__name__ == "LogRecorded"]
    assert len(events) == 1
    assert events[0].story_id == db_runtime.story_id
    assert events[0].root_story_id == api_runtime.story_id


def test_log_extra_fields_are_captured() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.fields")

    with story("API", renderers=[cap]):
        logger.warning("slow query", extra={"order_id": "ORD-42", "duration_ms": 250})

    event = next(e for e in cap.events if e.__class__.__name__ == "LogRecorded")
    assert event.fields == {"order_id": "ORD-42", "duration_ms": 250}


def test_log_without_extra_has_empty_fields() -> None:
    cap = CapturingRenderer()
    handler = NarrativeLogHandler(level=logging.WARNING)
    logger = _make_logger(handler, "rn.test.nofields")

    with story("API", renderers=[cap]):
        logger.warning("plain message")

    event = next(e for e in cap.events if e.__class__.__name__ == "LogRecorded")
    assert event.fields == {}
