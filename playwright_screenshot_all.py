# <Purpose>
# This script uses Playwright to automatically visit every main page and open every modal (with example data)
# in the Simple Data Checker web app, saving screenshots of each. It is intended for UI regression, documentation,
# and QA. Example data is used for all dynamic routes and modal forms. Screenshots are saved in the 'screenshots/'
# directory, named by page and modal. Requires Playwright and the web app running locally (default: http://localhost:5000).
# It also includes enhanced logging and attempts to interact with UI elements like toggles based on README info.
# It skips UI interactions on pages where errors are detected.
#
# Usage (PowerShell):
#   python playwright_screenshot_all.py
#
# Prerequisites:
#   pip install playwright
#   playwright install
#   (Start your Flask app on http://localhost:5000)

import os
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, expect
from config import PLAYWRIGHT_EXAMPLE_DATA, PLAYWRIGHT_SELECTORS

# --- Configuration ---
BASE_URL = os.environ.get("SIMPLE_DATA_CHECKER_BASE_URL", "http://localhost:5000")
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)
LOG_FILE = SCREENSHOT_DIR / "Playwright.log"

# Example data for dynamic routes
EXAMPLE_METRIC = (
    "Metric1"  # Used for /metric/ - might fail if ts_Metric1.csv doesn't exist
)
EXAMPLE_SECURITY_METRIC = "spread"  # Use a likely valid metric for security details
EXAMPLE_SECURITY_ID = "XS4363421503"
EXAMPLE_FUND_CODE = "IG01"
EXAMPLE_COMPARISON = "spread"
EXAMPLE_CURRENCY = "USD"
EXAMPLE_MAXMIN_FILE = "sec_Spread.csv"
EXAMPLE_BREACH_TYPE = "max"
EXAMPLE_FUND_GROUP = "IG01"  # Example fund group for filtering

EXAMPLE_INPUTS = {
    "metric": EXAMPLE_METRIC,
    "security_metric": EXAMPLE_SECURITY_METRIC,
    "security_id": EXAMPLE_SECURITY_ID,
    "fund_code": EXAMPLE_FUND_CODE,
    "comparison": EXAMPLE_COMPARISON,
    "currency": EXAMPLE_CURRENCY,
    "maxmin_file": EXAMPLE_MAXMIN_FILE,
    "breach_type": EXAMPLE_BREACH_TYPE,
    "fund_group": EXAMPLE_FUND_GROUP,
}


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(msg)


# List of (name, url, [modal_actions], [ui_interactions])
# Removed routes that returned 404 in previous runs
PAGES = [
    ("dashboard", "/", [], []),
    (
        "metric_detail",
        f"/metric/{EXAMPLE_METRIC}",
        ["inspect_modal"],
        ["toggle_sp_comparison"],
    ),
    ("securities_summary", "/security/summary", [], []),
    (
        "securities_summary_filtered",
        f"/security/summary?fund_group={EXAMPLE_FUND_GROUP}",
        [],
        [],
    ),
    # ("security_details", f"/security/details/{EXAMPLE_SECURITY_METRIC}/{EXAMPLE_SECURITY_ID}", ["raise_issue_modal", "add_exclusion_modal"], []), # Removed 404
    ("fund_overview", f"/fund/{EXAMPLE_FUND_CODE}", [], []),
    ("fund_duration_details", f"/fund/duration_details/{EXAMPLE_FUND_CODE}", [], []),
    ("exclusions", "/exclusions", [], []),
    ("comparison_summary", f"/compare/{EXAMPLE_COMPARISON}/summary", [], []),
    (
        "comparison_summary_filtered",
        f"/compare/{EXAMPLE_COMPARISON}/summary?fund_group={EXAMPLE_FUND_GROUP}",
        [],
        [],
    ),
    (
        "comparison_details",
        f"/compare/{EXAMPLE_COMPARISON}/details/{EXAMPLE_SECURITY_ID}",
        [],
        [],
    ),
    ("weights_check", "/weights/check", [], []),
    ("curve_summary", "/curve/summary", [], []),
    ("curve_details", f"/curve/details/{EXAMPLE_CURRENCY}", [], []),
    ("issues", "/issues", ["close_issue_modal"], []),
    ("attribution_summary", "/attribution/summary", [], []),
    # ("attribution_security", f"/attribution/security/{EXAMPLE_FUND_CODE}", [], []), # Removed 404
    # ("attribution_radar", f"/attribution/radar/{EXAMPLE_FUND_CODE}", [], []), # Removed 404
    # ("attribution_charts", f"/attribution/charts/{EXAMPLE_FUND_CODE}", [], []), # Removed 404
    ("maxmin_dashboard_all", "/maxmin/dashboard", [], []),
    ("maxmin_dashboard_yields", "/maxmin/dashboard/Yields", [], []),
    ("maxmin_dashboard_spreads", "/maxmin/dashboard/Spreads", [], []),
    (
        "maxmin_details",
        f"/maxmin/details/{EXAMPLE_MAXMIN_FILE}/{EXAMPLE_BREACH_TYPE}",
        [],
        [],
    ),
    ("watchlist", "/watchlist", ["add_watchlist_modal", "clear_watchlist_modal"], []),
    ("get_data", "/get_data", [], []),
    ("staleness_dashboard", "/staleness/dashboard", [], []),
]


