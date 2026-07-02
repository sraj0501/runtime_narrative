from __future__ import annotations

from http import HTTPStatus


def http_outcome(status_code: int) -> str:
    """Format an HTTP status code as a "200 OK"-style story outcome label.

    Sync by design: pure data transformation with no I/O.
    """
    try:
        return f"{status_code} {HTTPStatus(status_code).phrase}"
    except ValueError:
        return str(status_code)


__all__ = ["http_outcome"]
