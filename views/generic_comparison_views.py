# views/generic_comparison_views.py
# This module defines a generic Flask Blueprint for comparing two security datasets (e.g., spread, duration).
# It supports multiple comparison types defined in config.py.
# Features include:
# - Dynamic loading of configured comparison files.
# - Calculation of comparison statistics.
# - Merging with held status from weights data.
# - Server-side filtering, sorting, and pagination for the summary view.
# - Detail view showing overlayed time-series charts and statistics for a single security.
# - X-axis for all charts uses the full Dates.csv list, handling weekends and holidays.

import pandas as pd
import math
import logging
import os  # Added for path joining
from flask import (
    Blueprint,
    render_template,
    request,
    current_app,
    url_for,
    flash,
    abort,
)
from urllib.parse import (
    unquote,
    urlencode,
)  # For handling security IDs with special chars
from .comparison_helpers import load_generic_comparison_data
from .generic_comparison_helpers import (
    calculate_generic_comparison_stats,
    get_holdings_for_security,
    load_fund_codes_from_csv,
    _apply_summary_filters,
    _apply_summary_sorting,
    _paginate_summary_data,
)
import config
from config import GENERIC_COMPARISON_STATS_KEYS
from typing import Optional, List, Tuple, Dict

# Import shared utilities and processing functions
try:
    from utils import (
        load_weights_and_held_status,
        parse_fund_list,
        load_fund_groups,
    )  # Import parse_fund_list for fund filter logic
    from security_processing import (
        load_and_process_security_data,
    )  # Keep using this standard loader
    from config import COMPARISON_CONFIG, COLOR_PALETTE
    from preprocessing import read_and_sort_dates
except ImportError as e:
    logging.error(f"Error importing modules in generic_comparison_views: {e}")
    from ..utils import load_weights_and_held_status, parse_fund_list
    from ..security_processing import load_and_process_security_data
    from ..config import COMPARISON_CONFIG, COLOR_PALETTE
    from ..preprocessing import read_and_sort_dates

# Define the Blueprint
generic_comparison_bp = Blueprint(
    "generic_comparison_bp",
    __name__,
    template_folder="../templates",
    static_folder="../static",
)

# Use config.COMPARISON_PER_PAGE for pagination

# Purpose: This file defines the Flask Blueprint and routes for generic security data comparisons, including summary and detail views, statistics, filtering, and pagination.

# --- Refactored Helper Functions ---

