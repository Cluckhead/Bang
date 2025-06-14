"""
Blueprint for security-related routes (e.g., summary page and individual details).
"""

from flask import (
    Blueprint,
    render_template,
    jsonify,
    send_from_directory,
    url_for,
    current_app,
)
import os
import pandas as pd
import numpy as np
import traceback
from urllib.parse import unquote
from datetime import datetime
from flask import request  # Import request
import math
import json
import config
import re # Add import for regex

# Import necessary functions/constants from other modules
from config import (
    COLOR_PALETTE,
    STATIC_INFO_GROUPS,
)  # Keep palette and STATIC_INFO_GROUPS
from security_processing import (
    load_and_process_security_data,
    calculate_security_latest_metrics,
)

# Import the exclusion loading function
from utils import load_exclusions  # Import DataFrame-based load_exclusions from utils
from utils import replace_nan_with_none

# Add import for fund group utility
from utils import load_fund_groups, parse_fund_list

# Import get_holdings_for_security for fund holdings tile
from views.comparison_helpers import get_holdings_for_security

# Import get_active_exclusions, apply_security_filters, apply_security_sorting, paginate_security_data, load_filter_and_extract from security_helpers
from views.security_helpers import (
    get_active_exclusions,
    apply_security_filters,  # Renamed from _apply_security_filters
    apply_security_sorting,  # Renamed from _apply_security_sorting
    paginate_security_data,  # Renamed from _paginate_security_data
    load_filter_and_extract,
)

# Define the blueprint
security_bp = Blueprint("security", __name__, url_prefix="/security")

# Use config.SECURITIES_PER_PAGE for pagination

# Purpose: This file defines the Flask Blueprint and routes for security-level data checks, including summary and details pages, filtering, and static info display.


