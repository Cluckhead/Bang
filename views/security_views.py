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

# Import necessary functions/constants from other modules
from config import COLOR_PALETTE  # Keep palette
from security_processing import (
    load_and_process_security_data,
    calculate_security_latest_metrics,
)

# Import the exclusion loading function
from views.exclusion_views import load_exclusions  # Only import load_exclusions
from utils import replace_nan_with_none

# Add import for fund group utility
from utils import load_fund_groups, parse_fund_list

# Import get_holdings_for_security for fund holdings tile
from views.comparison_helpers import get_holdings_for_security

# Define the blueprint
security_bp = Blueprint("security", __name__, url_prefix="/security")

PER_PAGE = 50  # Define how many items per page


def get_active_exclusions(data_folder_path: str):
    """Loads exclusions and returns a set of SecurityIDs that are currently active."""
    # Pass the data folder path to the load_exclusions function
    exclusions = load_exclusions(data_folder_path)
    active_exclusions = set()
    today = datetime.now().date()

    for ex in exclusions:
        try:
            add_date = ex["AddDate"].date() if pd.notna(ex["AddDate"]) else None
            end_date = ex["EndDate"].date() if pd.notna(ex["EndDate"]) else None
            security_id = str(ex["SecurityID"])  # Ensure it's string for comparison

            if add_date and add_date <= today:
                if end_date is None or end_date >= today:
                    active_exclusions.add(security_id)
        except Exception as e:
            current_app.logger.error(f"Error processing exclusion record {ex}: {e}")

    current_app.logger.info(
        f"Found {len(active_exclusions)} active exclusions: {active_exclusions}"
    )
    return active_exclusions


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
        id_col_name = "ISIN"  # <<< Use ISIN as the identifier

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

        # --- Fund Group Filtering: Apply to DataFrame Before Filters ---
        fund_groups_dict = load_fund_groups(data_folder)
        if selected_fund_group and selected_fund_group in fund_groups_dict:
            allowed_funds = set(fund_groups_dict[selected_fund_group])
            # If 'Funds' column exists, filter by checking if any allowed fund is in the parsed list
            if "Funds" in combined_metrics_df.columns:
                combined_metrics_df = combined_metrics_df[
                    combined_metrics_df["Funds"].apply(
                        lambda x: (
                            any(f in allowed_funds for f in parse_fund_list(x))
                            if pd.notna(x)
                            else False
                        )
                    )
                ]
            else:
                # Fallback: Try to filter by a static column that matches fund code, e.g., 'Fund', 'Fund Code', or similar
                fund_col_candidates = [
                    col
                    for col in ["Fund", "Fund Code", "Code"]
                    if col in combined_metrics_df.columns
                ]
                if fund_col_candidates:
                    fund_col = fund_col_candidates[0]
                    combined_metrics_df = combined_metrics_df[
                        combined_metrics_df[fund_col].isin(allowed_funds)
                    ]
            # If no fund column, skip filtering (could log a warning)
        # --- Prepare Fund Group Filtering for UI (only groups with securities in current data) ---
        all_funds_in_data = set()
        if "Funds" in combined_metrics_df.columns:
            all_funds_in_data = set()
            for x in combined_metrics_df["Funds"].dropna():
                all_funds_in_data.update(parse_fund_list(x))
        else:
            fund_col_candidates = [
                col
                for col in ["Fund", "Fund Code", "Code"]
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

        # --- Apply Filtering Steps Sequentially ---
        current_app.logger.info("Applying filters...")
        # 1. Search Term Filter (on ID column - now ISIN)
        if search_term:
            combined_metrics_df = combined_metrics_df[
                combined_metrics_df[id_col_name]
                .astype(str)
                .str.contains(search_term, case=False, na=False)
            ]
            current_app.logger.info(
                f"Applied search term '{search_term}'. Rows remaining: {len(combined_metrics_df)}"
            )

        # 2. Active Exclusions Filter (should still work if exclusions use SecurityID/Name, adapt if needed)
        try:
            # Pass the absolute data folder path to get active exclusions
            active_exclusion_ids = get_active_exclusions(data_folder)
            # Assuming exclusions use Security Name/ID for now. If they use ISIN, this is correct.
            # If they use Security Name, we need to filter on that column instead.
            exclusion_col_to_check = id_col_name  # Assumes exclusions use ISIN
            # If exclusions.csv uses Security Name, use this instead:
            # exclusion_col_to_check = 'Security Name' if 'Security Name' in combined_metrics_df.columns else id_col_name

            if active_exclusion_ids:
                combined_metrics_df = combined_metrics_df[
                    ~combined_metrics_df[exclusion_col_to_check]
                    .astype(str)
                    .isin(active_exclusion_ids)
                ]
                current_app.logger.info(
                    f"Applied {len(active_exclusion_ids)} exclusions based on '{exclusion_col_to_check}'. Rows remaining: {len(combined_metrics_df)}"
                )
        except Exception as e:
            current_app.logger.warning(
                f"Warning: Error loading or applying exclusions: {e}"
            )

        # 3. Dynamic Filters (from request args)
        if active_filters:
            for col, value in active_filters.items():
                if col in combined_metrics_df.columns:
                    combined_metrics_df = combined_metrics_df[
                        combined_metrics_df[col].astype(str) == str(value)
                    ]
                    current_app.logger.info(
                        f"Applied filter '{col}={value}'. Rows remaining: {len(combined_metrics_df)}"
                    )
                else:
                    current_app.logger.warning(
                        f"Warning: Filter column '{col}' not found in DataFrame."
                    )

        # 4. Exclude Min = 0 if toggle is on
        if exclude_min_zero and "Min" in combined_metrics_df.columns:
            before_count = len(combined_metrics_df)
            combined_metrics_df = combined_metrics_df[
                ~(combined_metrics_df["Min"].fillna(0) == 0)
            ]
            after_count = len(combined_metrics_df)
            current_app.logger.info(
                f"Excluded securities where Min = 0. Rows before: {before_count}, after: {after_count}"
            )

        # --- Handle Empty DataFrame After Filtering ---
        if combined_metrics_df.empty:
            current_app.logger.warning("No data matches the specified filters.")
            message = "No securities found matching the current criteria."
            if search_term:
                message += f" Search term: '{search_term}'."
            if active_filters:
                message += f" Active filters: {active_filters}."
            return render_template(
                "securities_page.html",
                message=message,
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

        # --- Apply Sorting ---
        current_app.logger.info(f"Applying sort: By='{sort_by}', Order='{sort_order}'")

        # Default sort column if not provided or invalid
        effective_sort_by = sort_by
        is_default_sort = False
        if sort_by not in combined_metrics_df.columns:
            # Default to sorting by absolute Z-score if 'sort_by' is invalid or not provided
            if "Change Z-Score" in combined_metrics_df.columns:
                current_app.logger.info(
                    f"'{sort_by}' not valid or not provided. Defaulting sort to 'Abs Change Z-Score' {sort_order}"
                )
                # Calculate Abs Z-Score temporarily for sorting
                combined_metrics_df["_abs_z_score_"] = (
                    combined_metrics_df["Change Z-Score"].fillna(0).abs()
                )
                effective_sort_by = "_abs_z_score_"
                # Default Z-score sort is always descending unless explicitly requested otherwise for Z-score itself
                if sort_by != "Change Z-Score":
                    sort_order = "desc"
                is_default_sort = True
            else:
                current_app.logger.warning(
                    "Warning: Cannot apply default sort, 'Change Z-Score' missing."
                )
                effective_sort_by = id_col_name  # Fallback sort
                sort_order = "asc"

        ascending_order = sort_order == "asc"

        try:
            # Use na_position='last' to handle NaNs consistently
            combined_metrics_df.sort_values(
                by=effective_sort_by,
                ascending=ascending_order,
                inplace=True,
                na_position="last",
                key=lambda col: (
                    col.astype(str).str.lower() if col.dtype == "object" else col
                ),
            )
            current_app.logger.info(f"Sorted by '{effective_sort_by}', {sort_order}.")
        except Exception as e:
            current_app.logger.error(
                f"Error during sorting by {effective_sort_by}: {e}. Falling back to sorting by ID."
            )
            combined_metrics_df.sort_values(
                by=id_col_name, ascending=True, inplace=True, na_position="last"
            )
            sort_by = id_col_name  # Update sort_by to reflect fallback
            sort_order = "asc"

        # Remove temporary sort column if added
        if is_default_sort and "_abs_z_score_" in combined_metrics_df.columns:
            combined_metrics_df.drop(columns=["_abs_z_score_"], inplace=True)
            # Set sort_by for template correctly if default was used
            sort_by = "Change Z-Score"  # Reflect the conceptual sort column

        # --- Pagination ---
        total_items = len(combined_metrics_df)
        # Ensure PER_PAGE is positive to avoid division by zero or negative pages
        safe_per_page = max(1, PER_PAGE)
        total_pages = math.ceil(total_items / safe_per_page)
        total_pages = max(
            1, total_pages
        )  # Ensure at least 1 page, even if total_items is 0
        page = max(
            1, min(page, total_pages)
        )  # Ensure page is within valid range [1, total_pages]
        start_index = (page - 1) * safe_per_page
        end_index = start_index + safe_per_page

        current_app.logger.info(
            f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Per page={safe_per_page}"
        )

        # Calculate page numbers to display in pagination controls (e.g., show 2 pages before and after current)
        page_window = 2  # Number of pages to show before/after current page
        start_page_display = max(1, page - page_window)
        end_page_display = min(total_pages, page + page_window)

        paginated_df = combined_metrics_df.iloc[start_index:end_index]

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

        # Create pagination context for the template
        pagination_context = {
            "page": page,
            "per_page": safe_per_page,
            "total_pages": total_pages,
            "total_items": total_items,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_num": page - 1,
            "next_num": page + 1,
            "start_page_display": start_page_display,  # Pass calculated start page
            "end_page_display": end_page_display,  # Pass calculated end page
            # Function to generate URLs for pagination links, preserving state
            "url_for_page": lambda p: url_for(
                "security.securities_page",
                page=p,
                search_term=search_term,
                sort_by=sort_by,
                sort_order=sort_order,
                **{f"filter_{k}": v for k, v in active_filters.items()},
            ),
        }

    except Exception as e:
        current_app.logger.error(
            f"!!! Unexpected error during security page processing: {e}"
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
            fund_groups=filtered_fund_groups,
            selected_fund_group=selected_fund_group,
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
            ref_row = ref_df[ref_df["ISIN"] == decoded_security_id]
            if not ref_row.empty:
                reference_row = ref_row.iloc[0].to_dict()
            else:
                reference_row = None
        except Exception as e:
            current_app.logger.error(f"Error loading reference.csv: {e}")
            reference_row = None
    else:
        current_app.logger.warning("reference.csv not found in Data folder.")
        reference_row = None

    # --- NEW: Check exclusion list ---
    is_excluded = False
    exclusion_comment = None
    try:
        exclusions_path = os.path.join(data_folder, "exclusions.csv")
        if os.path.exists(exclusions_path):
            exclusions_df = pd.read_csv(exclusions_path, dtype=str)
            today = datetime.now().date()
            for _, row in exclusions_df.iterrows():
                if row["SecurityID"] == decoded_security_id:
                    add_date = (
                        pd.to_datetime(row["AddDate"], errors="coerce").date()
                        if pd.notna(row["AddDate"])
                        else None
                    )
                    end_date = (
                        pd.to_datetime(row["EndDate"], errors="coerce").date()
                        if pd.notna(row["EndDate"])
                        else None
                    )
                    if (
                        add_date
                        and add_date <= today
                        and (end_date is None or end_date >= today)
                    ):
                        is_excluded = True
                        exclusion_comment = row.get("Comment", None)
                        break
    except Exception as e:
        current_app.logger.error(f"Error checking exclusions: {e}")

    # --- NEW: Check issue list ---
    open_issues = []
    try:
        issues_path = os.path.join(data_folder, "data_issues.csv")
        if os.path.exists(issues_path):
            issues_df = pd.read_csv(issues_path, dtype=str)
            # Only consider issues where FundImpacted or Description mentions the ISIN
            for _, row in issues_df.iterrows():
                # Consider open if Status is not 'Closed' (case-insensitive)
                status = (row.get("Status") or "").strip().lower()
                if status != "closed":
                    # Check if ISIN is mentioned in FundImpacted or Description
                    fund_impacted = row.get("FundImpacted") or ""
                    description = row.get("Description") or ""
                    if (
                        decoded_security_id in fund_impacted
                        or decoded_security_id in description
                    ):
                        open_issues.append(row)
    except Exception as e:
        current_app.logger.error(f"Error checking data issues: {e}")

    # --- NEW: Prepare Bloomberg YAS link ---
    bloomberg_yas_url = None
    if reference_row and "BBG Ticker Yellow" in reference_row:
        bbg_ticker = reference_row["BBG Ticker Yellow"]
        bloomberg_yas_url = f"http://Bloomberg:{bbg_ticker} YAS"

    # --- Helper function to load, filter, and extract data ---
    def load_filter_and_extract(filename, security_id_to_filter, id_column_name="ISIN"):
        """Loads a sec_*.csv file, filters by security ID, and returns the long-format series."""
        current_app.logger.info(f"Loading file: {filename}")
        # Construct absolute path
        filepath = os.path.join(data_folder, filename)
        if not os.path.exists(filepath):
            current_app.logger.warning(f"Warning: File not found - {filename}")
            return (
                None,
                set(),
                {},
            )  # Return None for data, empty set for dates, empty dict for static

        try:
            # Load data, specifying the data folder
            df_long, static_cols = load_and_process_security_data(filename, data_folder)

            if df_long is None or df_long.empty:
                current_app.logger.warning(f"Warning: No data loaded from {filename}")
                return None, set(), {}

            # Ensure the ID column is available for filtering
            # security_processing should have already set the index to 'ISIN' or made it a column
            if (
                id_column_name not in df_long.index.names
                and id_column_name not in df_long.columns
            ):
                current_app.logger.error(
                    f"Error: ID column '{id_column_name}' not found in processed data from {filename}."
                )
                # Attempt to find the index name if it wasn't 'ISIN'
                fallback_id_col = df_long.index.name
                if fallback_id_col and fallback_id_col in df_long.index.names:
                    current_app.logger.info(
                        f"Attempting filter using index name: '{fallback_id_col}'"
                    )
                    id_column_name = fallback_id_col  # Use the actual index name
                else:
                    return None, set(), {}  # Cannot filter

            # Filter by the decoded security ID
            # Check if filtering on index or column
            if id_column_name in df_long.index.names:
                # If the ID is in the index (MultiIndex scenario: Date, ISIN)
                if isinstance(df_long.index, pd.MultiIndex):
                    # Need to select based on the level corresponding to the ID column
                    try:
                        level_index = df_long.index.names.index(id_column_name)
                        filtered_df = df_long[
                            df_long.index.get_level_values(level_index)
                            == security_id_to_filter
                        ]
                    except ValueError:
                        current_app.logger.error(
                            f"Error: Level '{id_column_name}' not found in MultiIndex."
                        )
                        return None, set(), {}
                    except (
                        KeyError
                    ):  # Handle case where the specific ID doesn't exist in the index level
                        current_app.logger.warning(
                            f"Warning: Security ID '{security_id_to_filter}' not found in index level '{id_column_name}' of {filename}."
                        )
                        filtered_df = pd.DataFrame()  # Empty DataFrame
                else:  # Single index (shouldn't happen if processed correctly, but handle defensively)
                    filtered_df = df_long.loc[[security_id_to_filter]]
            elif id_column_name in df_long.columns:
                # If the ID is a regular column
                filtered_df = df_long[df_long[id_column_name] == security_id_to_filter]
            else:
                # This case should have been caught earlier, but included for safety
                current_app.logger.error(
                    f"Error: Cannot filter - ID column '{id_column_name}' not found."
                )
                return None, set(), {}

            # Check if filtering yielded results
            if filtered_df.empty:
                current_app.logger.warning(
                    f"Warning: No data found for {id_column_name}='{security_id_to_filter}' in {filename}"
                )
                # Try alternative common ID column 'Security Name' if ISIN failed and it exists
                alt_id_col = "Security Name"
                if id_column_name == "ISIN" and alt_id_col in df_long.columns:
                    current_app.logger.info(
                        f"--> Retrying filter with '{alt_id_col}'..."
                    )
                    filtered_df = df_long[df_long[alt_id_col] == security_id_to_filter]
                    if filtered_df.empty:
                        current_app.logger.warning(
                            f"Warning: No data found for {alt_id_col}='{security_id_to_filter}' either."
                        )
                        return None, set(), {}
                    else:
                        current_app.logger.info(f"Found data using '{alt_id_col}'.")
                        id_column_name = (
                            alt_id_col  # Update the effective ID column used
                        )
                else:
                    # Still empty after initial filter, and no/failed retry
                    return None, set(), {}

            # Extract the relevant data series (Date index, Value column)
            # The value column is typically the first column after resetting index, or 'Value'
            value_col_name = "Value"  # Default assumption from melt
            if value_col_name not in filtered_df.columns:
                # Find the first non-ID, non-static column if 'Value' isn't present
                potential_value_cols = [
                    col
                    for col in filtered_df.columns
                    if col not in static_cols and col != id_column_name
                ]
                if potential_value_cols:
                    value_col_name = potential_value_cols[0]
                    current_app.logger.info(
                        f"Using '{value_col_name}' as value column."
                    )
                else:
                    current_app.logger.error(
                        f"Error: Could not determine the value column in {filename}."
                    )
                    return None, set(), {}

            # Ensure 'Date' is the index
            if "Date" in filtered_df.columns:
                filtered_df = filtered_df.set_index("Date")
            elif not isinstance(filtered_df.index, pd.DatetimeIndex):
                # If Date is part of a MultiIndex, extract it
                if "Date" in filtered_df.index.names:
                    # Reset the index, set 'Date' as the main index
                    filtered_df = filtered_df.reset_index().set_index("Date")
                else:
                    current_app.logger.error(
                        f"Error: Cannot find 'Date' index or column in {filename}."
                    )
                    return None, set(), {}

            # Extract the series and dates
            data_series = filtered_df[value_col_name].sort_index()
            dates = set(data_series.index)

            # Extract static info from the first row (they should be constant per security)
            local_static_info = {}
            # Make sure we use the *effective* id_column_name used for filtering
            relevant_static_cols = [
                col
                for col in static_cols
                if col in filtered_df.columns and col != id_column_name
            ]
            if not filtered_df.empty and relevant_static_cols:
                first_row = filtered_df.iloc[0]
                local_static_info = {
                    col: first_row[col]
                    for col in relevant_static_cols
                    if pd.notna(first_row[col])
                }
                # print(f"Static info found in {filename}: {local_static_info}")

            return data_series, dates, local_static_info

        except KeyError as e:
            current_app.logger.warning(
                f"Warning: KeyError accessing data for {id_column_name}='{security_id_to_filter}' in {filename}. Likely missing ID. Error: {e}"
            )
            return None, set(), {}
        except Exception as e:
            current_app.logger.error(
                f"Error processing file {filename} for {id_column_name}='{security_id_to_filter}': {e}"
            )
            import traceback

            traceback.print_exc()  # Print full traceback for debugging
            return None, set(), {}

    # --- Load Data for Each Chart Section ---

    # 1. Primary Metric (passed in URL) + Price
    metric_filename = f"sec_{metric_name}.csv"
    price_filename = "sec_Price.csv"
    # Use the decoded ID for filtering
    metric_series, metric_dates, metric_static = load_filter_and_extract(
        metric_filename, decoded_security_id
    )
    price_series, price_dates, price_static = load_filter_and_extract(
        price_filename, decoded_security_id
    )
    all_dates.update(metric_dates)
    all_dates.update(price_dates)
    static_info.update(metric_static)  # Prioritize static info from metric file
    static_info.update(price_static)  # Add/overwrite with price file info

    # 2. Duration + SP Duration
    duration_filename = "sec_Duration.csv"
    sp_duration_filename = "sec_DurationSP.csv"  # Optional SP file
    duration_series, duration_dates, duration_static = load_filter_and_extract(
        duration_filename, decoded_security_id
    )
    sp_duration_series, sp_duration_dates, sp_duration_static = load_filter_and_extract(
        sp_duration_filename, decoded_security_id
    )
    all_dates.update(duration_dates)
    all_dates.update(sp_duration_dates)
    static_info.update(duration_static)
    static_info.update(sp_duration_static)

    # 3. Spread Duration + SP Spread Duration
    spread_dur_filename = "sec_Spread duration.csv"
    sp_spread_dur_filename = "sec_Spread durationSP.csv"  # Optional SP file
    spread_dur_series, spread_dur_dates, spread_dur_static = load_filter_and_extract(
        spread_dur_filename, decoded_security_id
    )
    sp_spread_dur_series, sp_spread_dur_dates, sp_spread_dur_static = (
        load_filter_and_extract(sp_spread_dur_filename, decoded_security_id)
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
            spread_filename, decoded_security_id
        )
        all_dates.update(spread_dates)
        static_info.update(spread_static)
    else:
        spread_series = metric_series  # Reuse already loaded data
        spread_dates = metric_dates
        # Static info already handled

    sp_spread_series, sp_spread_dates, sp_spread_static = load_filter_and_extract(
        sp_spread_filename, decoded_security_id
    )
    all_dates.update(sp_spread_dates)
    static_info.update(sp_spread_static)

    # 5. YTM + SP YTM
    ytm_filename = "sec_YTM.csv"
    sp_ytm_filename = "sec_YTMSP.csv"
    ytm_series, ytm_dates, _ = load_filter_and_extract(
        ytm_filename, decoded_security_id
    )
    sp_ytm_series, sp_ytm_dates, _ = load_filter_and_extract(
        sp_ytm_filename, decoded_security_id
    )
    all_dates.update(ytm_dates)
    all_dates.update(sp_ytm_dates)

    # 6. YTW + SP YTW
    ytw_filename = "sec_YTW.csv"
    sp_ytw_filename = "sec_YTWSP.csv"
    ytw_series, ytw_dates, _ = load_filter_and_extract(
        ytw_filename, decoded_security_id
    )
    sp_ytw_series, sp_ytw_dates, _ = load_filter_and_extract(
        sp_ytw_filename, decoded_security_id
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
            decoded_security_id, chart_dates, data_folder
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
    current_app.logger.info(
        f"DEBUG: COLOR_PALETTE contents just before use: {COLOR_PALETTE}"
    )  # <<< ADDED DEBUG PRINT
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
        # Group 1: Identifiers
        identifiers = {
            k: reference_row[k]
            for k in ["ISIN", "Security Name", "BBG ID", "BBG Ticker Yellow"]
            if k in reference_row
        }
        # Group 2: Classification
        classification = {
            k: reference_row[k]
            for k in [
                "Security Sub Type",
                "SS Project - In Scope",
                "Is Distressed",
                "Rating",
                "BBG LEVEL 3",
                "CCY",
                "Country Of Risk",
            ]
            if k in reference_row
        }
        # Group 3: Call/Redemption
        call_info = {
            k: reference_row[k]
            for k in ["Call Indicator", "Make Whole Call"]
            if k in reference_row
        }
        # Group 4: Financials
        financials = {
            k: reference_row[k]
            for k in ["Coupon Rate", "Maturity Date"]
            if k in reference_row
        }
        # Group 5: Other
        others = {
            k: reference_row[k]
            for k in reference_row
            if k not in identifiers
            and k not in classification
            and k not in call_info
            and k not in financials
        }
        static_groups = [
            ("Identifiers", identifiers),
            ("Classification", classification),
            ("Call/Redemption", call_info),
            ("Financials", financials),
            ("Other Details", others),
        ]
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
        exclusion_comment=exclusion_comment,
        open_issues=open_issues,
        bloomberg_yas_url=bloomberg_yas_url,
        holdings_data=holdings_data,
        chart_dates=chart_dates,
    )


@security_bp.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(
        os.path.join(security_bp.root_path, "..", "static"), filename
    )
