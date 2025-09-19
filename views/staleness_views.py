# views/staleness_views.py
# This module defines the Flask routes for the Data Staleness feature.

from flask import Blueprint, render_template, request, url_for, current_app, redirect
import os
import logging
import urllib.parse
from analytics.staleness_processing import (
    get_staleness_summary,
    get_stale_securities_details,
)
from core.utils import load_exclusions
from core.config import (
    DATA_FOLDER,
    EXCLUSIONS_FILE,
    ID_COLUMN,
    COMPARISON_CONFIG,
    MAXMIN_THRESHOLDS,
)
from core import config

# Create blueprint
staleness_bp = Blueprint("staleness_bp", __name__, template_folder="../templates")

# --- Routes ---


def get_display_name_for_staleness_file(filename):
    """
    Returns a user-friendly display name for a staleness file, using COMPARISON_CONFIG and MAXMIN_THRESHOLDS.
    Falls back to a cleaned-up version of the filename if not found.
    """
    # Check COMPARISON_CONFIG (file1 and file2)
    for comp in COMPARISON_CONFIG.values():
        if filename == comp.get("file1"):
            return comp["display_name"]
        if filename == comp.get("file2"):
            # S&P overlay naming
            return f"S&P {comp['display_name']}"
    # Check MAXMIN_THRESHOLDS
    if filename in MAXMIN_THRESHOLDS:
        return MAXMIN_THRESHOLDS[filename].get("display_name", filename)
    # Fallback: remove extension, underscores, and common prefixes
    name = filename.replace(".csv", "")
    name = name.replace("sec_", "").replace("sp_", "").replace("_", " ")
    name = name.replace("SP", "S&P")
    return name.title()


@staleness_bp.route("/staleness/dashboard")
def dashboard():
    """Displays the staleness dashboard with summary counts for each file type."""
    current_app.logger.info("Accessing staleness dashboard.")
    try:
        # Get staleness threshold from query parameters, default to constant
        threshold_str = request.args.get(
            "threshold", str(config.STALENESS_THRESHOLD_DAYS)
        )
        try:
            threshold = int(threshold_str)
            if threshold < 0:
                threshold = 0  # Prevent negative thresholds
        except ValueError:
            threshold = config.STALENESS_THRESHOLD_DAYS
            current_app.logger.warning(
                f"Invalid threshold value '{threshold_str}' provided to dashboard, using default {threshold}."
            )

        # Load exclusions once for the summary
        exclusions_path = os.path.join(
            current_app.config["DATA_FOLDER"], EXCLUSIONS_FILE
        )
        exclusions_df = load_exclusions(exclusions_path)

        # Pass the threshold to the summary function
        summary_data = get_staleness_summary(
            data_folder=current_app.config["DATA_FOLDER"],
            exclusions_df=exclusions_df,
            threshold_days=threshold,
        )
        current_app.logger.info(
            f"Staleness summary generated: {len(summary_data)} files processed with threshold {threshold}."
        )

        # Prepare data for template (e.g., add detail URLs with threshold)
        summary_view_data = []
        for filename, data in summary_data.items():
            data["filename"] = filename
            data["display_name"] = get_display_name_for_staleness_file(filename)
            data["details_url"] = url_for(
                ".details", filename=filename, threshold=threshold
            )
            data["has_error"] = isinstance(data.get("stale_count"), str)
            summary_view_data.append(data)

        # Sort by stale count in descending order (most stale items first)
        # Move error items to the end
        summary_view_data.sort(
            key=lambda x: (
                x["has_error"],
                -1 * (x["stale_count"] if not x["has_error"] else 0),
            )
        )

        return render_template(
            "staleness_dashboard.html",
            summary_data=summary_view_data,
            current_threshold=threshold,
        )
    except Exception as e:
        current_app.logger.error(
            f"Error generating staleness dashboard: {e}", exc_info=True
        )
        # Render a simple error message or redirect
        return (
            render_template(
                "error.html", message="Could not generate staleness dashboard."
            ),
            500,
        )


@staleness_bp.route("/staleness/details/<path:filename>")
def details(filename):
    """Displays the detailed list of stale securities for a specific file."""
    current_app.logger.info(f"Accessing staleness details for file: {filename}")
    try:
        # Get staleness threshold from query parameters (now set by dashboard link), default if missing
        threshold_str = request.args.get(
            "threshold", str(config.STALENESS_THRESHOLD_DAYS)
        )
        try:
            threshold = int(threshold_str)
            if threshold < 0:
                threshold = 0  # Prevent negative thresholds
        except ValueError:
            threshold = config.STALENESS_THRESHOLD_DAYS
            current_app.logger.warning(
                f"Invalid threshold value '{threshold_str}', using default {threshold}."
            )

        # Load exclusions
        exclusions_path = os.path.join(
            current_app.config["DATA_FOLDER"], EXCLUSIONS_FILE
        )
        exclusions_df = load_exclusions(exclusions_path)

        # Get stale security details
        stale_securities, latest_date, total_count = get_stale_securities_details(
            filename,
            threshold_days=threshold,
            data_folder=current_app.config["DATA_FOLDER"],
            exclusions_df=exclusions_df,
        )
        current_app.logger.info(
            f"Found {len(stale_securities)} stale securities in {filename} with threshold {threshold}."
        )

        # Sort by days_stale in descending order (most stale items first)
        stale_securities.sort(key=lambda x: x["days_stale"], reverse=True)

        # Prepare static columns for table header (get from first item if available)
        static_columns = []
        if stale_securities:
            static_columns = list(stale_securities[0].get("static_info", {}).keys())

        # Generate URLs for security details page
        for item in stale_securities:
            # We need the metric name (derived from filename) and the security id
            # Ensure security ID is URL-safe
            safe_sec_id = urllib.parse.quote_plus(str(item["id"]))
            item["details_url"] = url_for(
                "security.security_details",  # CORRECTED - Use Flask's suggestion
                metric_name=item["metric_name"],
                security_id=safe_sec_id,
            )

        return render_template(
            "staleness_details.html",
            filename=filename,
            stale_securities=stale_securities,
            threshold=threshold,
            latest_date=latest_date,
            total_count=total_count,
            static_columns=static_columns,
            id_column=ID_COLUMN,  # Pass the ID column name for the template
        )
    except Exception as e:
        current_app.logger.error(
            f"Error generating staleness details for {filename}: {e}", exc_info=True
        )
        return (
            render_template(
                "error.html",
                message=f"Could not generate staleness details for {filename}.",
            ),
            500,
        )
