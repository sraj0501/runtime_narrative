"""Demonstrates HtmlReportRenderer — self-contained HTML report on story completion.

The report includes a stage timeline bar chart and a failure detail section with
the traceback. Open the generated file in any browser.

Run:
    uv run python examples/html_report.py
    # Open examples_report.html in your browser.
"""
import time

from runtime_narrative import HtmlReportRenderer, stage, story

renderer = HtmlReportRenderer("examples_report.html", open_browser=False)

print("=== Running success story ===")
with story("Order Fulfillment", renderers=[renderer], total_stages=3):
    with stage("Validate Order"):
        time.sleep(0.02)
        order = {"id": "ORD-123", "amount": 149.00, "email": "alice@example.com"}

    with stage("Reserve Inventory"):
        time.sleep(0.05)
        reserved = {"sku": "BOOT-42", "qty": 1}

    with stage("Queue Shipment"):
        time.sleep(0.03)
        print(f"  Queued shipment for {order['id']}")

print("\n=== Running failure story ===")
try:
    with story("Nightly Sync", renderers=[renderer], total_stages=3):
        with stage("Pull Remote Records"):
            time.sleep(0.04)
            remote_rows = list(range(500))

        with stage("Merge Into Local DB"):
            time.sleep(0.06)

        with stage("Send Confirmation Email"):
            raise RuntimeError("SMTP connection refused on port 465 — check firewall rules")
except RuntimeError:
    pass

print("\nReport written to: examples_report.html")
