# Purpose: This file defines the Flask Blueprint and routes for time-series metric details, including contribution analysis, chart rendering, and metric calculations.
# This file defines the routes for displaying detailed views of specific time-series metrics.
# It handles requests where the user wants to see the data and charts for a single metric
# (like 'Yield' or 'Spread Duration') across all applicable funds.
# It loads primary and optionally secondary data, calculates key metrics,
# handles filtering based on 'SS Project - In Scope' status via a query parameter,
# prepares data for visualization, and renders the metric detail page.
# All charts use the full Dates.csv list for the x-axis, handling weekends and holidays.
# Also includes routes for the 'Inspect' feature to analyze security contributions to metric changes.

"""
Blueprint for metric-specific routes (e.g., displaying individual metric charts).
"""
from flask import (
    Blueprint,
    render_template,
    jsonify,
    current_app,
    request,
)  # Added request
import os
import pandas as pd
import numpy as np
import traceback
import math
from core import config

# Import necessary functions/constants from other modules
from core.config import COLOR_PALETTE

# Make sure load_and_process_data and other loaders can handle security-level data if needed
from core.data_loader import load_and_process_data, LoadResult, load_simple_csv
from analytics.metric_calculator import calculate_latest_metrics
from data_processing.preprocessing import read_and_sort_dates
from core.utils import get_data_folder_path, load_fund_groups, filter_business_dates

# Define the blueprint for metric routes, using '/metric' as the URL prefix
metric_bp = Blueprint("metric", __name__, url_prefix="/metric")