# Calculate comparison stats function (seems largely reusable, maybe minor tweaks needed)
# Keep it similar to the original version found in comparison_views.py etc.
def calculate_generic_comparison_stats(merged_df, static_data, id_col):
    """
    Calculates comparison statistics for each security.
    Generic version adaptable to different comparison types.

    Args:
        merged_df (pd.DataFrame): The merged dataframe with 'Value_Orig', 'Value_New', 'Date', and the id_col.
        static_data (pd.DataFrame): DataFrame with static info per security, indexed or containing id_col.
        id_col (str): The name of the column containing the Security ID/Name.

    Returns:
        pd.DataFrame: A DataFrame containing comparison statistics for each security.
    """
    log = current_app.logger
    if merged_df.empty:
        log.warning("calculate_generic_comparison_stats received an empty merged_df.")
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(
            f"Specified id_col '{id_col}' not found in merged_df columns for stats calculation: {merged_df.columns.tolist()}"
        )
        return pd.DataFrame()

    log.info(
        f"Calculating generic comparison statistics using ID column: '{id_col}'..."
    )
    stats_list = []

    for sec_id, group in merged_df.groupby(id_col):
        sec_stats = {id_col: sec_id}

        # Ensure Date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(group["Date"]):
            group["Date"] = pd.to_datetime(group["Date"], errors="coerce")

        # Ensure Value columns are numeric
        group["Value_Orig"] = pd.to_numeric(group["Value_Orig"], errors="coerce")
        group["Value_New"] = pd.to_numeric(group["Value_New"], errors="coerce")

        # Filter for overall date range (where at least one value exists)
        group_valid_overall = group.dropna(
            subset=["Value_Orig", "Value_New"], how="all"
        )
        overall_min_date = group_valid_overall["Date"].min()
        overall_max_date = group_valid_overall["Date"].max()

        # Filter for valid comparison points (where BOTH values exist)
        valid_comparison = group.dropna(subset=["Value_Orig", "Value_New"])

        # 1. Correlation of Levels
        if len(valid_comparison) >= 2:
            level_corr = valid_comparison["Value_Orig"].corr(
                valid_comparison["Value_New"]
            )
            sec_stats["Level_Correlation"] = (
                level_corr if pd.notna(level_corr) else None
            )
        else:
            sec_stats["Level_Correlation"] = None

        # 2. Max / Min (using original group)
        sec_stats["Max_Orig"] = group["Value_Orig"].max()
        sec_stats["Min_Orig"] = group["Value_Orig"].min()
        sec_stats["Max_New"] = group["Value_New"].max()
        sec_stats["Min_New"] = group["Value_New"].min()

        # 3. Date Range Comparison
        min_date_orig_idx = group["Value_Orig"].first_valid_index()
        max_date_orig_idx = group["Value_Orig"].last_valid_index()
        min_date_new_idx = group["Value_New"].first_valid_index()
        max_date_new_idx = group["Value_New"].last_valid_index()

        sec_stats["Start_Date_Orig"] = (
            group.loc[min_date_orig_idx, "Date"]
            if min_date_orig_idx is not None
            else None
        )
        sec_stats["End_Date_Orig"] = (
            group.loc[max_date_orig_idx, "Date"]
            if max_date_orig_idx is not None
            else None
        )
        sec_stats["Start_Date_New"] = (
            group.loc[min_date_new_idx, "Date"]
            if min_date_new_idx is not None
            else None
        )
        sec_stats["End_Date_New"] = (
            group.loc[max_date_new_idx, "Date"]
            if max_date_new_idx is not None
            else None
        )

        same_start = (
            pd.notna(sec_stats["Start_Date_Orig"])
            and pd.notna(sec_stats["Start_Date_New"])
            and pd.Timestamp(sec_stats["Start_Date_Orig"])
            == pd.Timestamp(sec_stats["Start_Date_New"])
        )
        same_end = (
            pd.notna(sec_stats["End_Date_Orig"])
            and pd.notna(sec_stats["End_Date_New"])
            and pd.Timestamp(sec_stats["End_Date_Orig"])
            == pd.Timestamp(sec_stats["End_Date_New"])
        )
        sec_stats["Same_Date_Range"] = same_start and same_end

        # Add overall date range for info
        sec_stats["Overall_Start_Date"] = overall_min_date
        sec_stats["Overall_End_Date"] = overall_max_date

        # 4. Correlation of Daily Changes
        if len(valid_comparison) >= 1:  # Need at least 1 point to calculate diff
            valid_comparison = valid_comparison.copy()  # Avoid SettingWithCopyWarning
            valid_comparison["Change_Orig_Corr"] = valid_comparison["Value_Orig"].diff()
            valid_comparison["Change_New_Corr"] = valid_comparison["Value_New"].diff()

            # Drop NaNs created by the diff() itself and any pre-existing NaNs in changes
            valid_changes = valid_comparison.dropna(
                subset=["Change_Orig_Corr", "Change_New_Corr"]
            )

            if len(valid_changes) >= 2:  # Need 2 pairs of *changes* for correlation
                change_corr = valid_changes["Change_Orig_Corr"].corr(
                    valid_changes["Change_New_Corr"]
                )
                sec_stats["Change_Correlation"] = (
                    change_corr if pd.notna(change_corr) else None
                )
            else:
                sec_stats["Change_Correlation"] = None
                log.debug(
                    f"Cannot calculate Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}."
                )
        else:
            sec_stats["Change_Correlation"] = None
            log.debug(
                f"Cannot calculate Change_Correlation for {sec_id}. Need >= 1 valid comparison point to calculate diffs, found {len(valid_comparison)}."
            )

        # 5. Difference Statistics (use valid_comparison df)
        if not valid_comparison.empty:
            valid_comparison["Abs_Diff"] = (
                valid_comparison["Value_Orig"] - valid_comparison["Value_New"]
            ).abs()
            sec_stats["Mean_Abs_Diff"] = valid_comparison["Abs_Diff"].mean()
            sec_stats["Max_Abs_Diff"] = valid_comparison["Abs_Diff"].max()
        else:
            sec_stats["Mean_Abs_Diff"] = None
            sec_stats["Max_Abs_Diff"] = None

        # Count NaNs (use original group)
        sec_stats["NaN_Count_Orig"] = group["Value_Orig"].isna().sum()
        sec_stats["NaN_Count_New"] = group["Value_New"].isna().sum()
        sec_stats["Total_Points"] = len(group)

        stats_list.append(sec_stats)

    if not stats_list:
        log.warning("No statistics were generated.")
        return pd.DataFrame()

    summary_df = pd.DataFrame(stats_list)

    # Merge static data back (ensure ID columns match)
    if (
        not static_data.empty
        and id_col in static_data.columns
        and id_col in summary_df.columns
    ):
        # Ensure consistent types before merge if possible
        try:
            if static_data[id_col].dtype != summary_df[id_col].dtype:
                log.warning(
                    f"Attempting merge with different dtypes for ID column '{id_col}': Static ({static_data[id_col].dtype}), Summary ({summary_df[id_col].dtype}). Converting static to summary type."
                )
                static_data[id_col] = static_data[id_col].astype(
                    summary_df[id_col].dtype
                )
        except Exception as e:
            log.warning(
                f"Could not ensure matching dtypes for merge key '{id_col}': {e}"
            )

        summary_df = pd.merge(summary_df, static_data, on=id_col, how="left")
        log.info(
            f"Successfully merged static data back. Summary shape: {summary_df.shape}"
        )
    elif not static_data.empty:
        log.warning(
            f"Could not merge static data. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns})."
        )

    log.info(
        f"--- Exiting calculate_generic_comparison_stats. Output shape: {summary_df.shape} ---"
    )
    return summary_df


