"""Demonstrates FailureDiagnosticsConfig — rich diagnostics, redaction, production caps.

FailureDiagnosticsConfig controls:
- failure_diagnostics: "lean" (default) or "rich" (captures local variables)
- redact_extra: additional key substrings to redact (on top of built-ins like
  "password", "token", "secret", "api_key")
- redact_patterns: regex patterns matched against local variable key names
- redact_callback: custom predicate — return True to redact the key
- runtime_environment: "production" caps traceback to 8 000 chars

Run:
    uv run python examples/diagnostics_config.py
"""
from runtime_narrative import FailureDiagnosticsConfig, stage, story


def process_payment(card_number: str, cvv: str, amount: float) -> None:
    internal_ref = "TXN-20260629-001"
    raise ValueError(f"insufficient funds for transaction {internal_ref}: amount={amount:.2f}")


print("=== lean mode (default) — no locals captured ===\n")
lean_config = FailureDiagnosticsConfig(failure_diagnostics="lean")

try:
    with story("Checkout", diagnostics_config=lean_config):
        with stage("Charge Card"):
            process_payment("4111111111111111", "123", 99.99)
except ValueError:
    pass

print("\n=== rich mode — locals captured, secrets redacted ===\n")
rich_config = FailureDiagnosticsConfig(
    failure_diagnostics="rich",
    # "card" is not in the built-in redact list, so add it explicitly.
    redact_extra=("card_number", "cvv"),
    # Redact any key whose name matches this pattern (regex, case-insensitive).
    redact_patterns=(r"pan$", r"^secret_"),
    # Custom predicate — redact anything ending with "_ref" in non-prod.
    redact_callback=lambda key: key.endswith("_ref"),
)

try:
    with story("Checkout", diagnostics_config=rich_config):
        with stage("Charge Card"):
            process_payment("4111111111111111", "123", 99.99)
except ValueError:
    pass

print("\n=== production mode — traceback capped at 8 000 chars ===\n")
prod_config = FailureDiagnosticsConfig(
    runtime_environment="production",
    failure_diagnostics="lean",
)

try:
    with story("Checkout", diagnostics_config=prod_config):
        with stage("Charge Card"):
            process_payment("4111111111111111", "123", 99.99)
except ValueError:
    pass