@security_bp.route("/summary")
def securities_page():
    """Renders a page summarizing potential issues in security-level data, with server-side pagination, filtering, and sorting.
    Adds support for filtering by fund group (from FundGroups.csv)."""
    current_app.logger.info("\n--- Starting Security Data Processing (Paginated) ---")

    # Retrieve the configured absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # --- Get Request Parameters ---
    page = request.args.get("page", 1, type=int)
    search_term = request.args.get("search_term", "", type=str).strip()
    sort_by = request.args.get("sort_by", None, type=str)
    sort_order = request.args.get("sort_order", "desc", type=str).lower()
    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"
    active_filters = {
        key.replace("filter_", ""): value
        for key, value in request.args.items()
        if key.startswith("filter_") and value
    }
    # --- Min = 0 Exclusion Toggle ---
    exclude_min_zero = request.args.get("exclude_min_zero", "true") == "true"
    # --- Fund Group Filter ---
    selected_fund_group = request.args.get("fund_group", None)
    current_app.logger.info(
        f"Request Params: Page={page}, Search='{search_term}', SortBy='{sort_by}', SortOrder='{sort_order}', Filters={active_filters}, Exclude Min = 0: {exclude_min_zero}, Fund Group: {selected_fund_group}"
    )

    # Collect active filters from request args (e.g., ?filter_Country=USA&filter_Sector=Tech)
    active_filters = {
        key.replace("filter_", ""): value
        for key, value in request.args.items()
        if key.startswith("filter_") and value  # Ensure value is not empty
    }
    current_app.logger.info(
        f"Request Params: Page={page}, Search='{search_term}', SortBy='{sort_by}', SortOrder='{sort_order}', Filters={active_filters}"
    )

    # --- Load Base Data ---
    spread_filename = "sec_Spread.csv"
    # Construct absolute path
    data_filepath = os.path.join(data_folder, spread_filename)
    filter_options = {}  # To store all possible options for filter dropdowns

    if not os.path.exists(data_filepath):
        current_app.logger.error(
            f"Error: The required file '{spread_filename}' not found."
        )
        return render_template(
            "securities_page.html",
            message=f"Error: Required data file '{spread_filename}' not found.",
            securities_data=[],
            pagination=None,
        )

    try:
        current_app.logger.info(f"Loading and processing file: {spread_filename}")
        # Pass the absolute data folder path
        df_long, static_cols = load_and_process_security_data(
            spread_filename, data_folder
        )

        if df_long is None or df_long.empty:
            current_app.logger.warning(
                f"Skipping {spread_filename} due to load/process errors or empty data."
            )
            return render_template(
                "securities_page.html",
                message=f"Error loading or processing '{spread_filename}'.",
                securities_data=[],
                pagination=None,
            )

        current_app.logger.info("Calculating latest metrics...")
        combined_metrics_df = calculate_security_latest_metrics(df_long, static_cols)

        if combined_metrics_df.empty:
            current_app.logger.warning(f"No metrics calculated for {spread_filename}.")
            return render_template(
                "securities_page.html",
                message=f"Could not calculate metrics from '{spread_filename}'.",
                securities_data=[],
                pagination=None,
            )

        # Define ID column name
        id_col_name = config.ISIN_COL  # <<< Use ISIN as the identifier

        # Check if the chosen ID column exists in the index or columns
        if id_col_name in combined_metrics_df.index.names:
            combined_metrics_df.index.name = (
                id_col_name  # Ensure index name is set if using index
            )
            combined_metrics_df.reset_index(inplace=True)
        elif id_col_name in combined_metrics_df.columns:
            pass  # ID is already a column
        else:
            # Fallback or error if ISIN isn't found
            old_id_col = combined_metrics_df.index.name or "Security ID"
            current_app.logger.warning(
                f"Warning: ID column '{id_col_name}' not found. Falling back to '{old_id_col}'."
            )
            if old_id_col in combined_metrics_df.index.names:
                combined_metrics_df.index.name = old_id_col
                combined_metrics_df.reset_index(inplace=True)
                id_col_name = old_id_col  # Use the fallback name
            elif old_id_col in combined_metrics_df.columns:
                id_col_name = old_id_col
            else:
                current_app.logger.error(
                    f"Error: Cannot find a usable ID column ('{id_col_name}' or fallback '{old_id_col}') in {spread_filename}."
                )
                return render_template(
                    "securities_page.html",
                    message=f"Error: Cannot identify securities in {spread_filename}.",
                    securities_data=[],
                    pagination=None,
                )

        # Store the original unfiltered dataframe's columns
        original_columns = combined_metrics_df.columns.tolist()
        # combined_metrics_df.reset_index(inplace=True) # Reset index to make ID a regular column - ALREADY DONE OR ID IS A COLUMN

        # --- Collect Filter Options (from the full dataset BEFORE filtering) ---
        current_app.logger.info("Collecting filter options...")
        # Ensure ID column is not treated as a filterable static column
        current_static_in_df = [
            col
            for col in static_cols
            if col in combined_metrics_df.columns and col != id_col_name
        ]
        for col in current_static_in_df:
            unique_vals = combined_metrics_df[col].unique().tolist()
            unique_vals = [
                item.item() if isinstance(item, np.generic) else item
                for item in unique_vals
            ]
            unique_vals = sorted(
                [val for val in unique_vals if pd.notna(val) and val != ""]
            )  # Remove NaN/empty and sort
            if unique_vals:  # Only add if there are valid options
                filter_options[col] = unique_vals

        # Sort filter options dictionary by key for consistent display order
        final_filter_options = dict(sorted(filter_options.items()))

        # --- Fund-group dict & active exclusions (prepare inputs for filter helper) ---
        fund_groups_dict = load_fund_groups(data_folder)
        active_exclusion_ids = get_active_exclusions(data_folder)

        # --- Apply all filters via helper ------------------------------------------------
        current_app.logger.info("Applying filters via helper...")
        # Use imported apply_security_filters
        combined_metrics_df = apply_security_filters(
            df=combined_metrics_df,
            id_col_name=id_col_name,
            search_term=search_term,
            fund_groups_dict=fund_groups_dict,
            selected_fund_group=selected_fund_group,
            active_exclusion_ids=active_exclusion_ids,
            active_filters=active_filters,
            exclude_min_zero=exclude_min_zero,
        )

        # --- Prepare Fund-group options for UI (only groups with securities after filtering) ---
        all_funds_in_data: set[str] = set()
        if config.FUNDS_COL in combined_metrics_df.columns:
            for x in combined_metrics_df[config.FUNDS_COL].dropna():
                all_funds_in_data.update(parse_fund_list(x))
        else:
            fund_col_candidates = [
                col
                for col in ["Fund", "Fund Code", config.CODE_COL]
                if col in combined_metrics_df.columns
            ]
            if fund_col_candidates:
                fund_col = fund_col_candidates[0]
                all_funds_in_data = set(combined_metrics_df[fund_col].unique())

        filtered_fund_groups = {
            g: [f for f in funds if f in all_funds_in_data]
            for g, funds in fund_groups_dict.items()
        }
        filtered_fund_groups = {
            g: funds for g, funds in filtered_fund_groups.items() if funds
        }

        # --- Apply Sorting via helper ---
        current_app.logger.info("Applying sorting via helper...")
        # Use imported apply_security_sorting
        combined_metrics_df, sort_by, sort_order = apply_security_sorting(
            df=combined_metrics_df,
            sort_by=sort_by,
            sort_order=sort_order,
            id_col_name=id_col_name,
        )
        current_app.logger.info(f"Sorted by '{sort_by}', {sort_order}.")

        # --- Pagination via helper ---
        # Use imported paginate_security_data
        paginated_df, pagination_context = paginate_security_data(
            df=combined_metrics_df,
            page=page,
            per_page=config.SECURITIES_PER_PAGE,
        )

        current_app.logger.info(
            f"Pagination: Total items={pagination_context['total_items']}, Total pages={pagination_context['total_pages']}, Current page={pagination_context['page']}, Per page={pagination_context['per_page']}"
        )

        # --- Prepare Data for Template ---
        securities_data_list = paginated_df.round(3).to_dict(orient="records")
        # Replace NaN with None for JSON compatibility / template rendering
        for row in securities_data_list:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None

        # Define column order (ID first, then Static, then Metrics)
        # Ensure ISIN (id_col_name) is not in ordered_static_cols
        ordered_static_cols = sorted(
            [
                col
                for col in static_cols
                if col in paginated_df.columns and col != id_col_name
            ]
        )
        metric_cols_ordered = [
            "Latest Value",
            "Change",
            "Change Z-Score",
            "Mean",
            "Max",
            "Min",
        ]
        # Ensure only existing columns are included and ID col is first
        final_col_order = (
            [id_col_name]
            + [col for col in ordered_static_cols if col in paginated_df.columns]
            + [col for col in metric_cols_ordered if col in paginated_df.columns]
        )

        # Ensure all original columns are considered if they aren't static or metric
        # Make sure not to add id_col_name again
        other_cols = [col for col in paginated_df.columns if col not in final_col_order]
        final_col_order.extend(other_cols)  # Add any remaining columns

        current_app.logger.info(f"Final column order for display: {final_col_order}")

        # Extend pagination context with URL factory
        pagination_context["url_for_page"] = lambda p: url_for(
            "security.securities_page",
            page=p,
            search_term=search_term,
            sort_by=sort_by,
            sort_order=sort_order,
            **{f"filter_{k}": v for k, v in active_filters.items()},
        )

        # --- Handle Empty DataFrame After Filtering ---
        if combined_metrics_df.empty:
            current_app.logger.warning(
                "No data matches the specified filters after applying helper."
            )
            message_parts = [
                "No securities found matching the current criteria.",
            ]
            if search_term:
                message_parts.append(f"Search term: '{search_term}'.")
            if active_filters:
                message_parts.append(f"Active filters: {active_filters}.")

            return render_template(
                "securities_page.html",
                message=" ".join(message_parts),
                securities_data=[],
                filter_options=final_filter_options,
                column_order=[],
                id_col_name=id_col_name,
                search_term=search_term,
                active_filters=active_filters,
                pagination=None,
                current_sort_by=sort_by,
                current_sort_order=sort_order,
                exclude_min_zero=exclude_min_zero,
                fund_groups=filtered_fund_groups,
                selected_fund_group=selected_fund_group,
            )

    except Exception as e:
        current_app.logger.error(
            f"!!! Unexpected error during security page processing: {e}", exc_info=True
        )
        traceback.print_exc()
        return render_template(
            "securities_page.html",
            message=f"An unexpected error occurred: {e}",
            securities_data=[],
            pagination=None,
            filter_options=(
                final_filter_options if "final_filter_options" in locals() else {}
            ),
            active_filters=active_filters,
            exclude_min_zero=exclude_min_zero,
            fund_groups=(
                filtered_fund_groups if "filtered_fund_groups" in locals() else {}
            ),
            selected_fund_group=(
                selected_fund_group if "selected_fund_group" in locals() else None
            ),
        )

    # --- Render Template ---
    return render_template(
        "securities_page.html",
        securities_data=securities_data_list,
        filter_options=final_filter_options,
        column_order=final_col_order,
        id_col_name=id_col_name,
        search_term=search_term,
        active_filters=active_filters,  # Pass active filters for form state
        pagination=pagination_context,  # Pass pagination object
        current_sort_by=sort_by,
        current_sort_order=sort_order,
        message=None,  # Clear any previous error message if successful
        exclude_min_zero=exclude_min_zero,  # Pass toggle state to template
        fund_groups=filtered_fund_groups,  # Pass available groups for UI
        selected_fund_group=selected_fund_group,  # Pass selected group for UI
    )


