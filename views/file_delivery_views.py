# views/file_delivery_views.py
# Purpose: Flask Blueprint that exposes a dashboard summarising file delivery health
#          and an endpoint to fetch historical meta data for charting/modals.

from flask import Blueprint, render_template, current_app, jsonify, request
import logging

from analytics.file_delivery_processing import (
    load_monitors,
    update_log,
    build_dashboard_summary,
    get_time_series,
    get_column_completeness_comparison,
)

file_delivery_bp = Blueprint(
    "file_delivery_bp", __name__, url_prefix="/filedelivery", template_folder="../templates"
)

LOGGER = logging.getLogger(__name__)


@file_delivery_bp.route("/dashboard")
def dashboard():
    """Main dashboard page showing summary of latest deliveries."""
    monitors = load_monitors()
    # Update log before building summary (cheap – only new entries added)
    update_log(monitors)
    summary_rows = build_dashboard_summary(monitors)
    return render_template("file_delivery_dashboard.html", summary_data=summary_rows)


@file_delivery_bp.route("/history/<monitor_name>")
def history(monitor_name):
    """Return JSON time-series data for the requested monitor (for charts)."""
    days = int(request.args.get("days", 30))
    df_ts = get_time_series(monitor_name, days=days)
    if df_ts.empty:
        return jsonify({"status": "error", "message": "No data"}), 404
    # Convert to records for JS; drop heavy fields like headers
    cols_to_send = [
        "processed_ts",
        "rows",
        "completeness_pct",
        "filename",
        "headers_hash" if "headers_hash" in df_ts.columns else None,
    ]
    cols_to_send = [c for c in cols_to_send if c and c in df_ts.columns]
    records = df_ts[cols_to_send].to_dict(orient="records")
    return jsonify({"status": "ok", "data": records})


@file_delivery_bp.route("/columns/<monitor_name>")
def columns(monitor_name):
    """Return per-column completeness comparison JSON for modal."""
    rows = get_column_completeness_comparison(monitor_name)
    if not rows:
        return jsonify({"status": "error", "message": "Insufficient history"}), 404
    return jsonify({"status": "ok", "data": rows}) 