# === Filtering Helper =========================================================


# === Sorting Helper ===========================================================


# === Pagination Helper =======================================================


@generic_comparison_bp.route("/<comparison_type>/summary")
def summary(comparison_type):
    """Displays the generic comparison summary page with filtering, sorting, and pagination. Now supports fund group filtering."""
    log = current_app.logger
    log.info(
        f"--- Starting Generic Comparison Summary Request: Type = {comparison_type} ---"
    )

    # === Step 1: Validate comparison type & retrieve config ====================
    comp_config = COMPARISON_CONFIG.get(comparison_type)
    if not comp_config:
        log.error(f"Invalid comparison_type requested: {comparison_type}")
        abort(404, description=f"Comparison type '{comparison_type}' not found.")

    display_name = comp_config["display_name"]
    file1 = comp_config["file1"]
    file2 = comp_config["file2"]
    log.info(f"Config loaded for '{comparison_type}': file1='{file1}', file2='{file2}'")

    # === Step 2: Parse request parameters (sorting, filters, pagination) =======
    page = request.args.get("page", 1, type=int)
    sort_by = request.args.get("sort_by", "Change_Correlation")
    sort_order = request.args.get("sort_order", "desc").lower()
    ascending = sort_order == "asc"
    show_sold = request.args.get("show_sold", "false").lower() == "true"
    active_filters = {
        k.replace("filter_", ""): v
        for k, v in request.args.items()
        if k.startswith("filter_") and v
    }
    # === Fund Group Filter ===
    selected_fund_group = request.args.get("fund_group", None)
    log.info(
        f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}, FundGroup={selected_fund_group}"
    )

    # === Step 3: Load Data ===
    data_folder = current_app.config["DATA_FOLDER"]
    merged_data, static_data, static_cols, actual_id_col = load_generic_comparison_data(
        data_folder, file1, file2
    )

    if actual_id_col is None or merged_data.empty:
        log.warning(
            f"Failed to load or merge data for comparison type '{comparison_type}'. Rendering empty page."
        )
        return render_template(
            "comparison_summary_base.html",
            comparison_type=comparison_type,
            display_name=display_name,
            table_data=[],
            columns_to_display=[],
            id_column_name="Security",
            filter_options={},
            active_filters={},
            pagination=None,
            current_sort_by=sort_by,
            current_sort_order=sort_order,
            show_sold=show_sold,
            fund_groups={},
            selected_fund_group=None,
            message=f"Could not load data for {display_name} comparison.",
        )

    log.info(f"Actual ID column identified for '{comparison_type}': '{actual_id_col}'")

    # === Step 4: Calculate comparison statistics ==============================
    summary_stats = calculate_generic_comparison_stats(
        merged_data, static_data, id_col=actual_id_col
    )

    if summary_stats.empty:
        log.info(f"No summary statistics could be calculated for {comparison_type}.")
        return render_template(
            "comparison_summary_base.html",
            comparison_type=comparison_type,
            display_name=display_name,
            table_data=[],
            columns_to_display=[],
            id_column_name=actual_id_col,
            filter_options={},
            active_filters={},
            pagination=None,
            current_sort_by=sort_by,
            current_sort_order=sort_order,
            show_sold=show_sold,
            fund_groups={},
            selected_fund_group=None,
            message=f"No {display_name} comparison statistics available.",
        )

    # === Step 5: Load & merge held status (performed before applying filters) ===
    held_status = load_weights_and_held_status(
        current_app.config["DATA_FOLDER"], id_col_override="ISIN"
    )

    if not held_status.empty and actual_id_col in summary_stats.columns:
        try:
            if summary_stats[actual_id_col].dtype != held_status.index.dtype:
                log.info(
                    "Converting merge keys to string for held status merge (Summary: %s, Held: %s)",
                    summary_stats[actual_id_col].dtype,
                    held_status.index.dtype,
                )
                summary_stats[actual_id_col] = summary_stats[actual_id_col].astype(str)
                held_status.index = held_status.index.astype(str)
                held_status.index.name = actual_id_col
        except Exception as e:
            log.error("Failed to convert merge keys for held status merge: %s", e)

        log.info(
            "Attempting held status merge: left_on='%s', right_index name='%s'",
            actual_id_col,
            held_status.index.name,
        )

        summary_stats = pd.merge(
            summary_stats,
            held_status.rename("is_held"),
            left_on=actual_id_col,
            right_index=True,
            how="left",
        )

        if "is_held" in summary_stats.columns:
            summary_stats["is_held"] = summary_stats["is_held"].fillna(False)
        else:
            log.error("'is_held' column missing after merge attempt!")
            summary_stats["is_held"] = False
    else:
        log.warning(
            "Could not merge held status. Held status empty: %s or ID mismatch ('%s' in summary: %s)",
            held_status.empty,
            actual_id_col,
            actual_id_col in summary_stats.columns,
        )
        summary_stats["is_held"] = False

    # === Step 6–8: Apply summary filters using helper =========================
    # preserve row count before filtering for messaging logic
    original_count = len(summary_stats)
    filtered_data = _apply_summary_filters(
        summary_stats,
        selected_fund_group,
        show_sold,
        active_filters,
        data_folder,
        actual_id_col,
        static_cols,
    )

    # Prepare fund group filter options (requires data post-held filter)
    fund_groups_dict = load_fund_groups(data_folder)
    all_funds_in_data = set()
    if config.FUNDS_COL in filtered_data.columns:
        for x in filtered_data[config.FUNDS_COL].dropna():
            all_funds_in_data.update(parse_fund_list(x))
    else:
        fcands = [c for c in ["Fund", "Fund Code", "Code"] if c in filtered_data.columns]
        if fcands:
            all_funds_in_data = set(filtered_data[fcands[0]].unique())
    filtered_fund_groups = {
        g: [f for f in funds if f in all_funds_in_data]
        for g, funds in fund_groups_dict.items()
    }
    filtered_fund_groups = {g: v for g, v in filtered_fund_groups.items() if v}

    # Regenerate filter_options after helper filters
    filter_options = {}
    if not filtered_data.empty:
        potential_filter_cols = [
            col for col in static_cols if col in filtered_data.columns and col != actual_id_col
        ]
        for col in potential_filter_cols:
            if col == "Funds":
                filter_options[col] = load_fund_codes_from_csv(data_folder)
            else:
                uniques = filtered_data[col].dropna().unique()
                try:
                    sorted_vals = sorted(
                        uniques, key=lambda x: (isinstance(x, (int, float)), str(x).lower())
                    )
                except TypeError:
                    sorted_vals = sorted(uniques, key=str)
                if sorted_vals:
                    filter_options[col] = sorted_vals
        filter_options = dict(sorted(filter_options.items()))

    # === Handle No Data After Filters ===
    if filtered_data.empty:
        message = (
            f"No {display_name} comparison data available matching the current filters."
        )
        if not summary_stats.empty:  # Means filters caused the empty result
            message = f"No {display_name} comparison data matches the selected filters."
            if (
                not show_sold
                and "is_held" in summary_stats.columns
                and not summary_stats[summary_stats["is_held"]].empty
            ):
                message += " Try enabling 'Show Sold Securities'."
        elif original_count > 0 and not show_sold:  # Holding filter caused empty result
            message = "No *currently held* securities found for this comparison. Try enabling 'Show Sold Securities'."
        else:  # Original data was likely empty
            message = f"No data found for {display_name} comparison in files '{file1}' and '{file2}'."

        log.warning(message)
        return render_template(
            "comparison_summary_base.html",
            comparison_type=comparison_type,
            display_name=display_name,
            table_data=[],
            columns_to_display=[],
            id_column_name=actual_id_col,
            filter_options=filter_options,
            active_filters=active_filters,
            pagination=None,
            current_sort_by=sort_by,
            current_sort_order=sort_order,
            show_sold=show_sold,
            fund_groups=filtered_fund_groups,
            selected_fund_group=selected_fund_group,
            message=message,
        )

    # === Apply Sorting ===
    sorted_data, sort_by, sort_order = _apply_summary_sorting(
        filtered_data, sort_by, sort_order, actual_id_col
    )

    # === Pagination ===
    paginated_data, pagination_context = _paginate_summary_data(
        sorted_data, page, config.COMPARISON_PER_PAGE
    )

    pagination_context["url_for_page"] = lambda p: url_for(
        "generic_comparison_bp.summary",
        comparison_type=comparison_type,
        page=p,
        **{k: v for k, v in request.args.items() if k != "page"},
    )

    # === Prepare for Template ===
    # Define core stats columns + dynamic static columns + ID column
    core_stats_cols = [
        "Level_Correlation",
        "Change_Correlation",
        "Mean_Abs_Diff",
        "Max_Abs_Diff",
        "Same_Date_Range",
        "is_held",  # Add is_held for potential display/styling
        # Maybe add 'Total_Points', 'NaN_Count_Orig', 'NaN_Count_New' if useful
    ]
    # Ensure columns exist in the final paginated data
    columns_to_display = (
        [actual_id_col]
        + [
            col
            for col in static_cols
            if col != actual_id_col and col in paginated_data.columns
        ]
        + [col for col in core_stats_cols if col in paginated_data.columns]
    )

    table_data_dict = paginated_data.to_dict(orient="records")

    log.info(
        f"--- Successfully Prepared Data for Generic Comparison Summary Template ({comparison_type}) ---"
    )
    return render_template(
        "comparison_summary_base.html",  # Use the new base template
        comparison_type=comparison_type,
        display_name=display_name,
        table_data=table_data_dict,
        columns_to_display=columns_to_display,
        id_column_name=actual_id_col,  # Pass the actual ID column name
        filter_options=filter_options,
        active_filters=active_filters,
        current_sort_by=sort_by,
        current_sort_order=sort_order,
        pagination=pagination_context,
        show_sold=show_sold,
        fund_groups=filtered_fund_groups,
        selected_fund_group=selected_fund_group,
        message=None,
    )  # No message if data is present


