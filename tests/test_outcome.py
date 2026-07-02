from __future__ import annotations

from runtime_narrative.outcome import http_outcome


def test_http_outcome_known_codes() -> None:
    assert http_outcome(200) == "200 OK"
    assert http_outcome(404) == "404 Not Found"
    assert http_outcome(500) == "500 Internal Server Error"


def test_http_outcome_unknown_code_falls_back_to_number() -> None:
    assert http_outcome(599) == "599"
