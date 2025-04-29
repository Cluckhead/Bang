# views/maxmin_views.py
# This module defines the Flask Blueprint and routes for the Max/Min Value Breach feature.
# It provides web endpoints for a dashboard summarizing breaches across configured files
# and a details page listing specific securities that fall outside the configured
# maximum or minimum thresholds.
# It fetches configuration and data processing logic from config.py and maxmin_processing.py.

from flask import Blueprint, render_template, request, url_for, current_app
import os
import logging
import urllib.parse
from maxmin_processing import (
    get_breach_summary,
    get_breach_details,
    DEFAULT_MAX_THRESHOLD,
    DEFAULT_MIN_THRESHOLD,
)
from config import DATA_FOLDER, ID_COLUMN, MAXMIN_THRESHOLDS

maxmin_bp = Blueprint("maxmin_bp", __name__, template_folder="../templates")


def _get_threshold_overrides(request_args):
    """Helper function to parse max/min overrides from request arguments."""
    override_max = None
    override_min = None
    max_str = request_args.get("max")
    min_str = request_args.get("min")
    if max_str:
        try:
            override_max = float(max_str)
        except ValueError:
            current_app.logger.warning(
                f"Invalid override max value '{max_str}' received."
            )
    if min_str:
        try:
            override_min = float(min_str)
        except ValueError:
            current_app.logger.warning(
                f"Invalid override min value '{min_str}' received."
            )
    return override_max, override_min


@maxmin_bp.route("/maxmin/dashboard/")  # Trailing slash allows optional group
@maxmin_bp.route("/maxmin/dashboard/<group_name>")
def dashboard(group_name=None):
    """
    Displays the Max/Min Value Breach dashboard.
    Shows all files if no group_name is specified, otherwise filters by group.
    Allows temporary threshold overrides via query parameters.
    """
    if group_name:
        current_app.logger.info(
            f"Accessing max/min breach dashboard for group: {group_name}"
        )
        title = f"{group_name.capitalize()} Max/Min Breach Dashboard"
        # Filter the threshold config for the specified group
        threshold_config = {
            filename: config
            for filename, config in MAXMIN_THRESHOLDS.items()
            if config.get("group") == group_name
        }
        if not threshold_config:
            current_app.logger.warning(
                f"No files found for Max/Min group: {group_name}"
            )
            # Optionally, redirect or show an error/empty page
            # return render_template('error.html', message=f"Invalid Max/Min group specified: {group_name}"), 404
    else:
        current_app.logger.info("Accessing main max/min breach dashboard (all groups).")
        title = "Max/Min Value Breach Dashboard (All)"
        threshold_config = MAXMIN_THRESHOLDS  # Use all configured thresholds

    try:
        # Check for user overrides from query parameters
        override_max, override_min = _get_threshold_overrides(request.args)

        include_distressed = request.args.get("include_distressed", "0") == "1"

        # Fetch summary data using the appropriate config and overrides
        summary_data = get_breach_summary(
            data_folder=current_app.config["DATA_FOLDER"],
            threshold_config=threshold_config,
            override_max=override_max,
            override_min=override_min,
            include_distressed=include_distressed,
        )

        # Determine the thresholds that were actually applied for display
        # If overrides were used, they apply to all items. Otherwise, defaults vary.
        # We'll pass the override values (or None) to the template,
        # and the template will display either the override or the per-item config threshold.
        applied_max = override_max
        applied_min = override_min

        # Add details URLs - these always link using the file's *configured* thresholds (not overrides)
        for data in summary_data.values():
            # If overrides are active, add them as query params to the details links
            details_url_kwargs = {"filename": data["filename"], "breach_type": "max"}
            if applied_max is not None:
                details_url_kwargs["max"] = applied_max
            if applied_min is not None:
                details_url_kwargs["min"] = applied_min
            data["max_details_url"] = url_for(".details", **details_url_kwargs)

            details_url_kwargs = {"filename": data["filename"], "breach_type": "min"}
            if applied_max is not None:
                details_url_kwargs["max"] = applied_max
            if applied_min is not None:
                details_url_kwargs["min"] = applied_min
            data["min_details_url"] = url_for(".details", **details_url_kwargs)

        summary_list = list(summary_data.values())

        return render_template(
            "maxmin_dashboard.html",
            summary_data=summary_list,
            dashboard_title=title,
            group_name=group_name,
            # Pass the override values so the form can be pre-filled
            applied_max=applied_max,
            applied_min=applied_min,
            # Pass defaults for the form placeholder text
            DEFAULT_MAX_THRESHOLD=DEFAULT_MAX_THRESHOLD,
            DEFAULT_MIN_THRESHOLD=DEFAULT_MIN_THRESHOLD,
            include_distressed=include_distressed,
        )
    except Exception as e:
        current_app.logger.error(
            f"Error generating max/min dashboard (group: {group_name}): {e}",
            exc_info=True,
        )
        return (
            render_template("error.html", message=f"Could not generate {title}."),
            500,
        )