# --- Modal interaction helpers ---
def open_modal(page, modal_type):
    selector = None
    if modal_type == "inspect_modal":
        selector = "button:has-text('Inspect')"
        log(
            f"    Example inputs for Inspect modal: metric={EXAMPLE_METRIC}, fund_code={EXAMPLE_FUND_CODE}, date_range=2023-01-01 to 2023-01-31, data_source=Original"
        )
    elif modal_type == "raise_issue_modal":
        selector = "button.btn-warning:has-text('Raise Data Issue')"
        log(
            f"    Example inputs for Raise Issue modal: security_id={EXAMPLE_SECURITY_ID}, user=TestUser, data_source=Production, date=2023-01-15, description=Test issue, jira_link=, in_scope=No"
        )
    elif modal_type == "add_exclusion_modal":
        selector = "button.btn-danger:has-text('Add Exclusion')"
        log(
            f"    Example inputs for Add Exclusion modal: security_id={EXAMPLE_SECURITY_ID}, reason=Test exclusion, user=TestUser"
        )
    elif modal_type == "add_watchlist_modal":
        selector = "button.btn-success:has-text('Add to Watchlist')"
        log(
            f"    Example inputs for Add to Watchlist modal: security_id={EXAMPLE_SECURITY_ID}, reason=Test watchlist, user=TestUser"
        )
    elif modal_type == "clear_watchlist_modal":
        selector = "button.btn-danger:has-text('Clear')"
        log(
            f"    Example inputs for Clear Watchlist modal: security_id={EXAMPLE_SECURITY_ID}, user=TestUser, reason=Test clear"
        )
    elif modal_type == "close_issue_modal":
        selector = "button.btn-success:has-text('Close')"
        log(
            f"    Example inputs for Close Issue modal: issue_id=1, user=TestUser, resolution=Test resolution"
        )
    else:
        log(f"[WARN] Unknown modal type: {modal_type}")
        return

    log(f"    Attempting modal: {modal_type}")
    log(f"    Using selector: {selector}")
    btn = page.query_selector(selector)
    if not btn:
        log(f"    [SKIP] Modal trigger button not found for selector: {selector}")
        return

    try:
        btn.click()
        page.wait_for_selector(".modal.show, .modal[aria-modal='true']", timeout=5000)
        time.sleep(0.5)
        page.screenshot(path=SCREENSHOT_DIR / f"modal_{modal_type}.png", full_page=True)
        log(f"    {modal_type} opened and screenshot saved.")
        time.sleep(0.2)  # Short pause before trying to close
        close_btn = page.query_selector(
            ".modal.show button.btn-secondary, .modal[aria-modal='true'] button.btn-secondary, .modal.show button[data-bs-dismiss='modal'], .modal[aria-modal='true'] button[data-bs-dismiss='modal']"
        )
        if close_btn:
            close_btn.click()
            time.sleep(0.2)  # Wait for modal to close
            log(f"    {modal_type} closed.")
        else:
            log(f"    [WARN] Close button not found for modal: {modal_type}")
    except Exception as e:
        log(f"[WARN] Could not open or interact with {modal_type}: {e}")


