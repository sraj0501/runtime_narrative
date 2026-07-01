"""Demonstrates ConsoleRenderer's built-in color and emoji customization.

Two things are shown together here:

1. Colorful output is automatic and requires no configuration -- success lines,
   warnings, and the failure box are colored by ConsoleRenderer whenever the
   optional "console" extra (typer) is installed. This example doesn't do
   anything special to get color; it's just what story()/stage() produce.
2. level_icons lets you prepend any string -- typically an emoji -- to
   LogRecorded lines, per log level, without writing a custom renderer.

Requires the "console" extra for color: uv sync --extra console
(structlog extra is optional, for the richer log line style: uv sync --extra structlog)

Run:
    uv run python examples/colorful_errors_and_emojis.py
"""
import logging

from runtime_narrative import ConsoleRenderer, NarrativeLogHandler, stage, story

logger = logging.getLogger("checkout")
logger.setLevel(logging.DEBUG)
logger.addHandler(NarrativeLogHandler(level=logging.DEBUG))
logger.propagate = False

# Any string works as an icon -- emoji, ASCII tags, whatever fits your terminal.
renderer = ConsoleRenderer(
    level_icons={
        "debug": "🔍 ",
        "info": "ℹ️ ",
        "warning": "⚠️ ",
        "error": "🔥 ",
        "critical": "💥 ",
    }
)


class InsufficientStockError(Exception):
    pass


print("=== Success story: emoji-prefixed log lines at every level ===")
with story("Checkout", renderers=[renderer]):
    with stage("Validate Cart"):
        logger.debug("cart contents loaded", extra={"items": 3})
        logger.info("cart validated")

    with stage("Apply Discount"):
        logger.warning("promo code expired, falling back to full price", extra={"code": "SUMMER25"})

print("\n=== Failure story: colorful failure box comes from ConsoleRenderer itself ===")
try:
    with story("Checkout", renderers=[renderer]):
        with stage("Reserve Inventory"):
            logger.error("stock check failed", extra={"sku": "BOOT-42"})
            raise InsufficientStockError("only 0 units left for SKU BOOT-42")
except InsufficientStockError:
    pass

print(
    "\nNote: the log-line icons above are configurable via level_icons. "
    "The story/stage glyphs and the red failure box are ConsoleRenderer's "
    "fixed built-in style -- always on, not currently configurable."
)