@maxmin_bp.route("/maxmin/details/<path:filename>/<breach_type>")
def details(filename, breach_type):
    """Displays the detailed list of max or min breaches for a specific file, using its configured thresholds."""
    current_app.logger.info(
        f"Accessing max/min breach details for file: {filename}, type: {breach_type}"
    )
    try:
        # Check for max/min overrides in query params
        max_str = request.args.get("max")
        min_str = request.args.get("min")
        file_config = MAXMIN_THRESHOLDS.get(filename, {})
        if max_str is not None:
            try:
                max_threshold = float(max_str)
            except ValueError:
                max_threshold = file_config.get("max", DEFAULT_MAX_THRESHOLD)
                current_app.logger.warning(
                    f"Invalid max override '{max_str}' for {filename}, using config default."
                )
        else:
            max_threshold = file_config.get("max", DEFAULT_MAX_THRESHOLD)
        if min_str is not None:
            try:
                min_threshold = float(min_str)
            except ValueError:
                min_threshold = file_config.get("min", DEFAULT_MIN_THRESHOLD)
                current_app.logger.warning(
                    f"Invalid min override '{min_str}' for {filename}, using config default."
                )
        else:
            min_threshold = file_config.get("min", DEFAULT_MIN_THRESHOLD)
        display_name = file_config.get("display_name", filename)

        if not file_config:
            current_app.logger.warning(
                f"Max/Min thresholds not configured for file: {filename}. Using defaults."
            )

        include_distressed = request.args.get("include_distressed", "0") == "1"

        current_app.logger.debug(
            f"DETAILS: filename={filename}, breach_type={breach_type}, max={max_threshold}, min={min_threshold}, include_distressed={include_distressed}"
        )
        breaches, total_count = get_breach_details(
            filename,
            breach_type=breach_type,
            data_folder=current_app.config["DATA_FOLDER"],
            max_threshold=max_threshold,  # Use file-specific or override threshold
            min_threshold=min_threshold,  # Use file-specific or override threshold
            include_distressed=include_distressed,
        )
        current_app.logger.debug(
            f"DETAILS: Returned {len(breaches)} breaches (total_count={total_count}) for include_distressed={include_distressed}"
        )
        # Prepare static columns for table header (from first item if available)
        static_columns = []
        if breaches:
            static_columns = list(breaches[0].get("static_info", {}).keys())
        # Generate URLs for security details page
        for item in breaches:
            safe_sec_id = urllib.parse.quote_plus(str(item["id"]))
            # Use the metric name (derived from filename, e.g., 'sec_Spread')
            metric_name = item["file"].replace(".csv", "")
            item["details_url"] = url_for(
                "security.security_details",
                metric_name=metric_name,
                security_id=safe_sec_id,
            )
        # Get the dashboard URL to link back to
        group = file_config.get("group")
        if group:
            dashboard_url = url_for(".dashboard", group_name=group)
        else:
            dashboard_url = url_for(".dashboard")  # Link to main dashboard if no group

        return render_template(
            "maxmin_details.html",
            filename=filename,
            display_name=display_name,  # Pass display name to template
            breach_type=breach_type,
            breaches=breaches,
            max_threshold=max_threshold,  # Pass the actual threshold used
            min_threshold=min_threshold,  # Pass the actual threshold used
            total_count=total_count,
            static_columns=static_columns,
            id_column=ID_COLUMN,
            dashboard_url=dashboard_url,  # Add URL for back button
            include_distressed=include_distressed,
        )
    except FileNotFoundError:
        current_app.logger.error(
            f"Data file not found for max/min details: {os.path.join(current_app.config['DATA_FOLDER'], filename)}"
        )
        return (
            render_template(
                "error.html",
                message=f"Data file '{filename}' not found for Max/Min details.",
            ),
            404,
        )
    except Exception as e:
        current_app.logger.error(
            f"Error generating max/min details for {filename}: {e}", exc_info=True
        )
        return (
            render_template(
                "error.html",
                message=f"Could not generate max/min details for {filename} ({breach_type}).",
            ),
            500,
        )