# Helper function to safely convert values to JSON serializable types
def make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None  # Convert NaN/inf to None for JSON
        return obj
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj)  # Convert numpy integers
    elif isinstance(obj, (np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)  # Convert numpy floats
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()  # Convert Timestamps
    return obj


@metric_bp.route("/<string:metric_name>")
def metric_page(metric_name):
    """Renders the detailed page (`metric_page_js.html`) for a specific metric. X-axis always uses Dates.csv.
    Adds support for filtering by fund group (from FundGroups.csv)."""
    
    # Get metric config from the mapping
    metric_key = metric_name.replace(' ', '_').replace('-', '_').lower()
    metric_cfg = config.METRIC_FILE_MAP.get(metric_key)
    if not metric_cfg:
        current_app.logger.error(f"Metric '{metric_name}' not found in config mapping.")
        return f"Metric '{metric_name}' not found in config.", 404
    
    # Use the config mapping to get the correct file names
    primary_filename = metric_cfg["ts_file"]
    secondary_filename = metric_cfg["sp_ts_file"]
    
    fund_code = "N/A"  # Default for logging fallback in case of early error
    latest_date_overall = pd.Timestamp.min  # Initialize
    error_message = None  # Initialize error message

    try:
        # --- Get Filter State from Query Parameter ---
        sp_valid_param = request.args.get("sp_valid", "true").lower()
        filter_sp_valid = sp_valid_param == "true"
        # --- Fund Group Filter: get from query param ---
        selected_fund_group = request.args.get("fund_group", None)
        current_app.logger.info(
            f"--- Processing metric: {metric_name}, S&P Valid Filter: {filter_sp_valid}, Selected Fund Group: {selected_fund_group} ---"
        )
        current_app.logger.info(
            f"URL Query Params: {request.args}"
        )  # Log query params for debugging

        # --- Load Data (Primary and Secondary) with Filtering ---
        current_app.logger.info(
            f"Loading data: Primary='{primary_filename}', Secondary='{secondary_filename}', Filter='{filter_sp_valid}'"
        )
        load_result: LoadResult = load_and_process_data(
            primary_filename=primary_filename,
            secondary_filename=secondary_filename,
            filter_sp_valid=filter_sp_valid,  # Pass the filter flag
        )
        (
            primary_df,
            pri_fund_cols,
            pri_bench_col,
            secondary_df,
            sec_fund_cols,
            sec_bench_col,
        ) = load_result

        # --- Fund Group Filtering: Apply to DataFrames Before Metrics ---
        data_folder = current_app.config["DATA_FOLDER"]
        fund_groups_dict = load_fund_groups(data_folder)
        # Filter the groups dictionary first based on the currently loaded funds
        all_funds_in_data_primary = (
            set(primary_df.index.get_level_values("Code"))
            if primary_df is not None and "Code" in primary_df.index.names
            else set()
        )
        all_funds_in_data_secondary = (
            set(secondary_df.index.get_level_values("Code"))
            if secondary_df is not None and "Code" in secondary_df.index.names
            else set()
        )
        all_funds_in_data = all_funds_in_data_primary.union(all_funds_in_data_secondary)

        filtered_fund_groups_for_dropdown = {
            g: [f for f in funds if f in all_funds_in_data]
            for g, funds in fund_groups_dict.items()
        }
        filtered_fund_groups_for_dropdown = {
            g: funds for g, funds in filtered_fund_groups_for_dropdown.items() if funds
        }  # Remove empty groups

        if (
            selected_fund_group
            and selected_fund_group in filtered_fund_groups_for_dropdown
        ):  # Use the filtered list for checking validity
            current_app.logger.info(
                f"Applying fund group filter: {selected_fund_group}"
            )
            allowed_funds = set(filtered_fund_groups_for_dropdown[selected_fund_group])
            # Filter primary_df and secondary_df to only include allowed funds
            if primary_df is not None and not primary_df.empty:
                idx_names = list(primary_df.index.names)
                if "Code" in idx_names:
                    primary_df = primary_df[
                        primary_df.index.get_level_values("Code").isin(allowed_funds)
                    ]
                    pri_fund_cols = [
                        col for col in pri_fund_cols if col in primary_df.columns
                    ]  # Update fund cols if some were dropped
            if secondary_df is not None and not secondary_df.empty:
                idx_names = list(secondary_df.index.names)
                if "Code" in idx_names:
                    secondary_df = secondary_df[
                        secondary_df.index.get_level_values("Code").isin(allowed_funds)
                    ]
                    sec_fund_cols = [
                        col for col in sec_fund_cols if col in secondary_df.columns
                    ]  # Update fund cols
        elif selected_fund_group:
            current_app.logger.warning(
                f"Selected fund group '{selected_fund_group}' not found in available groups for this data or is empty. Ignoring filter."
            )
            selected_fund_group = None  # Reset if invalid

        # --- Validate Primary Data (Post-Filtering) ---
        if primary_df is None or primary_df.empty:
            data_folder_for_error = current_app.config["DATA_FOLDER"]
            primary_filepath = os.path.join(data_folder_for_error, primary_filename)
            if not os.path.exists(primary_filepath):
                current_app.logger.error(
                    f"Error: Primary data file not found: {primary_filepath} (Filter: {filter_sp_valid}, Group: {selected_fund_group})"
                )
                error_message = f"<strong>Missing Data File!</strong><br/>The required data file '<code>{primary_filename}</code>' is not found in the Data directory.<br/>Full path expected: <code>{primary_filepath}</code><br/>Please ensure the file exists before accessing this page."
                # Render template with error message and filter state
                return (
                    render_template(
                        "metric_page_js.html",
                        metric_name=metric_name,
                        metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
                        charts_data_json="{}",  # Empty data
                        latest_date="N/A",
                        missing_funds=pd.DataFrame(),  # Empty dataframe
                        sp_valid_state=filter_sp_valid,  # Pass filter state
                        secondary_data_initially_available=False,
                        fund_groups=filtered_fund_groups_for_dropdown,
                        selected_fund_group=selected_fund_group,
                        error_message=error_message,
                    ),
                    404,
                )
            else:
                current_app.logger.error(
                    f"Error: Failed to process primary data file '{primary_filename}' or file became empty after filtering (Filter: {filter_sp_valid}, Group: {selected_fund_group})."
                )
                # Construct error message piece by piece
                error_message_base = f"Error: Could not process required data for metric '{metric_name}' (file: '{primary_filename}')."
                error_details = []
                if filter_sp_valid:
                    error_details.append(
                        "The data might be missing, empty, or contain no rows marked as 'TRUE' in 'SS Project - In Scope' when the S&P Valid filter is ON."
                    )
                if selected_fund_group:
                    error_details.append(
                        f"Or no data was found for the selected fund group '{selected_fund_group}'."
                    )
                if not error_details:  # If no specific filter reason, add generic one
                    error_details.append("Check file format or logs.")
                error_message = f"{error_message_base} {' '.join(error_details)}"
                # Render template with error message and filter state
                return (
                    render_template(
                        "metric_page_js.html",
                        metric_name=metric_name,
                        metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
                        charts_data_json="{}",
                        latest_date="N/A",
                        missing_funds=pd.DataFrame(),
                        sp_valid_state=filter_sp_valid,
                        secondary_data_initially_available=False,
                        fund_groups=filtered_fund_groups_for_dropdown,
                        selected_fund_group=selected_fund_group,
                        error_message=error_message,
                    ),
                    500,
                )

        # Add check for pri_fund_cols after ensuring primary_df is not None
        if not pri_fund_cols:  # Check if list is empty after potential filtering
            current_app.logger.error(
                f"Error: Could not identify primary fund value columns in '{primary_filename}' after loading and filtering."
            )
            error_message = f"Error: Failed to identify fund value columns in '{primary_filename}' after filtering. Check file structure or filter criteria."
            return (
                render_template(
                    "metric_page_js.html",
                    metric_name=metric_name,
                    metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
                    charts_data_json="{}",
                    latest_date="N/A",
                    missing_funds=pd.DataFrame(),
                    sp_valid_state=filter_sp_valid,
                    secondary_data_initially_available=False,
                    fund_groups=filtered_fund_groups_for_dropdown,
                    selected_fund_group=selected_fund_group,
                    error_message=error_message,
                ),
                500,
            )

        # --- Determine Combined Metadata (Post-Filtering) ---
        all_dfs_for_meta = [
            df for df in [primary_df, secondary_df] if df is not None and not df.empty
        ]
        if not all_dfs_for_meta:
            current_app.logger.error(
                f"Error: No valid data loaded for {metric_name} (Filter: {filter_sp_valid}, Group: {selected_fund_group})"
            )
            error_message = f"Error: No data found for metric '{metric_name}' (Filter Applied: {filter_sp_valid}, Group: {selected_fund_group})."
            return (
                render_template(
                    "metric_page_js.html",
                    metric_name=metric_name,
                    metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
                    charts_data_json="{}",
                    latest_date="N/A",
                    missing_funds=pd.DataFrame(),
                    sp_valid_state=filter_sp_valid,
                    secondary_data_initially_available=False,
                    fund_groups=filtered_fund_groups_for_dropdown,
                    selected_fund_group=selected_fund_group,
                    error_message=error_message,
                ),
                404,
            )

        # --- Calculate Latest Date Overall ---
        try:
            # Combine DataFrames to get overall latest date - fix for MultiIndex concatenation error
            if all_dfs_for_meta:
                combined_df = pd.concat(all_dfs_for_meta, ignore_index=False)
                latest_date_overall = combined_df.index.get_level_values(0).max()
                latest_date_str = (
                    latest_date_overall.strftime("%Y-%m-%d")
                    if pd.notna(latest_date_overall)
                    else "N/A"
                )
            else:
                latest_date_overall = pd.Timestamp.min
                latest_date_str = "N/A"
        except Exception as idx_err:
            current_app.logger.error(
                f"Error combining indices or getting latest date for {metric_name}: {idx_err}"
            )
            # Fallback to primary df if it exists
            if primary_df is not None and not primary_df.empty:
                try:
                    # Attempt to get date from primary_df
                    latest_date_overall = primary_df.index.get_level_values(0).max()
                    latest_date_str = (
                        latest_date_overall.strftime("%Y-%m-%d")
                        if pd.notna(latest_date_overall)
                        else "N/A"
                    )
                    current_app.logger.warning(
                        f"Warning: Using latest date from primary data only: {latest_date_str}"
                    )
                except Exception as fallback_err:
                    # Handle error if even primary_df fails
                    current_app.logger.error(
                        f"Error getting latest date even from primary_df: {fallback_err}"
                    )
                    latest_date_overall = (
                        pd.Timestamp.min
                    )  # Reset to avoid downstream errors
                    latest_date_str = "N/A"
            else:
                # Handle case where primary_df was None or empty initially
                current_app.logger.error(
                    "Could not determine latest date from any available data (primary_df was None or empty)."
                )
                latest_date_overall = (
                    pd.Timestamp.min
                )  # Reset to avoid downstream errors
                latest_date_str = "N/A"

        # --- Check Secondary Data Availability (Post-Filtering)---
        secondary_data_available = (
            secondary_df is not None
            and not secondary_df.empty
            and sec_fund_cols is not None
            and sec_fund_cols
        )
        current_app.logger.info(
            f"Secondary data available for {metric_name} (post-filter): {secondary_data_available}"
        )

        # --- Calculate Metrics (based on potentially filtered data) ---
        current_app.logger.info(f"Calculating metrics for {metric_name}...")
        # Ensure we pass potentially filtered secondary data
        latest_metrics = calculate_latest_metrics(
            primary_df=primary_df,
            primary_fund_cols=pri_fund_cols,
            primary_benchmark_col=pri_bench_col,
            secondary_df=secondary_df if secondary_data_available else None,
            secondary_fund_cols=sec_fund_cols if secondary_data_available else None,
            secondary_benchmark_col=sec_bench_col if secondary_data_available else None,
            secondary_prefix="S&P ",
        )

        # --- Handle Empty Metrics Result ---
        missing_latest = pd.DataFrame()  # Initialize
        if latest_metrics.empty:
            current_app.logger.warning(
                f"Warning: Metric calculation returned empty DataFrame for {metric_name}. Rendering page with no fund data."
            )
            # Still need to prepare basic JSON payload for the template structure
            json_payload = {
                "metadata": {
                    "metric_name": metric_name,
                    "latest_date": latest_date_str,
                    "fund_col_names": pri_fund_cols or [],
                    "benchmark_col_name": pri_bench_col,
                    "secondary_fund_col_names": (
                        sec_fund_cols if secondary_data_available else []
                    ),
                    "secondary_benchmark_col_name": (
                        sec_bench_col if secondary_data_available else None
                    ),
                    "secondary_data_available": secondary_data_available,
                },
                "funds": {},
            }
            return render_template(
                "metric_page_js.html",
                metric_name=metric_name,
                metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
                charts_data_json=jsonify(json_payload).get_data(as_text=True),
                latest_date=(
                    latest_date_overall.strftime("%d/%m/%Y")
                    if pd.notna(latest_date_overall)
                    else "N/A"
                ),
                missing_funds=missing_latest,  # Empty DF
                sp_valid_state=filter_sp_valid,  # Pass filter state
                secondary_data_initially_available=secondary_data_available,  # Pass initial availability for JS
                fund_groups=filtered_fund_groups_for_dropdown,
                selected_fund_group=selected_fund_group,
                error_message="Warning: No metrics could be calculated, possibly due to filtering.",
            )  # Provide a message

        # --- Identify Missing Funds ---
        current_app.logger.info(
            f"Identifying potentially missing latest data for {metric_name}..."
        )
        primary_cols_for_check = []
        if pri_bench_col:
            primary_cols_for_check.append(pri_bench_col)
        if pri_fund_cols:
            primary_cols_for_check.extend(pri_fund_cols)

        primary_z_score_cols = [
            f"{col} Change Z-Score"
            for col in primary_cols_for_check
            if f"{col} Change Z-Score" in latest_metrics.columns
        ]
        primary_latest_val_cols = [
            f"{col} Latest Value"
            for col in primary_cols_for_check
            if f"{col} Latest Value" in latest_metrics.columns
        ]

        check_cols_for_missing = (
            primary_z_score_cols if primary_z_score_cols else primary_latest_val_cols
        )

        if check_cols_for_missing:
            # Check for NaN in *any* of the critical columns for a given fund
            missing_latest = latest_metrics[
                latest_metrics[check_cols_for_missing].isna().any(axis=1)
            ]
            if not missing_latest.empty:
                current_app.logger.info(
                    f"Found {len(missing_latest)} funds with missing latest data based on columns: {check_cols_for_missing}"
                )
        else:
            current_app.logger.warning(
                f"Warning: No primary Z-Score or Latest Value columns found for {metric_name} to check for missing data."
            )
            missing_latest = pd.DataFrame(
                index=latest_metrics.index
            )  # Assume none missing

        # --- Prepare Data Structure for JavaScript ---
        current_app.logger.info(
            f"Preparing chart and metric data for JavaScript for {metric_name}..."
        )
        funds_data_for_js = {}
        fund_codes_in_metrics = latest_metrics.index
        primary_df_index = primary_df.index if primary_df is not None else None
        secondary_df_index = (
            secondary_df.index
            if secondary_data_available and secondary_df is not None
            else None
        )

        data_folder = current_app.config["DATA_FOLDER"]
        dates_file_path = os.path.join(data_folder, "Dates.csv")
        full_date_list = read_and_sort_dates(dates_file_path) or []
        # Filter to business days (Mon-Fri) and exclude UK bank holidays from holidays.csv
        full_date_list = filter_business_dates(full_date_list, data_folder)
        full_date_list_dt = pd.to_datetime(full_date_list, errors="coerce").dropna()

        for fund_code in fund_codes_in_metrics:
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            is_missing_latest = fund_code in missing_latest.index
            fund_charts = []  # Initialize list to hold chart configs for this fund

            primary_labels = full_date_list  # Already filtered business dates
            primary_dt_index = full_date_list_dt  # Use datetime for reindexing
            fund_hist_primary = None
            relative_primary_hist = None
            relative_secondary_hist = None  # Initialize

            # --- Get Primary Historical Data ---
            if (
                primary_df_index is not None
                and "Code" in primary_df_index.names
                and fund_code in primary_df_index.get_level_values("Code")
            ):
                fund_hist_primary_raw = primary_df.xs(
                    fund_code, level="Code"
                ).sort_index()
                # Ensure index is DatetimeIndex before reindexing
                if isinstance(fund_hist_primary_raw.index, pd.DatetimeIndex):
                    # Reindex to full_date_list_dt, fill method can be added if needed (e.g., ffill)
                    fund_hist_primary = fund_hist_primary_raw.reindex(primary_dt_index)
                else:
                    current_app.logger.warning(
                        f"Warning: Primary index for {fund_code} is not DatetimeIndex. Attempting conversion."
                    )
                    try:
                        fund_hist_primary_raw.index = pd.to_datetime(
                            fund_hist_primary_raw.index
                        )
                        fund_hist_primary = fund_hist_primary_raw.reindex(
                            primary_dt_index
                        )
                    except Exception as dt_err:
                        current_app.logger.error(
                            f"Error converting primary index for {fund_code} to DatetimeIndex: {dt_err}. Cannot reindex."
                        )
                        fund_hist_primary = fund_hist_primary_raw  # Use as is, chart might be incomplete

            # --- Get Secondary Historical Data ---
            fund_hist_secondary = None
            if (
                secondary_data_available
                and secondary_df_index is not None
                and "Code" in secondary_df_index.names
                and fund_code in secondary_df_index.get_level_values("Code")
            ):
                fund_hist_secondary_raw = secondary_df.xs(
                    fund_code, level="Code"
                ).sort_index()
                if isinstance(fund_hist_secondary_raw.index, pd.DatetimeIndex):
                    fund_hist_secondary = fund_hist_secondary_raw.reindex(
                        primary_dt_index
                    )
                else:
                    current_app.logger.warning(
                        f"Warning: Secondary index for {fund_code} is not DatetimeIndex. Attempting conversion."
                    )
                    try:
                        fund_hist_secondary_raw.index = pd.to_datetime(
                            fund_hist_secondary_raw.index
                        )
                        fund_hist_secondary = fund_hist_secondary_raw.reindex(
                            primary_dt_index
                        )
                    except Exception as dt_err:
                        current_app.logger.error(
                            f"Error converting secondary index for {fund_code} to DatetimeIndex: {dt_err}. Cannot reindex."
                        )
                        fund_hist_secondary = fund_hist_secondary_raw  # Use as is

            # --- Prepare Main Chart Datasets (Primary Data) ---
            main_datasets = []
            if fund_hist_primary is not None:
                # Add primary fund column(s)
                if pri_fund_cols:
                    for i, col in enumerate(pri_fund_cols):
                        if col in fund_hist_primary.columns:
                            main_datasets.append(
                                {
                                    "label": col,
                                    "data": make_json_safe(
                                        fund_hist_primary[col].tolist()
                                    ),  # Use helper
                                    "borderColor": COLOR_PALETTE[
                                        i % len(COLOR_PALETTE)
                                    ],
                                    "backgroundColor": f"{COLOR_PALETTE[i % len(COLOR_PALETTE)]}40",  # Add alpha
                                    "tension": 0.1,
                                    "source": "primary",
                                    "isSpData": False,
                                }
                            )
                # Add primary benchmark column
                if pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                    main_datasets.append(
                        {
                            "label": "Benchmark",
                            "data": make_json_safe(
                                fund_hist_primary[pri_bench_col].tolist()
                            ),  # Use helper
                            "borderColor": "black",
                            "backgroundColor": "grey",
                            "borderDash": [5, 5],
                            "tension": 0.1,
                            "source": "primary",
                            "isSpData": False,
                        }
                    )

            # --- Add Secondary Data to Main Chart Datasets ---
            if secondary_data_available and fund_hist_secondary is not None:
                # Add secondary fund column(s) - Use same color but different style
                if sec_fund_cols:
                    for i, col in enumerate(sec_fund_cols):
                        if col in fund_hist_secondary.columns:
                            main_datasets.append(
                                {
                                    "label": f"S&P {col}",  # Prefix with S&P
                                    "data": make_json_safe(
                                        fund_hist_secondary[col].tolist()
                                    ),  # Use helper
                                    "borderColor": COLOR_PALETTE[
                                        i % len(COLOR_PALETTE)
                                    ],  # Same base color
                                    "backgroundColor": f"{COLOR_PALETTE[i % len(COLOR_PALETTE)]}20",  # Lighter alpha
                                    "borderDash": [2, 2],  # Different dash style
                                    "tension": 0.1,
                                    "source": "secondary",
                                    "isSpData": True,  # Mark as SP data
                                }
                            )

                # Add secondary benchmark column
                if sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                    main_datasets.append(
                        {
                            "label": "S&P Benchmark",
                            "data": make_json_safe(
                                fund_hist_secondary[sec_bench_col].tolist()
                            ),  # Use helper
                            "borderColor": "#FFA500",  # Orange for SP Benchmark
                            "backgroundColor": "#FFDAB9",  # Light Orange
                            "borderDash": [2, 2],
                            "tension": 0.1,
                            "source": "secondary",
                            "isSpData": True,  # Mark as SP data
                        }
                    )

            # --- Prepare Relative Chart Data (if possible) ---
            relative_datasets = []
            relative_chart_config = None
            relative_metrics_for_js = {}

            # 1. Calculate Primary Relative Series
            pri_fund_col_used = None
            if fund_hist_primary is not None and pri_fund_cols:
                pri_fund_col_used = pri_fund_cols[
                    0
                ]  # Use the first primary column for relative calc

            if (
                pri_fund_col_used
                and pri_bench_col
                and pri_bench_col in fund_hist_primary.columns
            ):
                port_col_hist = fund_hist_primary[pri_fund_col_used]
                bench_col_hist = fund_hist_primary[pri_bench_col]
                if (
                    not port_col_hist.dropna().empty
                    and not bench_col_hist.dropna().empty
                ):
                    relative_primary_hist = (port_col_hist - bench_col_hist).round(3)
                    relative_datasets.append(
                        {
                            "label": "Relative (Port - Bench)",
                            "data": make_json_safe(
                                relative_primary_hist.tolist()
                            ),  # Use helper
                            "borderColor": "#1f77b4",  # Specific color for primary relative
                            "backgroundColor": "#aec7e8",
                            "tension": 0.1,
                            "source": "primary_relative",
                            "isSpData": False,
                        }
                    )
                    # Extract primary relative metrics
                    for col in fund_latest_metrics_row.index:
                        if col.startswith("Relative "):
                            relative_metrics_for_js[col] = make_json_safe(
                                fund_latest_metrics_row[col]
                            )  # Use helper

            # 2. Calculate Secondary Relative Series (if applicable)
            sec_fund_col_used = None
            if (
                secondary_data_available
                and fund_hist_secondary is not None
                and sec_fund_cols
            ):
                sec_fund_col_used = sec_fund_cols[0]  # Use first secondary column

            if (
                sec_fund_col_used
                and sec_bench_col
                and sec_bench_col in fund_hist_secondary.columns
            ):
                port_col_hist_sec = fund_hist_secondary[sec_fund_col_used]
                bench_col_hist_sec = fund_hist_secondary[sec_bench_col]
                # Check if S&P Relative metrics exist, indicating calculation happened
                if (
                    f"S&P Relative Change Z-Score" in fund_latest_metrics_row.index
                    and pd.notna(
                        fund_latest_metrics_row[f"S&P Relative Change Z-Score"]
                    )
                ):
                    if (
                        not port_col_hist_sec.dropna().empty
                        and not bench_col_hist_sec.dropna().empty
                    ):
                        relative_secondary_hist = (
                            port_col_hist_sec - bench_col_hist_sec
                        ).round(3)
                        relative_datasets.append(
                            {
                                "label": "S&P Relative (Port - Bench)",
                                "data": make_json_safe(
                                    relative_secondary_hist.tolist()
                                ),  # Use helper
                                "borderColor": "#ff7f0e",  # Specific color for secondary relative
                                "backgroundColor": "#ffbb78",
                                "borderDash": [2, 2],
                                "tension": 0.1,
                                "source": "secondary_relative",
                                "isSpData": True,
                                "hidden": True,  # Initially hidden
                            }
                        )
                        # Extract secondary relative metrics
                        for col in fund_latest_metrics_row.index:
                            if col.startswith("S&P Relative "):
                                relative_metrics_for_js[col] = make_json_safe(
                                    fund_latest_metrics_row[col]
                                )  # Use helper

            # 3. Create Relative Chart Config if primary relative data exists
            if relative_primary_hist is not None and not relative_primary_hist.empty:
                relative_chart_config = {
                    "chart_type": "relative",
                    "title": f"{fund_code} - Relative ({metric_name})",
                    "labels": primary_labels,
                    "datasets": relative_datasets,
                    "latest_metrics": make_json_safe(
                        relative_metrics_for_js
                    ),  # Use helper
                }

            # --- Prepare Main Chart Config ---
            main_chart_config = None
            if main_datasets:  # Only create if there's actual data
                main_chart_config = {
                    "chart_type": "main",
                    "title": f"{fund_code} - {metric_name}",
                    "labels": primary_labels,  # Business-day filtered
                    "datasets": main_datasets,  # Already JSON safe from above
                    "latest_metrics": make_json_safe(
                        fund_latest_metrics_row.to_dict()
                    ),  # Use helper
                }
                # Add main chart FIRST
                fund_charts.append(main_chart_config)

            # Now add the relative chart config if it exists
            if relative_chart_config:
                fund_charts.append(relative_chart_config)

            # --- Store Fund Data ---
            # Ensure all values in latest_metrics_raw are JSON-safe
            safe_latest_metrics_raw = make_json_safe(fund_latest_metrics_row.to_dict())
            funds_data_for_js[fund_code] = {
                # 'latest_metrics_html': "<td>Placeholder</td>", # Remove if not used
                "latest_metrics_raw": safe_latest_metrics_raw,  # Use safe dict
                "charts": fund_charts,  # Already JSON safe from above
                "is_missing_latest": is_missing_latest,
                "max_abs_z": (
                    make_json_safe(
                        fund_latest_metrics_row.filter(like="Z-Score").abs().max()
                    )
                    if hasattr(fund_latest_metrics_row.filter(like="Z-Score"), "abs")
                    else None
                ),
            }

        # --- Final JSON Payload Preparation ---
        json_payload = {
            "metadata": {
                "metric_name": metric_name,
                "latest_date": latest_date_str,
                "fund_col_names": pri_fund_cols or [],
                "benchmark_col_name": pri_bench_col,
                "secondary_fund_col_names": (
                    sec_fund_cols if secondary_data_available else []
                ),
                "secondary_benchmark_col_name": (
                    sec_bench_col if secondary_data_available else None
                ),
                "secondary_data_available": secondary_data_available,
            },
            "funds": funds_data_for_js,  # Already made safe inside loop
        }
        # Final check for safety, although internal loops should handle most
        json_payload = make_json_safe(json_payload)

        # --- Render Template ---
        current_app.logger.info(
            f"Rendering template for {metric_name} with filter_sp_valid={filter_sp_valid}, Group={selected_fund_group}"
        )
        return render_template(
            "metric_page_js.html",
            metric_name=metric_name,
            metric_display_name=metric_cfg["display_name"],  # Pass the display name from config
            charts_data_json=jsonify(json_payload).get_data(
                as_text=True
            ),  # jsonify handles final conversion
            latest_date=(
                latest_date_overall.strftime("%d/%m/%Y")
                if pd.notna(latest_date_overall)
                else "N/A"
            ),
            missing_funds=missing_latest,
            sp_valid_state=filter_sp_valid,  # Pass filter state
            secondary_data_initially_available=secondary_data_available,  # Pass initial availability for JS logic
            error_message=error_message,  # Pass potential error message
            fund_groups=filtered_fund_groups_for_dropdown,  # Pass available groups for UI dropdown
            selected_fund_group=selected_fund_group,  # Pass selected group for UI state
        )

    except FileNotFoundError as e:
        current_app.logger.error(
            f"Error: File not found during processing for {metric_name}. Details: {e}"
        )
        traceback.print_exc()
        error_message = (
            f"Error: Required data file not found for metric '{metric_name}'. {e}"
        )
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get("sp_valid", "true").lower()
        filter_sp_valid_except = sp_valid_param_except == "true"
        selected_fund_group_except = request.args.get("fund_group", None)
        # Attempt to load fund groups even in error for the dropdown
        fund_groups_except = {}
        try:
            data_folder_except = current_app.config["DATA_FOLDER"]
            fund_groups_except = load_fund_groups(data_folder_except)
        except Exception as fg_err:
            current_app.logger.error(
                f"Could not load fund groups during exception handling: {fg_err}"
            )
        return (
            render_template(
                "metric_page_js.html",
                metric_name=metric_name,
                metric_display_name=metric_name.replace('_', ' ').title(),  # Fallback display name
                charts_data_json="{}",
                latest_date="N/A",
                missing_funds=pd.DataFrame(),
                sp_valid_state=filter_sp_valid_except,
                secondary_data_initially_available=False,
                error_message=error_message,
                fund_groups=fund_groups_except,
                selected_fund_group=selected_fund_group_except,
            ),
            404,
        )

    except Exception as e:
        current_app.logger.error(
            f"Unexpected error processing metric {metric_name}: {e}\n{traceback.format_exc()}"
        )
        error_message = f"An unexpected error occurred while processing metric '{metric_name}'. Please check the logs for details."
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get("sp_valid", "true").lower()
        filter_sp_valid_except = sp_valid_param_except == "true"
        selected_fund_group_except = request.args.get("fund_group", None)
        # Attempt to load fund groups even in error for the dropdown
        fund_groups_except = {}
        try:
            data_folder_except = current_app.config["DATA_FOLDER"]
            fund_groups_except = load_fund_groups(data_folder_except)
        except Exception as fg_err:
            current_app.logger.error(
                f"Could not load fund groups during exception handling: {fg_err}"
            )
        return (
            render_template(
                "metric_page_js.html",
                metric_name=metric_name,
                metric_display_name=metric_name.replace('_', ' ').title(),  # Fallback display name
                charts_data_json="{}",
                latest_date="N/A",
                missing_funds=pd.DataFrame(),
                sp_valid_state=filter_sp_valid_except,
                secondary_data_initially_available=False,
                error_message=error_message,
                fund_groups=fund_groups_except,
                selected_fund_group=selected_fund_group_except,
            ),
            500,
        )


# Inspect feature routes and helper functions have been relocated to
# views/inspect_views.py under the `inspect_bp` blueprint.