@security_bp.route("/security/details/<metric_name>/<path:security_id>")
def security_details(metric_name, security_id):
    """
    Renders a detail page for a specific security, showing historical charts
    for the specified metric overlaid with Price, plus separate charts for
    Duration, Spread Duration, and Spread (each potentially overlaid with SP data).
    Also loads all static info from reference.csv, checks exclusion and issue lists,
    and provides a Bloomberg YAS link.
    """
    # <<< ADDED: Decode the security_id to handle potential URL encoding (e.g., %2F for /)
    decoded_security_id = unquote(security_id)
    current_app.logger.info(
        f"--- Requesting Security Details: Metric='{metric_name}', Decoded ID='{decoded_security_id}' ---"
    )

    # Clean the decoded_security_id to get a base ISIN (remove trailing -<number> if present)
    # This cleaned ID is for reference.csv, exclusions, issues, and holdings data
    cleaned_isin_for_static_data = re.sub(r"-\d+$", "", decoded_security_id)
    current_app.logger.info(
        f"Cleaned ISIN for static data lookup: '{cleaned_isin_for_static_data}'"
    )

    # --- Identify Alternate (Hyphenated / Non-Hyphenated) Versions of This ISIN ---
    alternate_versions = []  # List of dicts: {id, name, url}
    try:
        base_isin_pattern = re.compile(rf"^{re.escape(cleaned_isin_for_static_data)}(?:-\d+)?$")
        alt_candidates = []
        # Prefer reference.csv if loaded; fallback to w_secs.csv if reference missing.
        if 'ref_df' in locals() and not ref_df.empty:
            alt_candidates = ref_df[config.ISIN_COL].dropna().astype(str).unique().tolist()
        else:
            w_secs_path = os.path.join(current_app.config["DATA_FOLDER"], "w_secs.csv")
            if os.path.exists(w_secs_path):
                try:
                    w_df = pd.read_csv(w_secs_path, usecols=[config.ISIN_COL])
                    alt_candidates = w_df[config.ISIN_COL].dropna().astype(str).unique().tolist()
                except Exception as e:
                    current_app.logger.warning(f"Could not load w_secs.csv for alternate ISIN lookup: {e}")

        for candidate in alt_candidates:
            if candidate == decoded_security_id:
                continue  # Skip current
            if base_isin_pattern.match(candidate):
                alt_name = None
                if 'ref_df' in locals() and not ref_df.empty and 'Security Name' in ref_df.columns:
                    name_row = ref_df[ref_df[config.ISIN_COL] == candidate]
                    if not name_row.empty and pd.notna(name_row.iloc[0].get('Security Name')):
                        alt_name = name_row.iloc[0]['Security Name']

                alt_url = url_for("security.security_details", metric_name=metric_name, security_id=candidate)
                alternate_versions.append({"id": candidate, "name": alt_name, "url": alt_url})

        if alternate_versions:
            current_app.logger.info(f"Found alternate ISIN versions for {decoded_security_id}: {[a['id'] for a in alternate_versions]}")
    except Exception as e:
        current_app.logger.warning(f"Error searching for alternate ISIN versions for {decoded_security_id}: {e}")

    data_folder = current_app.config["DATA_FOLDER"]
    all_dates = set()
    chart_data = {}  # Dictionary to hold data for JSON output
    static_info = {}  # To store static info for the security

    # --- NEW: Load static info from reference.csv ---
    reference_path = os.path.join(data_folder, "reference.csv")
    reference_row = None
    reference_columns = []
    if os.path.exists(reference_path):
        try:
            ref_df = pd.read_csv(reference_path, dtype=str)
            reference_columns = ref_df.columns.tolist()
            # Use cleaned_isin_for_static_data for lookup
            ref_row = ref_df[ref_df[config.ISIN_COL] == cleaned_isin_for_static_data]
            if not ref_row.empty:
                reference_row = ref_row.iloc[0].to_dict()
            else:
                reference_row = None
        except Exception as e:
            current_app.logger.error(f"Error loading reference.csv: {e}", exc_info=True)
            ref_df = pd.DataFrame()
    else:
        current_app.logger.warning("reference.csv not found in Data folder.")

    # --- NEW: Check exclusion list ---
    is_excluded = False
    exclusion_info = None
    try:
        exclusions_df = load_exclusions(os.path.join(data_folder, "exclusions.csv"))
        if exclusions_df is not None and not exclusions_df.empty:
            security_exclusions = exclusions_df[
                exclusions_df["SecurityID"] == cleaned_isin_for_static_data # Use cleaned ID
            ]
            if not security_exclusions.empty:
                active_exclusions = security_exclusions[
                    (security_exclusions["EndDate"].isna())
                    | (
                        pd.to_datetime(security_exclusions["EndDate"])
                        >= pd.Timestamp.now()
                    )
                ]
                if not active_exclusions.empty:
                    is_excluded = True
                    # Get the most recent exclusion
                    exclusion_info = (
                        active_exclusions.sort_values("AddDate", ascending=False)
                        .iloc[0]
                        .to_dict()
                    )
    except Exception as e:
        current_app.logger.error(f"Error checking exclusions: {e}", exc_info=True)

    # --- NEW: Check for open data issues ---
    open_issues = []
    try:
        from issue_processing import load_issues

        issues_df = load_issues(data_folder)
        if not issues_df.empty:
            # Filter to issues for this security
            # Ensure 'SecurityID' column exists before trying to filter
            if "SecurityID" in issues_df.columns:
                security_issues = issues_df[
                    (issues_df["SecurityID"] == cleaned_isin_for_static_data) # Use cleaned ID
                    & (issues_df["Status"] == "Open")
                ]
                if not security_issues.empty:
                    open_issues = security_issues.to_dict("records")
            else:
                current_app.logger.warning("Column 'SecurityID' not found in issues_df. Cannot filter issues.")

    except Exception as e:
        current_app.logger.error(f"Error checking data issues: {e}", exc_info=True)

    # --- NEW: Prepare Bloomberg YAS link ---
    bloomberg_yas_url = None
    if reference_row and "BBG Ticker Yellow" in reference_row:
        bbg_ticker = reference_row["BBG Ticker Yellow"]
        bloomberg_yas_url = config.BLOOMBERG_YAS_URL_FORMAT.format(ticker=bbg_ticker)

    # --- Load Data for Each Chart Section ---

    # 1. Primary Metric (passed in URL) + Price
    # Correctly construct metric_filename
    if metric_name.startswith("sec_"):
        metric_filename = f"{metric_name}.csv"
    else:
        metric_filename = f"sec_{metric_name}.csv"
    
    price_filename = "sec_Price.csv"
    # Use the decoded ID for filtering, call imported helper
    metric_series, metric_dates, metric_static = load_filter_and_extract(
        data_folder, metric_filename, decoded_security_id
    )
    price_series, price_dates, price_static = load_filter_and_extract(
        data_folder, price_filename, decoded_security_id
    )
    all_dates.update(metric_dates)
    all_dates.update(price_dates)
    static_info.update(metric_static)  # Prioritize static info from metric file
    static_info.update(price_static)  # Add/overwrite with price file info

    # 2. Duration + SP Duration
    duration_filename = "sec_Duration.csv"
    sp_duration_filename = "sec_DurationSP.csv"  # Optional SP file
    duration_series, duration_dates, duration_static = load_filter_and_extract(
        data_folder, duration_filename, decoded_security_id
    )
    sp_duration_series, sp_duration_dates, sp_duration_static = load_filter_and_extract(
        data_folder, sp_duration_filename, decoded_security_id
    )
    all_dates.update(duration_dates)
    all_dates.update(sp_duration_dates)
    static_info.update(duration_static)
    static_info.update(sp_duration_static)

    # 3. Spread Duration + SP Spread Duration
    spread_dur_filename = "sec_Spread duration.csv"
    sp_spread_dur_filename = "sec_Spread durationSP.csv"  # Optional SP file
    spread_dur_series, spread_dur_dates, spread_dur_static = load_filter_and_extract(
        data_folder, spread_dur_filename, decoded_security_id
    )
    sp_spread_dur_series, sp_spread_dur_dates, sp_spread_dur_static = (
        load_filter_and_extract(
            data_folder, sp_spread_dur_filename, decoded_security_id
        )
    )
    all_dates.update(spread_dur_dates)
    all_dates.update(sp_spread_dur_dates)
    static_info.update(spread_dur_static)
    static_info.update(sp_spread_dur_static)

    # 4. Spread + SP Spread
    spread_filename = "sec_Spread.csv"  # May reload if metric_name wasn't Spread
    sp_spread_filename = "sec_SpreadSP.csv"  # Optional SP file
    # Only load spread again if the primary metric wasn't spread
    if metric_name.lower() != "spread":
        spread_series, spread_dates, spread_static = load_filter_and_extract(
            data_folder, spread_filename, decoded_security_id
        )
        all_dates.update(spread_dates)
        static_info.update(spread_static)
    else:
        spread_series = metric_series  # Reuse already loaded data
        spread_dates = metric_dates
        # Static info already handled

    sp_spread_series, sp_spread_dates, sp_spread_static = load_filter_and_extract(
        data_folder, sp_spread_filename, decoded_security_id
    )
    all_dates.update(sp_spread_dates)
    static_info.update(sp_spread_static)

    # 5. YTM + SP YTM
    ytm_filename = "sec_YTM.csv"
    sp_ytm_filename = "sec_YTMSP.csv"
    ytm_series, ytm_dates, _ = load_filter_and_extract(
        data_folder, ytm_filename, decoded_security_id
    )
    sp_ytm_series, sp_ytm_dates, _ = load_filter_and_extract(
        data_folder, sp_ytm_filename, decoded_security_id
    )
    all_dates.update(ytm_dates)
    all_dates.update(sp_ytm_dates)

    # 6. YTW + SP YTW
    ytw_filename = "sec_YTW.csv"
    sp_ytw_filename = "sec_YTWSP.csv"
    ytw_series, ytw_dates, _ = load_filter_and_extract(
        data_folder, ytw_filename, decoded_security_id
    )
    sp_ytw_series, sp_ytw_dates, _ = load_filter_and_extract(
        data_folder, sp_ytw_filename, decoded_security_id
    )
    all_dates.update(ytw_dates)
    all_dates.update(sp_ytw_dates)

    # --- Prepare Data for Chart.js ---
    if not all_dates:
        current_app.logger.warning(
            "No dates found across any datasets. Cannot generate chart labels."
        )
        # Render template with error message or indication of no data
        return render_template(
            "security_details_page.html",
            security_id=decoded_security_id,
            metric_name=metric_name,
            chart_data_json="{}",  # Empty JSON
            latest_date="N/A",
            static_info=static_info,  # Show static info if any was found
            message="No historical data found for this security.",
            holdings_data=None,
            chart_dates=None,
            # Add missing variables for error case
            static_groups=[],
            reference_missing=True,
            is_excluded=is_excluded,
            exclusion_comment=exclusion_info,
            open_issues=open_issues,
            bloomberg_yas_url=bloomberg_yas_url,
        )

    # Sort dates and format as strings for labels
    sorted_dates = sorted(list(all_dates))
    # Use .strftime for consistent formatting
    chart_data["labels"] = [d.strftime("%Y-%m-%d") for d in sorted_dates]
    latest_date_str = chart_data["labels"][-1] if chart_data["labels"] else "N/A"

    # --- Fund Holdings Over Time (Based on Chart Dates) ---
    holdings_data = None
    chart_dates = chart_data["labels"] if "labels" in chart_data else None
    if chart_dates:
        holdings_data, _, holdings_error = get_holdings_for_security(
            cleaned_isin_for_static_data, chart_dates, data_folder # Use cleaned ID
        )
        if holdings_error:
            current_app.logger.warning(
                f"Holdings Error for {decoded_security_id}: {holdings_error}"
            )

    # Helper to prepare dataset structure for Chart.js
    def prepare_dataset(df_series, label, color, y_axis_id="y"):
        if df_series is None or df_series.empty:
            current_app.logger.warning(
                f"Cannot prepare dataset for '{label}': DataFrame is None or empty."
            )
            # Return structure with null data matching the length of labels
            return {
                "label": label,
                "data": [None]
                * len(chart_data["labels"]),  # Use None for missing points
                "borderColor": color,
                "backgroundColor": color + "80",  # Optional: add transparency
                "fill": False,
                "tension": 0.1,
                "pointRadius": 2,
                "pointHoverRadius": 5,
                "yAxisID": y_axis_id,
                "spanGaps": True,  # Let Chart.js connect lines over nulls
            }

        # Ensure value column is numeric, coercing errors
        df_series = pd.to_numeric(df_series, errors="coerce")

        # Merge with the full date range, using pd.NA for missing numeric values
        merged_df = pd.merge(
            pd.DataFrame({"Date": sorted_dates}),
            df_series.reset_index(),
            on="Date",
            how="left",
        )

        # <<< ADDED: Identify the value column name after the merge
        # It will be the column that is NOT 'Date'
        value_col_name_in_merged = [col for col in merged_df.columns if col != "Date"][
            0
        ]

        # Replace pandas NA/NaN with None for JSON compatibility
        # data_values = merged_df[value_col_name].replace({pd.NA: None, np.nan: None}).tolist()
        # Replace only NaN with None, keep numeric types where possible
        # Ensure the column is float first to handle potential integers mixed with NaN
        # <<< CHANGED: Use the identified column name
        data_values = (
            merged_df[value_col_name_in_merged]
            .astype(float)
            .replace({np.nan: None})
            .tolist()
        )

        return {
            "label": label,
            "data": data_values,
            "borderColor": color,
            "backgroundColor": color + "80",
            "fill": False,
            "tension": 0.1,
            "pointRadius": 2,
            "pointHoverRadius": 5,
            "yAxisID": y_axis_id,
            "spanGaps": True,
        }

    # Primary Chart Datasets (Metric + Price)
    chart_data["primary_datasets"] = []  # <<< Initialize the list here
    # current_app.logger.info(
    #     f"DEBUG: COLOR_PALETTE contents just before use: {COLOR_PALETTE}"
    # ) # <<< REMOVED DEBUG PRINT
    if metric_series is not None:
        chart_data["primary_datasets"].append(
            prepare_dataset(metric_series, metric_name, COLOR_PALETTE[0], "y")
        )
    else:  # Add placeholder if metric data failed to load
        chart_data["primary_datasets"].append(
            prepare_dataset(None, metric_name, COLOR_PALETTE[0], "y")
        )

    if price_series is not None:
        chart_data["primary_datasets"].append(
            prepare_dataset(
                price_series, "Price", COLOR_PALETTE[1], "y1"
            )  # Use secondary axis
        )
    else:  # Add placeholder if price data failed to load
        chart_data["primary_datasets"].append(
            prepare_dataset(None, "Price", COLOR_PALETTE[1], "y1")
        )

    # Duration Chart Datasets
    chart_data["duration_dataset"] = prepare_dataset(
        duration_series, "Duration", COLOR_PALETTE[2]
    )
    chart_data["sp_duration_dataset"] = prepare_dataset(
        sp_duration_series, "SP Duration", COLOR_PALETTE[3]
    )

    # Spread Duration Chart Datasets
    chart_data["spread_duration_dataset"] = prepare_dataset(
        spread_dur_series, "Spread Duration", COLOR_PALETTE[4]
    )
    chart_data["sp_spread_duration_dataset"] = prepare_dataset(
        sp_spread_dur_series, "SP Spread Duration", COLOR_PALETTE[5]
    )

    # Spread Chart Datasets
    chart_data["spread_dataset"] = prepare_dataset(
        spread_series, "Spread", COLOR_PALETTE[6]
    )
    chart_data["sp_spread_dataset"] = prepare_dataset(
        sp_spread_series, "SP Spread", COLOR_PALETTE[7]
    )

    # YTM Chart Datasets
    chart_data["ytm_dataset"] = prepare_dataset(ytm_series, "YTM", COLOR_PALETTE[8])
    chart_data["sp_ytm_dataset"] = prepare_dataset(
        sp_ytm_series, "SP YTM", COLOR_PALETTE[9]
    )

    # YTW Chart Datasets
    chart_data["ytw_dataset"] = prepare_dataset(ytw_series, "YTW", COLOR_PALETTE[10])
    chart_data["sp_ytw_dataset"] = prepare_dataset(
        sp_ytw_series, "SP YTW", COLOR_PALETTE[11]
    )

    # Convert the entire chart_data dictionary to JSON safely
    chart_data_json = json.dumps(
        chart_data, default=replace_nan_with_none, indent=4
    )  # Use helper for NaN->null

    # --- NEW: Group static info for display ---
    static_groups = []
    if reference_row:
        used_keys = set()
        for group_name, col_list in STATIC_INFO_GROUPS:
            group_dict = {k: reference_row[k] for k in col_list if k in reference_row}
            used_keys.update(group_dict.keys())
            static_groups.append((group_name, group_dict))
        # Add 'Other Details' for any remaining keys
        others = {k: reference_row[k] for k in reference_row if k not in used_keys}
        static_groups.append(("Other Details", others))
    else:
        static_groups = []

    current_app.logger.info(
        f"Rendering security details page for {decoded_security_id}"
    )
    # Pass the decoded ID to the template
    return render_template(
        "security_details_page.html",
        security_id=decoded_security_id,
        metric_name=metric_name,
        chart_data_json=chart_data_json,
        latest_date=latest_date_str,
        static_groups=static_groups,
        reference_missing=(reference_row is None),
        is_excluded=is_excluded,
        exclusion_comment=exclusion_info,
        open_issues=open_issues,
        bloomberg_yas_url=bloomberg_yas_url,
        holdings_data=holdings_data,
        chart_dates=chart_dates,
        alternate_versions=alternate_versions,
    )


@security_bp.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(
        os.path.join(security_bp.root_path, "..", "static"), filename
    )
