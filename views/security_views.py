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
    send_file,
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
import io  # For CSV export
import csv  # For CSV writing
import yaml  # For field alias mapping

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
from utils import load_fund_groups, parse_fund_list, load_weights_and_held_status # Added load_weights_and_held_status

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
@security_bp.route("/summary/<metric_name>")
def securities_page(metric_name: str = "Spread"):
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
    # Dynamically build the filename for the requested metric (e.g. Duration →
    # 'sec_Duration.csv').  Capitalise the first letter to match the existing
    # naming convention.
    metric_proper = metric_name[:1].upper() + metric_name[1:]
    metric_filename = f"sec_{metric_proper}.csv"
    filter_options = {}  # To store all possible options for filter dropdowns

    if not os.path.exists(os.path.join(data_folder, metric_filename)):
        current_app.logger.error(
            f"Error: The required file '{metric_filename}' not found."
        )
        return render_template(
            "securities_page.html",
            message=f"<strong>Missing Data File!</strong> The required data file '<code>{metric_filename}</code>' is not found in the Data directory. Please ensure the file exists before accessing this page.",
            securities_data=[],
            pagination=None,
            metric_name=metric_name,
        )

    try:
        current_app.logger.info(f"Loading and processing file: {metric_filename}")
        # Pass the absolute data folder path
        df_long, static_cols = load_and_process_security_data(
            metric_filename, data_folder
        )

        if df_long is None or df_long.empty:
            current_app.logger.warning(
                f"Skipping {metric_filename} due to load/process errors or empty data."
            )
            return render_template(
                "securities_page.html",
                message=f"Error loading or processing '{metric_filename}'.",
                securities_data=[],
                pagination=None,
                metric_name=metric_name,
            )

        current_app.logger.info("Calculating latest metrics...")
        combined_metrics_df = calculate_security_latest_metrics(df_long, static_cols)

        if combined_metrics_df.empty:
            current_app.logger.warning(f"No metrics calculated for {metric_filename}.")
            return render_template(
                "securities_page.html",
                message=f"Could not calculate metrics from '{metric_filename}'.",
                securities_data=[],
                pagination=None,
                metric_name=metric_name,
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
                    f"Error: Cannot find a usable ID column ('{id_col_name}' or fallback '{old_id_col}') in {metric_filename}."
                )
                return render_template(
                    "securities_page.html",
                    message=f"Error: Cannot identify securities in {metric_filename}.",
                    securities_data=[],
                    pagination=None,
                    metric_name=metric_name,
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

        # --- Load Fund Groups for the dropdown ---
        # This should be done early to populate the dropdown regardless of filtering
        all_fund_groups_dict = load_fund_groups(data_folder)
        current_app.logger.info(f"Loaded all fund groups: {all_fund_groups_dict.keys()}")

        # --- Apply Fund Group Filter (if selected) based on w_secs.csv ---
        if selected_fund_group and selected_fund_group in all_fund_groups_dict:
            current_app.logger.info(f"Applying fund group filter for: {selected_fund_group}")
            funds_in_selected_group = set(all_fund_groups_dict[selected_fund_group])
            
            # Load w_secs.csv to get holdings data
            # Using a simplified way to get relevant ISINs for the group.
            # For a more robust solution, consider date alignment and summing weights.
            w_secs_path = os.path.join(data_folder, config.W_SECS_FILENAME)
            if os.path.exists(w_secs_path):
                try:
                    df_w_secs = pd.read_csv(w_secs_path, low_memory=False)
                    # Ensure 'Fund Code' or similar exists. Assuming config.CODE_COL refers to fund code in w_secs
                    fund_col_in_w_secs = config.CODE_COL 
                    if fund_col_in_w_secs not in df_w_secs.columns:
                        # Try a common alternative if config.CODE_COL is not 'Fund Code'
                        if 'Fund Code' in df_w_secs.columns:
                            fund_col_in_w_secs = 'Fund Code'
                        else: # Add more fallbacks if necessary
                            current_app.logger.warning(f"'{config.CODE_COL}' or 'Fund Code' not found in {config.W_SECS_FILENAME}. Cannot filter by fund group holdings.")
                            df_w_secs = pd.DataFrame() # Empty df if no fund column

                    if not df_w_secs.empty:
                        # Filter w_secs for funds in the selected group
                        df_w_secs_group = df_w_secs[df_w_secs[fund_col_in_w_secs].isin(funds_in_selected_group)]
                        
                        # Get unique ISINs held by these funds
                        # Assuming config.ISIN_COL is the ISIN column in w_secs
                        if config.ISIN_COL in df_w_secs_group.columns:
                            securities_in_group_held = set(df_w_secs_group[config.ISIN_COL].unique())
                            current_app.logger.info(f"Found {len(securities_in_group_held)} unique securities for group '{selected_fund_group}'.")
                            
                            # Filter the main combined_metrics_df
                            combined_metrics_df = combined_metrics_df[combined_metrics_df[id_col_name].isin(securities_in_group_held)]
                            current_app.logger.info(f"Shape of combined_metrics_df after fund group pre-filter: {combined_metrics_df.shape}")
                        else:
                            current_app.logger.warning(f"'{config.ISIN_COL}' not found in {config.W_SECS_FILENAME}. Cannot filter by fund group holdings.")
                except Exception as e:
                    current_app.logger.error(f"Error processing {config.W_SECS_FILENAME} for fund group filter: {e}")
            else:
                current_app.logger.warning(f"{config.W_SECS_FILENAME} not found. Cannot filter by fund group.")
        
        # --- Active exclusions ---
        active_exclusion_ids = get_active_exclusions(data_folder)

        # --- Apply other filters (search, static, min=0) via helper ---
        # Note: The fund group filtering is now done above.
        # The apply_security_filters helper might still have its own fund group logic;
        # for this view, it might be redundant or could be disabled if it conflicts.
        # For now, we pass None as selected_fund_group to the helper if already filtered.
        
        combined_metrics_df_after_main_filters = apply_security_filters(
            df=combined_metrics_df.copy(), # Pass a copy
            id_col_name=id_col_name,
            search_term=search_term,
            fund_groups_dict=all_fund_groups_dict, # Pass all groups for other potential uses
            selected_fund_group=None, # Crucial: Indicate that primary group filtering is done
            active_exclusion_ids=active_exclusion_ids,
            active_filters=active_filters,
            exclude_min_zero=exclude_min_zero,
        )
        current_app.logger.info(f"Shape of combined_metrics_df after all filters helper: {combined_metrics_df_after_main_filters.shape}")


        # --- Prepare Fund-group options for UI (based on ALL_FUND_GROUPS_DICT initially) ---
        # This ensures all groups are always shown in dropdown, and selection is maintained
        # The actual filtering of securities is handled by the logic above and apply_security_filters
        ui_fund_groups = all_fund_groups_dict


        # --- Sorting ---
        # Use imported apply_security_sorting
        # ... (sorting logic using combined_metrics_df_after_main_filters)
        sorted_df, current_sort_by, current_sort_order = apply_security_sorting(
            combined_metrics_df_after_main_filters, sort_by, sort_order, id_col_name
        )


        # --- Pagination ---
        # Use imported paginate_security_data
        # ... (pagination logic using sorted_df)
        paginated_data, pagination_context = paginate_security_data(
            sorted_df, page, config.SECURITIES_PER_PAGE
        )

        # Helper to retain the *metric_name* in page links *unless* we're on
        # the default (Spread) route to keep URLs clean.
        def _url_for_page(p: int) -> str:
            base_args = {
                "page": p,
                "search_term": search_term,
                "sort_by": current_sort_by,
                "sort_order": current_sort_order,
                "fund_group": selected_fund_group,
                "exclude_min_zero": "true" if exclude_min_zero else "false",
                **{f"filter_{k}": v for k, v in active_filters.items()},
            }
            if metric_name and metric_name.lower() != "spread":
                return url_for("security.securities_page", metric_name=metric_name, **base_args)
            return url_for("security.securities_page", **base_args)

        pagination_context["url_for_page"] = _url_for_page
        
        # --- Final Data Preparation ---
        # ... (column order, final data conversion)
        # ... (Make sure 'final_data_list' is derived from 'paginated_data')

        # Ensure column_order is defined, e.g. from config or dynamically
        column_order = config.SECURITIES_SUMMARY_COLUMNS_ORDER
        
        # Ensure all columns in column_order exist, add missing ones with empty strings
        for col in column_order:
            if col not in paginated_data.columns:
                paginated_data[col] = '' # or np.nan if you prefer

        final_data_list = paginated_data[column_order].to_dict(orient="records")
        final_data_list = replace_nan_with_none(final_data_list)


        current_app.logger.info(f"Rendering securities_page.html with {len(final_data_list)} securities.")
        return render_template(
            "securities_page.html",
            securities_data=final_data_list,
            pagination=pagination_context,
            filter_options=final_filter_options, # Use the options collected before any filtering
            active_filters=active_filters,
            search_term=search_term,
            id_col_name=id_col_name,
            current_sort_by=current_sort_by,
            current_sort_order=current_sort_order,
            column_order=column_order,
            exclude_min_zero=exclude_min_zero,
            fund_groups=ui_fund_groups, # Pass the fund groups for the dropdown
            selected_fund_group=selected_fund_group, # Pass the selected group to maintain dropdown state
            metric_name=metric_name,
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
                ui_fund_groups if "ui_fund_groups" in locals() else {}
            ),
            selected_fund_group=(
                selected_fund_group if "selected_fund_group" in locals() else None
            ),
            metric_name=metric_name,
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

@security_bp.route('/mark_good', methods=['POST'])
def mark_good():
    """API endpoint to mark a specific (ISIN, Metric, Date) tuple as cleared/"good".
    Stores the override in Data/good_points.csv so that subsequent loads ignore that value.
    Expects JSON: { "isin": "XS...", "metric": "Spread", "date": "YYYY-MM-DD" }
    Returns HTTP 204 on success.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        isin = data.get('isin')
        metric = data.get('metric')
        date_str = data.get('date')
        if not all([isin, metric, date_str]):
            return ("Missing fields", 400)
        # Validate date
        try:
            date_val = pd.to_datetime(date_str).date()
        except Exception:
            return ("Invalid date", 400)
        data_folder = current_app.config.get('DATA_FOLDER')
        if not data_folder:
            return ("Server not configured", 500)
        good_path = os.path.join(data_folder, 'good_points.csv')
        # Load or create
        cols = ['ISIN', 'Metric', 'Date']
        if os.path.exists(good_path):
            good_df = pd.read_csv(good_path)
        else:
            good_df = pd.DataFrame(columns=cols)
        # Prevent duplicates
        dup_mask = (
            (good_df['ISIN'] == isin) &
            (good_df['Metric'].str.lower() == metric.lower()) &
            (good_df['Date'] == date_val.isoformat())
        ) if not good_df.empty else pd.Series(False)
        if not dup_mask.any():
            good_df.loc[len(good_df)] = [isin, metric, date_val.isoformat()]
            good_df.to_csv(good_path, index=False)
        current_app.logger.info(f"Marked good point: {isin} {metric} {date_val}")
        return ('', 204)
    except Exception as e:
        current_app.logger.error(f"/mark_good error: {e}", exc_info=True)
        return ("Server Error", 500)

# --------------------- Field Data Override Routes ---------------------
@security_bp.route('/get_field_data')
def get_field_data():
    """Return existing values for a given ISIN, field, and date range as JSON for the Edit-Data modal."""
    isin = request.args.get('isin')
    field = request.args.get('field')
    start = request.args.get('start')
    end = request.args.get('end')
    if not (isin and field and start and end):
        return jsonify({'error': 'Missing parameters'}), 400
    try:
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
    except Exception:
        return jsonify({'error': 'Invalid date format'}), 400

    # Map UI field → underlying file field (via YAML)
    alias_path = os.path.join(current_app.root_path, 'config', 'field_aliases.yaml')
    field_map = {}
    if os.path.exists(alias_path):
        try:
            with open(alias_path, 'r', encoding='utf-8') as f:
                field_map = yaml.safe_load(f) or {}
        except Exception:
            pass  # Ignore and fall back to identity
    db_field = field_map.get(field, field)  # Identity fallback

    # Determine filename (supports SP version)
    sp_suffix = 'SP' if db_field.lower().endswith('sp') else ''
    base_field_name = db_field[:-2] if sp_suffix else db_field
    metric_filename = f"sec_{db_field}.csv"  # e.g. sec_Spread.csv or sec_SpreadSP.csv

    data_folder = current_app.config['DATA_FOLDER']
    file_path = os.path.join(data_folder, metric_filename)
    if not os.path.exists(file_path):
        return jsonify([])  # Return empty if no file found

    # Re-use existing loader for consistency
    df_long, _ = load_and_process_security_data(metric_filename, data_folder)
    if df_long.empty:
        return jsonify([])

    # Convert index to columns for simpler filtering (avoids unsorted index slice errors)
    df_reset = df_long.reset_index()

    # Determine ID column present
    id_col = config.ISIN_COL if config.ISIN_COL in df_reset.columns else df_reset.columns[1]

    # Apply filters
    mask = (
        (df_reset[id_col] == isin) &
        (df_reset['Date'] >= start_dt) &
        (df_reset['Date'] <= end_dt)
    )
    df_filtered = df_reset.loc[mask, ['Date', 'Value']].sort_values('Date')

    if df_filtered.empty:
        return jsonify([])

    result = df_filtered.to_dict(orient='records')
    # Convert Timestamp to str
    for row in result:
        if isinstance(row['Date'], (pd.Timestamp, datetime)):
            row['Date'] = row['Date'].strftime('%Y-%m-%d')
    return jsonify(result)


@security_bp.route('/export_field_data', methods=['POST'])
def export_field_data():
    """Receive modified data and return CSV for user download."""
    data = request.get_json(force=True)
    required_keys = {'isin', 'field', 'data'}
    if not data or not required_keys.issubset(data.keys()):
        return jsonify({'error': 'Invalid payload'}), 400

    isin = data['isin']
    field = data['field']
    rows = data['data']  # list of dicts with Date and Value

    # Prepare CSV content: Field, ISIN, Date, Value
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Field', 'ISIN', 'Date', 'Value'])
    for row in rows:
        date_str = row.get('Date')
        val = row.get('Value')
        writer.writerow([field, isin, date_str, val])

    csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
    filename = f"override_{field}_{isin}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    csv_bytes.seek(0)
    return send_file(
        csv_bytes,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )
