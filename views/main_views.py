# This file defines the routes related to the main, top-level views of the application.
# It primarily handles the dashboard or index page.

"""
Blueprint for main application routes, like the index page.
"""
from flask import Blueprint, render_template, current_app, url_for, request, Response, jsonify, redirect, flash
from typing import Any, Dict, List, Union, Optional
import os
import pandas as pd
import traceback
from datetime import datetime, timedelta
import json
import time

# Import necessary functions/constants from other modules
# Removed: from config import DATA_FOLDER
from core.data_loader import load_and_process_data
from analytics.metric_calculator import calculate_latest_metrics
from analytics.file_delivery_processing import load_monitors, update_log, build_dashboard_summary
from core.utils import check_holidays, load_fund_groups

# Import functions for Issues, Exceptions, Watchlist, and Tickets data
import analytics.issue_processing as issue_processing
import analytics.ticket_processing as ticket_processing
from views.exclusion_views import load_exclusions
from views.watchlist_views import load_watchlist

# Define the blueprint for main routes
main_bp = Blueprint("main", __name__)


def get_issues_count(data_folder_path: str) -> int:
    """Get count of open issues."""
    try:
        issues_df = issue_processing.load_issues(data_folder_path)
        if issues_df.empty:
            return 0
        # Count only open issues
        open_issues = issues_df[issues_df['Status'] == 'Open']
        return len(open_issues)
    except Exception as e:
        current_app.logger.error(f"Error getting issues count: {e}")
        return 0


def get_exceptions_count(data_folder_path: str) -> int:
    """Get count of active exceptions/exclusions."""
    try:
        exclusions_list = load_exclusions(data_folder_path)
        if not exclusions_list:
            return 0

        current_date = datetime.now().date()
        active_count = 0

        for exclusion in exclusions_list:
            # Support both "EndDate" and legacy "End Date" keys
            end_date_raw = exclusion.get("EndDate", exclusion.get("End Date"))

            # Treat missing / blank / NaT as active
            if end_date_raw in (None, "", pd.NaT) or pd.isna(end_date_raw):
                active_count += 1
                continue

            # Ensure we have a datetime object for comparison
            if not isinstance(end_date_raw, datetime):
                try:
                    end_date_parsed = pd.to_datetime(end_date_raw, errors="coerce")
                except Exception:
                    end_date_parsed = pd.NaT
            else:
                end_date_parsed = end_date_raw

            if pd.isna(end_date_parsed):
                # Could not parse – assume active
                active_count += 1
                continue

            if end_date_parsed.date() >= current_date:
                active_count += 1

        return active_count

    except Exception as e:
        current_app.logger.error(f"Error getting exceptions count: {e}")
        return 0


def get_watchlist_count(data_folder_path: str) -> int:
    """Get count of active watchlist items."""
    try:
        watchlist_list = load_watchlist(data_folder_path)
        if not watchlist_list:
            return 0
        # Count only active watchlist items
        active_count = 0
        for item in watchlist_list:
            status = item.get('Status', 'Active')
            if status != 'Cleared':
                active_count += 1
        return active_count
    except Exception as e:
        current_app.logger.error(f"Error getting watchlist count: {e}")
        return 0


def get_fund_specific_counts(data_folder_path: str, fund_code: str) -> Dict[str, int]:
    """Get counts for a specific fund for Issues, Exceptions, and Watchlist."""
    counts = {"Issues": 0, "Exceptions": 0, "Watchlist": 0}
    
    try:
        # Issues count for this fund
        issues_df = issue_processing.load_issues(data_folder_path)
        if not issues_df.empty:
            fund_issues = issues_df[
                (issues_df['Status'] == 'Open') & 
                (issues_df['FundImpacted'] == fund_code)
            ]
            counts["Issues"] = len(fund_issues)
        
        # Exceptions - these are security-level, so we'd need to check if the fund holds those securities
        # For now, we'll show 0 as this requires cross-referencing with holdings data
        counts["Exceptions"] = 0
        
        # Watchlist - also security-level, same approach
        counts["Watchlist"] = 0
        
    except Exception as e:
        current_app.logger.error(f"Error getting fund-specific counts for {fund_code}: {e}")
    
    return counts


