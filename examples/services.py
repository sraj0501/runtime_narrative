"""Sample services module used by instrument_module.py and auto_instrument.py."""
from __future__ import annotations


class CustomerService:
    def load(self, source: str) -> list[str]:
        return [f"customer_{i}" for i in range(3)]

    def validate(self, customers: list[str]) -> None:
        if not customers:
            raise ValueError("empty customer list")

    def save(self, customers: list[str]) -> int:
        return len(customers)


def summarize(customers: list[str]) -> str:
    return f"{len(customers)} customer(s) processed"