# --- UI Interaction Helpers ---
def perform_ui_interaction(page, interaction_type):
    log(f"  Performing UI interaction: {interaction_type}")
    if interaction_type == "toggle_sp_comparison":
        sp_toggle_selector = "input[type='checkbox'][id*='toggleSpData'], label:has-text('S&P Comparison') input[type='checkbox']"
        log(
            f"    Attempting to toggle S&P comparison using selector: {sp_toggle_selector}"
        )
        toggle = page.query_selector(sp_toggle_selector)
        if toggle:
            try:
                toggle.click()
                log(f"    Clicked S&P toggle.")
                time.sleep(1)  # Wait for UI update
                screenshot_path = SCREENSHOT_DIR / f"metric_detail_sp_toggled.png"
                page.screenshot(path=screenshot_path, full_page=True)
                log(f"    Saved screenshot after toggle: {screenshot_path}")
            except Exception as e:
                log(f"    [WARN] Failed to click S&P toggle or take screenshot: {e}")
        else:
            log(f"    [SKIP] S&P comparison toggle not found.")
    else:
        log(f"[WARN] Unknown UI interaction type: {interaction_type}")


# --- Main script ---
def main():
    if LOG_FILE.exists():
        LOG_FILE.unlink()
    log("=== Playwright Screenshot Run Started ===")
    log(f"Example input values: {EXAMPLE_INPUTS}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        for name, url, modals, interactions in PAGES:
            log(f"Visiting {url} ...")
            log(f"  Example inputs for this page: {EXAMPLE_INPUTS}")
            page_had_errors = False  # Flag to track page errors
            try:
                response = page.goto(BASE_URL + url, timeout=10000)
                page.wait_for_load_state("networkidle", timeout=5000)
                time.sleep(1)

                # Explicitly check status code and log 404s
                status = response.status if response else None
                log(f"  HTTP Status: {status}")
                if status == 404:
                    log("  [STATUS] Received 404 Not Found from server.")
                    page_had_errors = (
                        True  # Treat 404 as an error for skipping interactions
                    )

                # Log page title (even for 404s)
                try:
                    title = page.title()
                    log(f"  Page title: {title}")
                except Exception as e:
                    log(f"  [WARN] Could not get page title: {e}")

                # Log error banners/messages if present
                error_banners = []
                if status != 404:
                    error_banners = page.query_selector_all(
                        ".alert-danger, .alert-warning, .alert-info"
                    )
                    if not error_banners:
                        log("  No warning/error banners detected on page.")
                    else:
                        page_had_errors = True  # Banners indicate potential issues
                        for idx, banner in enumerate(error_banners):
                            try:
                                text = banner.inner_text().strip().replace("\n", " ")
                                log(f"  Banner {idx+1}: {text}")
                            except Exception as e:
                                log(f"  [WARN] Could not read banner text: {e}")

                screenshot_path = SCREENSHOT_DIR / f"{name}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                log(f"  Saved screenshot: {screenshot_path}")

                # Perform UI interactions only if page loaded without errors/banners
                if not page_had_errors:
                    for interaction in interactions:
                        perform_ui_interaction(page, interaction)
                elif interactions:
                    log(
                        "  [SKIP] Skipping UI interactions due to detected page errors/banners or 404 status."
                    )

                # Attempt to open modals (even on pages with errors, button might still exist)
                for modal in modals:
                    open_modal(page, modal)
            except Exception as e:
                log(f"[ERROR] Failed to process {url}: {e}")

        browser.close()
    log("=== Playwright Screenshot Run Finished ===")


if __name__ == "__main__":
    main()
