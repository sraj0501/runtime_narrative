from __future__ import annotations

from typing import Protocol


class RenderProtocol(Protocol):
    def handle(self, event: object) -> None:
        ...


__all__ = ["RenderProtocol"]