def create_default_dashboard_kpis(kpi_json_path: str) -> None:
    """Create a default dashboard_kpis.json file with empty but valid structure."""
    try:
        # Ensure the directory exists (only if there's a directory in the path)
        directory = os.path.dirname(kpi_json_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        # Create default structure
        default_kpis = {
            "timestamp": datetime.now().isoformat(),
            "staleness": {},
            "maxmin": {},
            "file_delivery": [],
            "zscore_metrics": {},
            "price_matching": {}
        }
        
        # Write the default file
        with open(kpi_json_path, "w", encoding="utf-8") as f:
            json.dump(default_kpis, f, indent=2)
        
        current_app.logger.info(f"Created default dashboard_kpis.json at {kpi_json_path}")
        
    except Exception as e:
        current_app.logger.error(f"Error creating default dashboard_kpis.json: {e}")


@main_bp.route("/flags/zscore")
def zscore_flags() -> str:
    """Displays all fund-metric pairs with |Z-Score| > 2 from the cached KPI data."""
    data_folder = current_app.config["DATA_FOLDER"]
    kpi_json_path = os.path.join(data_folder, "dashboard_kpis.json")
    
    flagged_items = []
    try:
        with open(kpi_json_path, "r", encoding="utf-8") as f:
            kpis = json.load(f)
        
        zscore_metrics = kpis.get("zscore_metrics", {})
        for metric, fund_data_list in zscore_metrics.items():
            for fund_row in fund_data_list:
                fund_code = fund_row.get("Fund Code")
                for key, value in fund_row.items():
                    if "Z-Score" in key and value is not None and abs(value) > 2:
                        flagged_items.append({
                            "fund_code": fund_code,
                            "metric": metric,
                            "source_field": key.replace(" Z-Score", ""),
                            "z_score": value
                        })
        
        # Sort by absolute Z-score descending (most extreme first)
        flagged_items.sort(key=lambda x: abs(x['z_score']), reverse=True)
        
        current_app.logger.info(f"Found {len(flagged_items)} extreme Z-score flags (|Z| > 2)")

    except FileNotFoundError:
        current_app.logger.warning(f"Dashboard KPIs file not found at {kpi_json_path}, creating default file")
        create_default_dashboard_kpis(kpi_json_path)
        flagged_items = []  # Default to empty list since the new file won't have any data yet
    except Exception as e:
        current_app.logger.error(f"Could not load or process z-score flags: {e}")
        flagged_items = []
    
    return render_template("zscore_flags.html", flags=flagged_items)


@main_bp.route("/")
def index() -> str:
    """Renders the main dashboard page (`index.html`) using pre-calculated KPIs from dashboard_kpis.json."""
    data_folder = current_app.config["DATA_FOLDER"]
    kpi_json_path = os.path.join(data_folder, "dashboard_kpis.json")
    kpis = None
    try:
        with open(kpi_json_path, "r", encoding="utf-8") as f:
            kpis = json.load(f)
    except FileNotFoundError:
        current_app.logger.warning(f"Dashboard KPIs file not found at {kpi_json_path}, creating default file")
        create_default_dashboard_kpis(kpi_json_path)
        # Try to load the newly created file
        try:
            with open(kpi_json_path, "r", encoding="utf-8") as f:
                kpis = json.load(f)
        except Exception as e:
            current_app.logger.error(f"Error loading newly created dashboard KPIs file: {e}")
            kpis = None
    except Exception as e:
        current_app.logger.error(f"Could not load dashboard KPIs from {kpi_json_path}: {e}")
        kpis = None

    # --- Fallbacks if file missing or invalid ---
    zscore_metrics = kpis.get("zscore_metrics", {}) if kpis else {}
    file_delivery = kpis.get("file_delivery", []) if kpis else []
    staleness = kpis.get("staleness", {}) if kpis else {}
    maxmin = kpis.get("maxmin", {}) if kpis else {}
    last_run_time = kpis.get("timestamp") if kpis else None

    # --- Calculate last data refresh based on newest ts_*.csv file ---
    try:
        ts_files = [f for f in os.listdir(data_folder) if f.startswith("ts_") and f.endswith(".csv")]
        if ts_files:
            # Find the most recently modified TS file
            latest_ts_file = max(ts_files, key=lambda f: os.path.getmtime(os.path.join(data_folder, f)))
            latest_mtime = os.path.getmtime(os.path.join(data_folder, latest_ts_file))
            last_run_time = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
            # Determine staleness (older than 24 hours)
            is_data_stale = (datetime.now() - datetime.fromtimestamp(latest_mtime)) > timedelta(hours=24)
        else:
            # If no TS files found, treat data as stale
            is_data_stale = True
    except Exception as e:
        current_app.logger.error(f"Error computing last data refresh time from TS files: {e}")
        # Fallback: if KPI timestamp exists use it for staleness calculation, otherwise mark stale
        if last_run_time:
            try:
                parsed_dt = datetime.strptime(last_run_time, "%Y-%m-%d %H:%M:%S") if ":" in last_run_time else datetime.fromisoformat(last_run_time)
                is_data_stale = (datetime.now() - parsed_dt) > timedelta(hours=24)
            except Exception:
                is_data_stale = False
        else:
            is_data_stale = True

    # --- Fund Group Filter Setup (still needed for dropdown) ---
    selected_fund_group = request.args.get("fund_group", None)
    fund_groups_dict = load_fund_groups(data_folder)
    filtered_fund_groups = fund_groups_dict.copy() if fund_groups_dict else {}

    # --- KPI Summary Tiles ---
    # Calculate total funds and fund health data from zscore_metrics
    total_funds = 0
    fund_health_rows = []
    # Collect list of metrics present in zscore_metrics for dynamic columns
    metric_names = sorted(zscore_metrics.keys()) if zscore_metrics else []

    fund_health_columns = ["Fund", "RAG"] + metric_names + ["Issues", "Exceptions", "Watchlist"]
    fund_codes = set()
    # Aggregate all fund codes from all metrics
    for metric_data in zscore_metrics.values():
        for row in metric_data:
            fund_codes.add(row.get("Fund Code"))
    fund_codes = sorted([fc for fc in fund_codes if fc])
    total_funds = len(fund_codes)
    # Build a nested dict of z-scores per fund per metric, and track fund-level max |Z|
    fund_metric_z = {}
    fund_max_z = {}
    for metric_name, metric_data in zscore_metrics.items():
        for row in metric_data:
            fund = row.get("Fund Code")
            # Collect numeric Z-score values in this row
            z_scores = [v for k, v in row.items() if isinstance(v, (int, float)) and "Z-Score" in k]
            max_abs_z = max([abs(z) for z in z_scores if z is not None], default=0)
            # Store per-metric z
            fund_metric_z.setdefault(fund, {})[metric_name] = max_abs_z
            # Track fund-level max
            if fund not in fund_max_z or max_abs_z > fund_max_z[fund]:
                fund_max_z[fund] = max_abs_z
    # --- Fund Health Table ---
    for fund in fund_codes:
        max_z = fund_max_z.get(fund, 0)
        if max_z > 3:
            rag = "Red"
        elif max_z > 2:
            rag = "Amber"
        else:
            rag = "Green"
        # Use existing helper for counts
        fund_counts = get_fund_specific_counts(data_folder, fund)

        row_dict = {
            "Fund": fund,
            "RAG": rag,
            "Issues": fund_counts["Issues"],
            "Exceptions": fund_counts["Exceptions"],
            "Watchlist": fund_counts["Watchlist"],
        }

        # Insert per-metric z-scores (default to None if missing)
        for m in metric_names:
            row_dict[m] = fund_metric_z.get(fund, {}).get(m)

        fund_health_rows.append(row_dict)

    # If a fund group filter is selected, apply it to the fund health rows
    if selected_fund_group and selected_fund_group in fund_groups_dict:
        allowed_funds = set(fund_groups_dict[selected_fund_group])
        fund_health_rows = [row for row in fund_health_rows if row["Fund"] in allowed_funds]
        total_funds = len(allowed_funds)
    # --- KPI Tiles ---
    issues_count = get_issues_count(data_folder)
    exceptions_count = get_exceptions_count(data_folder)
    watchlist_count = get_watchlist_count(data_folder)
    unallocated_tickets_count = ticket_processing.get_unallocated_tickets_count(data_folder)
    
    kpi_tiles = [
        {"title": "Total Funds", "value": total_funds, "link": url_for("main.index")},
        {"title": "Unallocated Tickets", "value": unallocated_tickets_count, "link": url_for("ticket_bp.manage_tickets"), "highlight": unallocated_tickets_count > 0},
        {"title": "Open Issues", "value": issues_count, "link": url_for("issue_bp.manage_issues")},
        {"title": "Active Exceptions", "value": exceptions_count, "link": url_for("exclusion_bp.manage_exclusions")},
        {"title": "Watchlist Items", "value": watchlist_count, "link": url_for("watchlist_bp.manage_watchlist")},
    ]

    # --- Data Quality Tiles (from cached data) ---
    data_quality_tiles = []
    
    # Staleness Summary
    total_stale_securities = 0
    total_securities_checked = 0
    for file_name, stale_data in staleness.items():
        if isinstance(stale_data, dict):
            total_stale_securities += stale_data.get("stale_count", 0)
            total_securities_checked += stale_data.get("total_count", 0)
    
    stale_percentage = (total_stale_securities / total_securities_checked * 100) if total_securities_checked > 0 else 0
    data_quality_tiles.append({
        "title": "Stale Securities",
        "value": total_stale_securities,
        "subtitle": f"{stale_percentage:.1f}% of {total_securities_checked:,}",
        "link": url_for("staleness_bp.dashboard"),
        "highlight": total_stale_securities > 0
    })
    
    # Max/Min Breaches Summary
    total_max_breaches = 0
    total_min_breaches = 0
    for file_name, breach_data in maxmin.items():
        if isinstance(breach_data, dict):
            total_max_breaches += breach_data.get("max_breach_count", 0)
            total_min_breaches += breach_data.get("min_breach_count", 0)
    
    total_breaches = total_max_breaches + total_min_breaches
    data_quality_tiles.append({
        "title": "Threshold Breaches",
        "value": total_breaches,
        "subtitle": f"Max: {total_max_breaches}, Min: {total_min_breaches}",
        "link": url_for("maxmin_bp.dashboard"),
        "highlight": total_breaches > 0
    })
    
    # Z-Score Extremes (|Z| > 2)
    extreme_z_count = 0
    for metric_data in zscore_metrics.values():
        for row in metric_data:
            z_scores = [v for k, v in row.items() if isinstance(v, (int, float)) and "Z-Score" in k]
            max_z = max([abs(z) for z in z_scores if z is not None], default=0)
            if max_z > 2:
                extreme_z_count += 1
    
    data_quality_tiles.append({
        "title": "Extreme Z-Scores",
        "value": extreme_z_count,
        "subtitle": f"Fund-metrics with |Z| > 2",
        "link": url_for("main.zscore_flags"),
        "highlight": extreme_z_count > 0
    })
    
    # Price Matching Summary
    price_matching = kpis.get("price_matching", {}) if kpis else {}
    match_percentage = price_matching.get("match_percentage", 0)
    total_comparisons = price_matching.get("total_comparisons", 0)
    latest_date = price_matching.get("latest_date", "Unknown")
    
    # Highlight if error or match rate below 90%
    has_error = "error" in price_matching
    low_match_rate = match_percentage < 90 if not has_error else False
    
    if has_error:
        display_value = "Error"
        subtitle = f"Check failed: {latest_date}"
    else:
        display_value = f"{match_percentage}%"
        subtitle = f"{total_comparisons:,} comparisons on {latest_date}"
    
    data_quality_tiles.append({
        "title": "Price Matching",
        "value": display_value,
        "subtitle": subtitle,
        "link": url_for("price_matching_bp.dashboard"),  # We'll create this next
        "highlight": has_error or low_match_rate
    })
    # --- File Delivery Tiles ---
    file_delivery_tiles = []
    for item in file_delivery:
        # Determine previous business day (Mon→Fri=previous Fri)
        today = datetime.now().date()
        if today.weekday() == 0:  # Monday
            prev_bd = today - timedelta(days=3)
        elif today.weekday() == 6:  # Sunday
            prev_bd = today - timedelta(days=2)
        else:
            prev_bd = today - timedelta(days=1)

        file_date_str = item.get("file_date")
        file_date = None
        try:
            if file_date_str:
                file_date = datetime.fromisoformat(file_date_str).date()
        except Exception:
            file_date = None

        missing_prev_bd = file_date != prev_bd if file_date else True

        delta_comp = item.get("delta_completeness")
        change_flag = abs(delta_comp) > 1 if delta_comp is not None else False

        highlight_flag = change_flag or missing_prev_bd or item.get("status") == "missing"

        tile = {
            "title": item.get("display_name"),
            "value": f"{item.get('completeness_pct')}%" if item.get("status") != "missing" else "-",
            "delta_rows": item.get("delta_rows"),
            "link": url_for('file_delivery_bp.dashboard'),
            "highlight": highlight_flag,
        }
        file_delivery_tiles.append(tile)
    # --- Holiday Checking ---
    holiday_info = check_holidays(data_folder)
    # --- Data Staleness/MaxMin/Other KPIs can be passed as needed ---
    # --- Render ---
    return render_template(
        "dashboard.html",
        kpi_tiles=kpi_tiles,
        data_quality_tiles=data_quality_tiles,
        file_delivery_tiles=file_delivery_tiles,
        fund_health_columns=fund_health_columns,
        fund_health_rows=fund_health_rows,
        last_run_time=last_run_time,
        is_data_stale=is_data_stale,  # Calculated above
        holiday_info=holiday_info,
        fund_groups=filtered_fund_groups,
        selected_fund_group=selected_fund_group,
    )


@main_bp.route("/refresh_checks", methods=["POST"])
def refresh_checks() -> Response:
    """Endpoint to synchronously run all data-quality checks and refresh the KPI cache.

    Returns JSON status so that the dashboard can reload when complete.
    """
    try:
        start_time = time.perf_counter()
        try:
            import run_all_checks  # noqa: WPS433 (runtime import needed)
        except ModuleNotFoundError as mnfe:
            # Provide a lightweight stub of the 'filelock' package if it's missing.
            if mnfe.name != "filelock":
                raise  # re-raise for non-filelock issues
            import sys, types

            filelock_stub = types.ModuleType("filelock")

            class _DummyLock:  # noqa: N801 – simple stub class
                def __init__(self, *args, **kwargs):
                    pass

                def __enter__(self):  # noqa: D401
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):  # noqa: D401
                    return False  # propagate exceptions

                def acquire(self, *args, **kwargs):  # noqa: D401
                    return True

                def release(self):  # noqa: D401
                    pass

            filelock_stub.FileLock = _DummyLock
            filelock_stub.Timeout = Exception
            sys.modules["filelock"] = filelock_stub

            import run_all_checks  # import succeeds with stub

        # Run the checks (this may take a few seconds).
        run_all_checks.main()

        duration = time.perf_counter() - start_time
        current_app.logger.info("Refresh checks endpoint completed in %.2f seconds", duration)
        return jsonify({"status": "ok"})

    except Exception as exc:  # pragma: no cover – defensive guard
        current_app.logger.error("Failed to refresh checks: %s", exc, exc_info=True)
        return jsonify({"status": "error", "message": str(exc)[:200]}), 500