@generic_comparison_bp.route("/<comparison_type>/details/<path:security_id>")
def details(comparison_type, security_id):
    """Displays the detail page for a specific security comparison. X-axis always uses Dates.csv."""
    log = current_app.logger
    security_id_encoded = security_id
    try:
        decoded_security_id = unquote(security_id_encoded)
        log.info(
            f"--- Starting Generic Comparison Detail Request: Type = {comparison_type}, Decoded Security ID = '{decoded_security_id}' (Encoded: '{security_id_encoded}') ---"
        )
    except Exception as e:
        log.error(f"Error decoding security ID '{security_id_encoded}': {e}")
        abort(400, description="Invalid security ID format in URL.")

    # === Step 1: Validate comparison type & retrieve config ==================
    comp_config = COMPARISON_CONFIG.get(comparison_type)
    if not comp_config:
        log.error(f"Invalid comparison_type requested: {comparison_type}")
        abort(404, description=f"Comparison type '{comparison_type}' not found.")

    display_name = comp_config["display_name"]
    file1 = comp_config["file1"]
    file2 = comp_config["file2"]
    value_label = comp_config.get("value_label", "Value")
    log.info(
        f"Config loaded for '{comparison_type}': file1='{file1}', file2='{file2}', value_label='{value_label}'"
    )

    # === Step 2: Load merged data & static info ==============================
    data_folder = current_app.config["DATA_FOLDER"]
    merged_data, static_data, _, actual_id_col = load_generic_comparison_data(
        data_folder, file1, file2
    )

    # === Step 3: Load full date list for chart axis ==========================
    dates_file_path = os.path.join(data_folder, "Dates.csv")
    full_date_list = read_and_sort_dates(dates_file_path) or []
    if not full_date_list:
        log.warning(
            f"Could not load Dates.csv from {dates_file_path}. Chart x-axis may be incomplete."
        )

    if actual_id_col is None or merged_data.empty:
        flash(
            f"Could not load comparison data for type '{comparison_type}'.", "warning"
        )
        log.warning(
            f"Failed to load comparison data for {comparison_type}, rendering potentially empty detail page."
        )
        return render_template(
            "comparison_details_base.html",
            comparison_type=comparison_type,
            display_name=display_name,
            value_label=value_label,
            security_id=decoded_security_id,
            security_name=decoded_security_id,  # Default if no static data
            chart_data=None,
            stats=None,
            id_column_name="Security",  # Default
            message=f"Could not load data for comparison '{display_name}'.",
            holdings_data=None,  # Added
            chart_dates=None,  # Added
        )

    # === Step 4: Filter merged data for requested security ===================
    log.debug(
        f"Filtering merged data for security ID '{decoded_security_id}' using column '{actual_id_col}'"
    )
    try:
        merged_data[actual_id_col] = merged_data[actual_id_col].astype(str)
        security_data = merged_data[
            merged_data[actual_id_col] == str(decoded_security_id)
        ].copy()
    except KeyError:
        log.error(
            f"ID column '{actual_id_col}' not found in merged_data during filtering."
        )
        security_data = pd.DataFrame()
    except Exception as e:
        log.error(
            f"Error filtering merged_data for security ID '{decoded_security_id}': {e}"
        )
        security_data = pd.DataFrame()

    if security_data.empty:
        log.warning(
            f"No data found for Security ID '{decoded_security_id}' (using column '{actual_id_col}') in comparison type '{comparison_type}'."
        )
        return render_template(
            "comparison_details_base.html",
            comparison_type=comparison_type,
            display_name=display_name,
            value_label=value_label,
            security_id=decoded_security_id,
            security_name=decoded_security_id,  # Attempt to get name below
            chart_data=None,
            stats=None,
            id_column_name=actual_id_col,
            message=f"No data found for {actual_id_col} '{decoded_security_id}' in {display_name} comparison.",
            holdings_data=None,  # Added
            chart_dates=None,  # Added
        )

    # === Step 5: Calculate stats for this security ===========================
    security_static_row = pd.DataFrame()
    if not static_data.empty and actual_id_col in static_data.columns:
        try:
            static_data[actual_id_col] = static_data[actual_id_col].astype(str)
            security_static_row = static_data[
                static_data[actual_id_col] == str(decoded_security_id)
            ]
        except Exception as e:
            log.warning(
                f"Error getting static data row for '{decoded_security_id}': {e}"
            )

    stats_df = calculate_generic_comparison_stats(
        security_data, security_static_row, actual_id_col
    )

    stats = {}
    security_name = decoded_security_id  # Default name is the ID
    if not stats_df.empty:
        stats = stats_df.iloc[0].to_dict()
        potential_name_col = "Security Name"
        if potential_name_col in stats and pd.notna(stats[potential_name_col]):
            security_name = stats[potential_name_col]
            log.info(
                f"Found security name: '{security_name}' for ID '{decoded_security_id}'"
            )
        else:
            log.info(
                f"Using ID '{decoded_security_id}' as name (Column '{potential_name_col}' not found or is null in stats)."
            )
    else:
        log.warning(
            f"Could not calculate statistics for security {decoded_security_id}."
        )

    # === Step 6: Build chart data aligned to Dates.csv =======================
    chart_data = None
    chart_dates = full_date_list.copy() if full_date_list else []
    if not security_data.empty and chart_dates:
        try:
            security_data["Date"] = pd.to_datetime(security_data["Date"])
            security_data = security_data.sort_values(by="Date")
            # Reindex to full_date_list
            security_data.set_index(
                security_data["Date"].dt.strftime("%Y-%m-%d"), inplace=True
            )
            value_orig_aligned = []
            value_new_aligned = []
            for date_str in chart_dates:
                row = (
                    security_data.loc[date_str]
                    if date_str in security_data.index
                    else None
                )
                if row is not None:
                    # If multiple rows per date, take the first
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    value_orig_aligned.append(
                        row["Value_Orig"] if pd.notna(row["Value_Orig"]) else None
                    )
                    value_new_aligned.append(
                        row["Value_New"] if pd.notna(row["Value_New"]) else None
                    )
                else:
                    value_orig_aligned.append(None)
                    value_new_aligned.append(None)
            chart_data = {
                "labels": chart_dates,
                "datasets": [
                    {
                        "label": f"Original {value_label}",
                        "data": value_orig_aligned,
                        "borderColor": COLOR_PALETTE[0],
                        "backgroundColor": COLOR_PALETTE[0] + "80",
                        "fill": False,
                        "tension": 0.1,
                    },
                    {
                        "label": f"New {value_label}",
                        "data": value_new_aligned,
                        "borderColor": COLOR_PALETTE[1],
                        "backgroundColor": COLOR_PALETTE[1] + "80",
                        "fill": False,
                        "tension": 0.1,
                    },
                ],
            }
            # --- Ensure chart_data is JSON serializable (convert numpy types) ---
            import numpy as np

            def convert_numpy(obj):
                if isinstance(obj, np.generic):
                    return obj.item()
                if isinstance(obj, dict):
                    return {k: convert_numpy(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [convert_numpy(i) for i in obj]
                return obj

            chart_data = convert_numpy(chart_data)
            log.info(
                f"Prepared chart data for {decoded_security_id} with {len(chart_dates)} dates (from Dates.csv)."
            )
        except Exception as e:
            log.error(
                f"Error processing dates for chart data for security {decoded_security_id}: {e}"
            )
            flash("Error processing dates for chart.", "danger")
    else:
        log.warning(
            f"Security data is empty or chart_dates missing for {decoded_security_id}, cannot generate chart."
        )

    # === Step 7: Load holdings data for overlay ==============================
    holdings_data = {}
    holdings_error = None
    if chart_dates:  # Only try to get holdings if we have dates from Dates.csv
        holdings_data, _, holdings_error = get_holdings_for_security(
            decoded_security_id, chart_dates, data_folder
        )
        if holdings_error:
            flash(f"Note: Could not display fund holdings. {holdings_error}", "warning")
            log.warning(f"Holdings Error for {decoded_security_id}: {holdings_error}")
        if not holdings_data and not holdings_error:
            log.info(
                f"No holdings information found in w_secs.csv for security {decoded_security_id}."
            )
    else:
        log.warning(
            f"Skipping holdings check for {decoded_security_id} because chart dates are missing."
        )

    # --- Prepare Holdings Summary for Display ---
    fund_holdings_summary = {}
    if holdings_data:
        for fund, held_flags in holdings_data.items():
            # Check if the fund held the security at ANY point in the chart's timeframe
            if any(held_flags):
                fund_holdings_summary[fund] = "Held during period"
            else:
                # This case shouldn't happen if w_secs only contains > 0 weights,
                # but including for completeness. It might also mean the fund exists
                # for the security but not within the chart's date range.
                fund_holdings_summary[fund] = "Not held during period"
    elif not holdings_error: # No error, but no data either
         fund_holdings_summary = {"Note": "No holding information found for this security in w_secs.csv."}
    # If there was a holdings_error, the flash message handles it.

    log.info(f"--- Successfully Prepared Data for Generic Comparison Detail ({comparison_type}, {decoded_security_id}) ---")
    return render_template(
        "comparison_details_base.html",
        comparison_type=comparison_type,
        display_name=display_name,
        value_label=value_label,
        security_id=decoded_security_id,  # Pass decoded ID
        security_name=security_name,  # Pass potentially better name
        chart_data=chart_data,
        stats=stats if stats else None,  # Pass dict or None
        id_column_name=actual_id_col,
        message=None,  # No error message if we got this far, warnings flashed
        holdings_data=holdings_data,  # Pass holdings dict
        chart_dates=chart_dates,  # Pass list of dates
        fund_holdings_summary=fund_holdings_summary # Pass summary dict
    )
