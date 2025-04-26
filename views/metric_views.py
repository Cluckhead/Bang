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
from flask import Blueprint, render_template, jsonify, current_app, request # Added request
import os
import pandas as pd
import numpy as np
import traceback
import math
from datetime import datetime # Added for inspect route date parsing

# Import necessary functions/constants from other modules
from config import COLOR_PALETTE
# Make sure load_and_process_data and other loaders can handle security-level data if needed
from data_loader import load_and_process_data, LoadResult, load_simple_csv
from metric_calculator import calculate_latest_metrics
from process_data import read_and_sort_dates
from utils import get_data_folder_path, load_fund_groups

# Define the blueprint for metric routes, using '/metric' as the URL prefix
metric_bp = Blueprint('metric', __name__, url_prefix='/metric')

# Helper function to safely convert values to JSON serializable types
def make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None # Convert NaN/inf to None for JSON
        return obj
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj) # Convert numpy integers
    elif isinstance(obj, (np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj) # Convert numpy floats
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat() # Convert Timestamps
    return obj

@metric_bp.route('/<string:metric_name>')
def metric_page(metric_name):
    """Renders the detailed page (`metric_page_js.html`) for a specific metric. X-axis always uses Dates.csv.
    Adds support for filtering by fund group (from FundGroups.csv)."""
    primary_filename = f"ts_{metric_name}.csv"
    secondary_filename = f"sp_{primary_filename}"
    fund_code = 'N/A' # Default for logging fallback in case of early error
    latest_date_overall = pd.Timestamp.min # Initialize
    error_message = None # Initialize error message

    try:
        # --- Get Filter State from Query Parameter ---
        sp_valid_param = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid = sp_valid_param == 'true'
        # --- Fund Group Filter: get from query param ---
        selected_fund_group = request.args.get('fund_group', None)
        current_app.logger.info(f"--- Processing metric: {metric_name}, S&P Valid Filter: {filter_sp_valid}, Selected Fund Group: {selected_fund_group} ---")
        current_app.logger.info(f"URL Query Params: {request.args}") # Log query params for debugging

        # --- Load Data (Primary and Secondary) with Filtering ---
        current_app.logger.info(f"Loading data: Primary='{primary_filename}', Secondary='{secondary_filename}', Filter='{filter_sp_valid}'")
        load_result: LoadResult = load_and_process_data(
            primary_filename=primary_filename,
            secondary_filename=secondary_filename,
            filter_sp_valid=filter_sp_valid # Pass the filter flag
        )
        primary_df, pri_fund_cols, pri_bench_col, secondary_df, sec_fund_cols, sec_bench_col = load_result

        # --- Fund Group Filtering: Apply to DataFrames Before Metrics ---
        data_folder = current_app.config['DATA_FOLDER']
        fund_groups_dict = load_fund_groups(data_folder)
        # Filter the groups dictionary first based on the currently loaded funds
        all_funds_in_data_primary = set(primary_df.index.get_level_values('Code')) if primary_df is not None and 'Code' in primary_df.index.names else set()
        all_funds_in_data_secondary = set(secondary_df.index.get_level_values('Code')) if secondary_df is not None and 'Code' in secondary_df.index.names else set()
        all_funds_in_data = all_funds_in_data_primary.union(all_funds_in_data_secondary)

        filtered_fund_groups_for_dropdown = {g: [f for f in funds if f in all_funds_in_data] for g, funds in fund_groups_dict.items()}
        filtered_fund_groups_for_dropdown = {g: funds for g, funds in filtered_fund_groups_for_dropdown.items() if funds} # Remove empty groups

        if selected_fund_group and selected_fund_group in filtered_fund_groups_for_dropdown: # Use the filtered list for checking validity
            current_app.logger.info(f"Applying fund group filter: {selected_fund_group}")
            allowed_funds = set(filtered_fund_groups_for_dropdown[selected_fund_group])
            # Filter primary_df and secondary_df to only include allowed funds
            if primary_df is not None and not primary_df.empty:
                idx_names = list(primary_df.index.names)
                if 'Code' in idx_names:
                    primary_df = primary_df[primary_df.index.get_level_values('Code').isin(allowed_funds)]
                    pri_fund_cols = [col for col in pri_fund_cols if col in primary_df.columns] # Update fund cols if some were dropped
            if secondary_df is not None and not secondary_df.empty:
                idx_names = list(secondary_df.index.names)
                if 'Code' in idx_names:
                    secondary_df = secondary_df[secondary_df.index.get_level_values('Code').isin(allowed_funds)]
                    sec_fund_cols = [col for col in sec_fund_cols if col in secondary_df.columns] # Update fund cols
        elif selected_fund_group:
            current_app.logger.warning(f"Selected fund group '{selected_fund_group}' not found in available groups for this data or is empty. Ignoring filter.")
            selected_fund_group = None # Reset if invalid

        # --- Validate Primary Data (Post-Filtering) ---
        if primary_df is None or primary_df.empty:
            data_folder_for_error = current_app.config['DATA_FOLDER']
            primary_filepath = os.path.join(data_folder_for_error, primary_filename)
            if not os.path.exists(primary_filepath):
                 current_app.logger.error(f"Error: Primary data file not found: {primary_filepath} (Filter: {filter_sp_valid}, Group: {selected_fund_group})")
                 error_message = f"Error: Data file for metric '{metric_name}' (expected: '{primary_filename}') not found."
                 # Render template with error message and filter state
                 return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}', # Empty data
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(), # Empty dataframe
                               sp_valid_state=filter_sp_valid, # Pass filter state
                               secondary_data_initially_available=False,
                               fund_groups=filtered_fund_groups_for_dropdown,
                               selected_fund_group=selected_fund_group,
                               error_message=error_message), 404
            else:
                 current_app.logger.error(f"Error: Failed to process primary data file '{primary_filename}' or file became empty after filtering (Filter: {filter_sp_valid}, Group: {selected_fund_group}).")
                 # Construct error message piece by piece
                 error_message_base = f"Error: Could not process required data for metric '{metric_name}' (file: '{primary_filename}')."
                 error_details = []
                 if filter_sp_valid:
                     error_details.append("The data might be missing, empty, or contain no rows marked as 'TRUE' in 'SS Project - In Scope' when the S&P Valid filter is ON.")
                 if selected_fund_group:
                    error_details.append(f"Or no data was found for the selected fund group '{selected_fund_group}'.")
                 if not error_details: # If no specific filter reason, add generic one
                      error_details.append("Check file format or logs.")
                 error_message = f"{error_message_base} {' '.join(error_details)}"
                 # Render template with error message and filter state
                 return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               fund_groups=filtered_fund_groups_for_dropdown,
                               selected_fund_group=selected_fund_group,
                               error_message=error_message), 500

        # Add check for pri_fund_cols after ensuring primary_df is not None
        if not pri_fund_cols: # Check if list is empty after potential filtering
            current_app.logger.error(f"Error: Could not identify primary fund value columns in '{primary_filename}' after loading and filtering.")
            error_message = f"Error: Failed to identify fund value columns in '{primary_filename}' after filtering. Check file structure or filter criteria."
            return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               fund_groups=filtered_fund_groups_for_dropdown,
                               selected_fund_group=selected_fund_group,
                               error_message=error_message), 500

        # --- Determine Combined Metadata (Post-Filtering) ---
        all_dfs_for_meta = [df for df in [primary_df, secondary_df] if df is not None and not df.empty]
        if not all_dfs_for_meta:
            current_app.logger.error(f"Error: No valid data loaded for {metric_name} (Filter: {filter_sp_valid}, Group: {selected_fund_group})")
            error_message = f"Error: No data found for metric '{metric_name}' (Filter Applied: {filter_sp_valid}, Group: {selected_fund_group})."
            return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               fund_groups=filtered_fund_groups_for_dropdown,
                               selected_fund_group=selected_fund_group,
                               error_message=error_message), 404

        # --- Calculate Latest Date Overall ---
        try:
            # Combine indices only from non-empty DataFrames that exist
            combined_index = pd.concat([df.index for df in all_dfs_for_meta])
            latest_date_overall = combined_index.get_level_values(0).max()
            latest_date_str = latest_date_overall.strftime('%Y-%m-%d') if pd.notna(latest_date_overall) else "N/A"
        except Exception as idx_err:
            current_app.logger.error(f"Error combining indices or getting latest date for {metric_name}: {idx_err}")
            # Fallback to primary df if it exists
            if primary_df is not None and not primary_df.empty:
                try:
                    # Attempt to get date from primary_df
                    latest_date_overall = primary_df.index.get_level_values(0).max()
                    latest_date_str = latest_date_overall.strftime('%Y-%m-%d') if pd.notna(latest_date_overall) else "N/A"
                    current_app.logger.warning(f"Warning: Using latest date from primary data only: {latest_date_str}")
                except Exception as fallback_err:
                    # Handle error if even primary_df fails
                    current_app.logger.error(f"Error getting latest date even from primary_df: {fallback_err}")
                    latest_date_overall = pd.Timestamp.min # Reset to avoid downstream errors
                    latest_date_str = "N/A"
            else:
                # Handle case where primary_df was None or empty initially
                current_app.logger.error("Could not determine latest date from any available data (primary_df was None or empty).")
                latest_date_overall = pd.Timestamp.min # Reset to avoid downstream errors
                latest_date_str = "N/A"

        # --- Check Secondary Data Availability (Post-Filtering)---
        secondary_data_available = secondary_df is not None and not secondary_df.empty and sec_fund_cols is not None and sec_fund_cols
        current_app.logger.info(f"Secondary data available for {metric_name} (post-filter): {secondary_data_available}")

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
            secondary_prefix="S&P "
        )

        # --- Handle Empty Metrics Result --- 
        missing_latest = pd.DataFrame() # Initialize
        if latest_metrics.empty:
            current_app.logger.warning(f"Warning: Metric calculation returned empty DataFrame for {metric_name}. Rendering page with no fund data.")
            # Still need to prepare basic JSON payload for the template structure
            json_payload = {
                "metadata": {
                    "metric_name": metric_name,
                    "latest_date": latest_date_str,
                    "fund_col_names": pri_fund_cols or [],
                    "benchmark_col_name": pri_bench_col,
                    "secondary_fund_col_names": sec_fund_cols if secondary_data_available else [],
                    "secondary_benchmark_col_name": sec_bench_col if secondary_data_available else None,
                    "secondary_data_available": secondary_data_available
                },
                "funds": {}
            }
            return render_template('metric_page_js.html',
                           metric_name=metric_name,
                           charts_data_json=jsonify(json_payload).get_data(as_text=True),
                           latest_date=latest_date_overall.strftime('%d/%m/%Y') if pd.notna(latest_date_overall) else "N/A",
                           missing_funds=missing_latest, # Empty DF
                           sp_valid_state=filter_sp_valid, # Pass filter state
                           secondary_data_initially_available=secondary_data_available, # Pass initial availability for JS
                           fund_groups=filtered_fund_groups_for_dropdown,
                           selected_fund_group=selected_fund_group,
                           error_message="Warning: No metrics could be calculated, possibly due to filtering.") # Provide a message

        # --- Identify Missing Funds --- 
        current_app.logger.info(f"Identifying potentially missing latest data for {metric_name}...")
        primary_cols_for_check = []
        if pri_bench_col:
            primary_cols_for_check.append(pri_bench_col)
        if pri_fund_cols:
            primary_cols_for_check.extend(pri_fund_cols)
        
        primary_z_score_cols = [f'{col} Change Z-Score' for col in primary_cols_for_check 
                                if f'{col} Change Z-Score' in latest_metrics.columns]
        primary_latest_val_cols = [f'{col} Latest Value' for col in primary_cols_for_check
                                   if f'{col} Latest Value' in latest_metrics.columns]
        
        check_cols_for_missing = primary_z_score_cols if primary_z_score_cols else primary_latest_val_cols
        
        if check_cols_for_missing:
            # Check for NaN in *any* of the critical columns for a given fund
            missing_latest = latest_metrics[latest_metrics[check_cols_for_missing].isna().any(axis=1)]
            if not missing_latest.empty:
                 current_app.logger.info(f"Found {len(missing_latest)} funds with missing latest data based on columns: {check_cols_for_missing}")
        else:
            current_app.logger.warning(f"Warning: No primary Z-Score or Latest Value columns found for {metric_name} to check for missing data.")
            missing_latest = pd.DataFrame(index=latest_metrics.index) # Assume none missing

        # --- Prepare Data Structure for JavaScript --- 
        current_app.logger.info(f"Preparing chart and metric data for JavaScript for {metric_name}...")
        funds_data_for_js = {}
        fund_codes_in_metrics = latest_metrics.index
        primary_df_index = primary_df.index if primary_df is not None else None
        secondary_df_index = secondary_df.index if secondary_data_available and secondary_df is not None else None
             
        data_folder = current_app.config['DATA_FOLDER']
        dates_file_path = os.path.join(data_folder, 'Dates.csv')
        full_date_list = read_and_sort_dates(dates_file_path) or []
        full_date_list_dt = pd.to_datetime(full_date_list, errors='coerce').dropna() # Convert to datetime for reindexing

        for fund_code in fund_codes_in_metrics:
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            is_missing_latest = fund_code in missing_latest.index
            fund_charts = [] # Initialize list to hold chart configs for this fund

            primary_labels = full_date_list # Use original string dates for labels
            primary_dt_index = full_date_list_dt # Use datetime for reindexing
            fund_hist_primary = None
            relative_primary_hist = None
            relative_secondary_hist = None # Initialize

            # --- Get Primary Historical Data ---
            if primary_df_index is not None and 'Code' in primary_df_index.names and fund_code in primary_df_index.get_level_values('Code'):
                fund_hist_primary_raw = primary_df.xs(fund_code, level='Code').sort_index()
                # Ensure index is DatetimeIndex before reindexing
                if isinstance(fund_hist_primary_raw.index, pd.DatetimeIndex):
                    # Reindex to full_date_list_dt, fill method can be added if needed (e.g., ffill)
                    fund_hist_primary = fund_hist_primary_raw.reindex(primary_dt_index)
                else:
                    current_app.logger.warning(f"Warning: Primary index for {fund_code} is not DatetimeIndex. Attempting conversion.")
                    try:
                        fund_hist_primary_raw.index = pd.to_datetime(fund_hist_primary_raw.index)
                        fund_hist_primary = fund_hist_primary_raw.reindex(primary_dt_index)
                    except Exception as dt_err:
                         current_app.logger.error(f"Error converting primary index for {fund_code} to DatetimeIndex: {dt_err}. Cannot reindex.")
                         fund_hist_primary = fund_hist_primary_raw # Use as is, chart might be incomplete

            # --- Get Secondary Historical Data ---
            fund_hist_secondary = None
            if secondary_data_available and secondary_df_index is not None and 'Code' in secondary_df_index.names and fund_code in secondary_df_index.get_level_values('Code'):
                fund_hist_secondary_raw = secondary_df.xs(fund_code, level='Code').sort_index()
                if isinstance(fund_hist_secondary_raw.index, pd.DatetimeIndex):
                    fund_hist_secondary = fund_hist_secondary_raw.reindex(primary_dt_index)
                else:
                    current_app.logger.warning(f"Warning: Secondary index for {fund_code} is not DatetimeIndex. Attempting conversion.")
                    try:
                         fund_hist_secondary_raw.index = pd.to_datetime(fund_hist_secondary_raw.index)
                         fund_hist_secondary = fund_hist_secondary_raw.reindex(primary_dt_index)
                    except Exception as dt_err:
                         current_app.logger.error(f"Error converting secondary index for {fund_code} to DatetimeIndex: {dt_err}. Cannot reindex.")
                         fund_hist_secondary = fund_hist_secondary_raw # Use as is

            # --- Prepare Main Chart Datasets (Primary Data) ---
            main_datasets = []
            if fund_hist_primary is not None:
                # Add primary fund column(s)
                if pri_fund_cols:
                    for i, col in enumerate(pri_fund_cols):
                        if col in fund_hist_primary.columns:
                            main_datasets.append({
                                "label": col,
                                "data": make_json_safe(fund_hist_primary[col].tolist()), # Use helper
                                "borderColor": COLOR_PALETTE[i % len(COLOR_PALETTE)],
                                "backgroundColor": f"{COLOR_PALETTE[i % len(COLOR_PALETTE)]}40", # Add alpha
                                "tension": 0.1,
                                "source": "primary",
                                "isSpData": False
                            })
                # Add primary benchmark column
                if pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                    main_datasets.append({
                        "label": "Benchmark",
                        "data": make_json_safe(fund_hist_primary[pri_bench_col].tolist()), # Use helper
                        "borderColor": "black",
                        "backgroundColor": "grey",
                        "borderDash": [5, 5],
                        "tension": 0.1,
                        "source": "primary",
                        "isSpData": False
                    })

            # --- Add Secondary Data to Main Chart Datasets ---
            if secondary_data_available and fund_hist_secondary is not None:
                 # Add secondary fund column(s) - Use same color but different style
                if sec_fund_cols:
                    for i, col in enumerate(sec_fund_cols):
                        if col in fund_hist_secondary.columns:
                             main_datasets.append({
                                "label": f"S&P {col}", # Prefix with S&P
                                "data": make_json_safe(fund_hist_secondary[col].tolist()), # Use helper
                                "borderColor": COLOR_PALETTE[i % len(COLOR_PALETTE)], # Same base color
                                "backgroundColor": f"{COLOR_PALETTE[i % len(COLOR_PALETTE)]}20", # Lighter alpha
                                "borderDash": [2, 2], # Different dash style
                                "tension": 0.1,
                                "source": "secondary",
                                "isSpData": True # Mark as SP data
                            })

                # Add secondary benchmark column
                if sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                    main_datasets.append({
                        "label": "S&P Benchmark",
                        "data": make_json_safe(fund_hist_secondary[sec_bench_col].tolist()), # Use helper
                        "borderColor": "#FFA500", # Orange for SP Benchmark
                        "backgroundColor": "#FFDAB9", # Light Orange
                        "borderDash": [2, 2],
                        "tension": 0.1,
                        "source": "secondary",
                        "isSpData": True # Mark as SP data
                    })

            # --- Prepare Relative Chart Data (if possible) ---
            relative_datasets = []
            relative_chart_config = None
            relative_metrics_for_js = {}

            # 1. Calculate Primary Relative Series
            pri_fund_col_used = None
            if fund_hist_primary is not None and pri_fund_cols:
                pri_fund_col_used = pri_fund_cols[0] # Use the first primary column for relative calc

            if pri_fund_col_used and pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                port_col_hist = fund_hist_primary[pri_fund_col_used]
                bench_col_hist = fund_hist_primary[pri_bench_col]
                if not port_col_hist.dropna().empty and not bench_col_hist.dropna().empty:
                    relative_primary_hist = (port_col_hist - bench_col_hist).round(3)
                    relative_datasets.append({
                        'label': 'Relative (Port - Bench)',
                        'data': make_json_safe(relative_primary_hist.tolist()), # Use helper
                        'borderColor': '#1f77b4', # Specific color for primary relative
                        'backgroundColor': '#aec7e8',
                        'tension': 0.1,
                        'source': 'primary_relative',
                        'isSpData': False
                    })
                    # Extract primary relative metrics
                    for col in fund_latest_metrics_row.index:
                        if col.startswith('Relative '):
                             relative_metrics_for_js[col] = make_json_safe(fund_latest_metrics_row[col]) # Use helper

            # 2. Calculate Secondary Relative Series (if applicable)
            sec_fund_col_used = None
            if secondary_data_available and fund_hist_secondary is not None and sec_fund_cols:
                 sec_fund_col_used = sec_fund_cols[0] # Use first secondary column

            if sec_fund_col_used and sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                port_col_hist_sec = fund_hist_secondary[sec_fund_col_used]
                bench_col_hist_sec = fund_hist_secondary[sec_bench_col]
                # Check if S&P Relative metrics exist, indicating calculation happened
                if f'S&P Relative Change Z-Score' in fund_latest_metrics_row.index and pd.notna(fund_latest_metrics_row[f'S&P Relative Change Z-Score']):
                    if not port_col_hist_sec.dropna().empty and not bench_col_hist_sec.dropna().empty:
                        relative_secondary_hist = (port_col_hist_sec - bench_col_hist_sec).round(3)
                        relative_datasets.append({
                            'label': 'S&P Relative (Port - Bench)',
                            'data': make_json_safe(relative_secondary_hist.tolist()), # Use helper
                            'borderColor': '#ff7f0e', # Specific color for secondary relative
                            'backgroundColor': '#ffbb78',
                            'borderDash': [2, 2],
                            'tension': 0.1,
                            'source': 'secondary_relative',
                            'isSpData': True,
                            'hidden': True # Initially hidden
                        })
                         # Extract secondary relative metrics
                        for col in fund_latest_metrics_row.index:
                            if col.startswith('S&P Relative '):
                                relative_metrics_for_js[col] = make_json_safe(fund_latest_metrics_row[col]) # Use helper

            # 3. Create Relative Chart Config if primary relative data exists
            if relative_primary_hist is not None and not relative_primary_hist.empty:
                relative_chart_config = {
                    'chart_type': 'relative',
                    'title': f'{fund_code} - Relative ({metric_name})',
                    'labels': primary_labels,
                    'datasets': relative_datasets,
                    'latest_metrics': make_json_safe(relative_metrics_for_js) # Use helper
                }

            # --- Prepare Main Chart Config ---
            main_chart_config = None
            if main_datasets: # Only create if there's actual data
                main_chart_config = {
                    'chart_type': 'main',
                    'title': f'{fund_code} - {metric_name}',
                    'labels': primary_labels,
                    'datasets': main_datasets, # Already JSON safe from above
                    'latest_metrics': make_json_safe(fund_latest_metrics_row.to_dict()) # Use helper
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
                'latest_metrics_raw': safe_latest_metrics_raw, # Use safe dict
                'charts': fund_charts, # Already JSON safe from above
                'is_missing_latest': is_missing_latest,
                'max_abs_z': make_json_safe(fund_latest_metrics_row.filter(like='Z-Score').abs().max()) if hasattr(fund_latest_metrics_row.filter(like='Z-Score'), 'abs') else None
            }

        # --- Final JSON Payload Preparation ---
        json_payload = {
            "metadata": {
                "metric_name": metric_name,
                "latest_date": latest_date_str,
                "fund_col_names": pri_fund_cols or [],
                "benchmark_col_name": pri_bench_col,
                "secondary_fund_col_names": sec_fund_cols if secondary_data_available else [],
                "secondary_benchmark_col_name": sec_bench_col if secondary_data_available else None,
                "secondary_data_available": secondary_data_available
            },
            "funds": funds_data_for_js # Already made safe inside loop
        }
        # Final check for safety, although internal loops should handle most
        json_payload = make_json_safe(json_payload)

        # --- Render Template --- 
        current_app.logger.info(f"Rendering template for {metric_name} with filter_sp_valid={filter_sp_valid}, Group={selected_fund_group}")
        return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json=jsonify(json_payload).get_data(as_text=True), # jsonify handles final conversion
                               latest_date=latest_date_overall.strftime('%d/%m/%Y') if pd.notna(latest_date_overall) else "N/A",
                               missing_funds=missing_latest,
                               sp_valid_state=filter_sp_valid, # Pass filter state
                               secondary_data_initially_available=secondary_data_available, # Pass initial availability for JS logic
                               error_message=error_message, # Pass potential error message
                               fund_groups=filtered_fund_groups_for_dropdown, # Pass available groups for UI dropdown
                               selected_fund_group=selected_fund_group # Pass selected group for UI state
                               )

    except FileNotFoundError as e:
        current_app.logger.error(f"Error: File not found during processing for {metric_name}. Details: {e}")
        traceback.print_exc()
        error_message = f"Error: Required data file not found for metric '{metric_name}'. {e}"
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid_except = sp_valid_param_except == 'true'
        selected_fund_group_except = request.args.get('fund_group', None)
        # Attempt to load fund groups even in error for the dropdown
        fund_groups_except = {}
        try:
            data_folder_except = current_app.config['DATA_FOLDER']
            fund_groups_except = load_fund_groups(data_folder_except)
        except Exception as fg_err:
             current_app.logger.error(f"Could not load fund groups during exception handling: {fg_err}")
        return render_template('metric_page_js.html',
                               metric_name=metric_name, charts_data_json='{}', latest_date="N/A",
                               missing_funds=pd.DataFrame(), sp_valid_state=filter_sp_valid_except,
                               secondary_data_initially_available=False, error_message=error_message,
                               fund_groups=fund_groups_except, selected_fund_group=selected_fund_group_except), 404

    except Exception as e:
        current_app.logger.error(f"Unexpected error processing metric {metric_name}: {e}\n{traceback.format_exc()}")
        error_message = f"An unexpected error occurred while processing metric '{metric_name}'. Please check the logs for details."
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid_except = sp_valid_param_except == 'true'
        selected_fund_group_except = request.args.get('fund_group', None)
         # Attempt to load fund groups even in error for the dropdown
        fund_groups_except = {}
        try:
            data_folder_except = current_app.config['DATA_FOLDER']
            fund_groups_except = load_fund_groups(data_folder_except)
        except Exception as fg_err:
             current_app.logger.error(f"Could not load fund groups during exception handling: {fg_err}")
        return render_template('metric_page_js.html',
                               metric_name=metric_name, charts_data_json='{}', latest_date="N/A",
                               missing_funds=pd.DataFrame(), sp_valid_state=filter_sp_valid_except,
                               secondary_data_initially_available=False, error_message=error_message,
                               fund_groups=fund_groups_except, selected_fund_group=selected_fund_group_except), 500

# --- Inspect Feature Routes ---

def _melt_data(df, id_vars, fund_code):
    """Melts the dataframe from wide (dates as columns) to long format.
       Filters by fund_code, handling list-like entries (e.g., [IG01] or ['IG01','IG02']) in 'Funds'.
    """
    if df is None or df.empty:
        current_app.logger.warning(f"[_melt_data] Input DataFrame is None or empty for fund '{fund_code}'.")
        return None

    current_app.logger.debug(f"[_melt_data] Processing for fund '{fund_code}'. Input shape: {df.shape}, Columns: {df.columns.tolist()}")
    current_app.logger.debug(f"[_melt_data] ID Vars: {id_vars}")

    try:
        if 'Funds' not in df.columns:
             current_app.logger.error(f"[_melt_data] Critical Error: 'Funds' column not found in input DataFrame for fund '{fund_code}'. Columns: {df.columns.tolist()}")
             return None

        # --- Robust Fund Filtering Logic --- 
        def check_fund_match(fund_entry, target_fund):
            if pd.isna(fund_entry):
                return False
            # Check if it looks like a list string (e.g., [IG01] or ['IG01'] or [IG01, IG02])
            if isinstance(fund_entry, str) and fund_entry.startswith('[') and fund_entry.endswith(']'):
                # Strip brackets
                content = fund_entry[1:-1].strip()
                if not content: # Handle empty brackets '[]'
                    return False
                # Split by comma, strip whitespace and quotes from each item
                items = [item.strip().strip("'\"") for item in content.split(',')]
                return target_fund in items
            else:
                # Treat as a single value comparison (convert to string for safety)
                return str(fund_entry).strip() == target_fund

        # Apply the checking function
        mask = df['Funds'].apply(lambda x: check_fund_match(x, fund_code))
        df_filtered = df[mask]
        # --- End Fund Filtering Logic --- 
            
    except Exception as e:
        current_app.logger.error(f"[_melt_data] Error processing 'Funds' column during filtering for '{fund_code}': {e}", exc_info=True)
        return None

    current_app.logger.debug(f"[_melt_data] Shape after filtering for '{fund_code}': {df_filtered.shape}")
    if df_filtered.empty:
        current_app.logger.warning(f"[_melt_data] No data found for fund_code '{fund_code}' after filtering.")
        return pd.DataFrame(columns=id_vars + ['Date', 'Value'])

    # --- Identify date columns (rest of the function remains the same) --- 
    date_cols = []
    non_date_cols = []
    for col in df_filtered.columns:
        if col not in id_vars: # No need to check for 'FundsList' anymore
            try:
                pd.to_datetime(col, errors='raise')
                date_cols.append(col)
            except (ValueError, TypeError):
                non_date_cols.append(col)
                continue
                
    current_app.logger.debug(f"[_melt_data] Identified date columns: {date_cols}")
    current_app.logger.debug(f"[_melt_data] Identified non-date columns (excluding ids): {non_date_cols}")

    if not date_cols:
        current_app.logger.error("[_melt_data] Could not identify any date columns for melting.")
        return None

    # --- Melt the filtered dataframe (rest of the function remains the same) --- 
    try:
        current_app.logger.debug(f"[_melt_data] Attempting melt with id_vars={id_vars}, value_vars={date_cols[:5]}...")
        melted_df = df_filtered.melt(
            id_vars=id_vars, # No 'FundsList' helper column needed
            value_vars=date_cols,
            var_name='Date',
            value_name='Value'
        )
        current_app.logger.debug(f"[_melt_data] Melt successful. Shape after melt: {melted_df.shape}")
        
        melted_df['Date'] = pd.to_datetime(melted_df['Date'], errors='coerce')
        melted_df = melted_df.dropna(subset=['Date'])
        current_app.logger.debug(f"[_melt_data] Date conversion done. Shape after dropping NaT dates: {melted_df.shape}")
        return melted_df
    except Exception as melt_err:
        current_app.logger.error(f"[_melt_data] Error melting dataframe: {melt_err}", exc_info=True)
        return None

def _calculate_contributions(metric_name, fund_code, start_date_str, end_date_str, data_source, top_n=10):
    """Helper function to calculate security contributions to a metric's change.

    Args:
        metric_name (str): The name of the metric.
        fund_code (str): The fund code to filter by.
        start_date_str (str): Start date in YYYY-MM-DD format.
        end_date_str (str): End date in YYYY-MM-DD format.
        data_source (str): 'Original' or 'SP'.
        top_n (int): Number of top/bottom contributors to return.

    Returns:
        dict: A dictionary containing the calculated results or an error message.
              Expected keys on success: 'metric_name', 'fund_code', 'start_date', 
              'end_date', 'baseline_date', 'data_source', 'top_contributors', 'top_detractors'.
              Expected keys on error: 'error'.
              
    Raises:
        FileNotFoundError: If a required data file is not found.
        ValueError: For invalid input parameters (dates, etc.).
        KeyError: If expected columns are missing in data files.
        Exception: For other unexpected errors during calculation.
    """
    current_app.logger.info(f"--- Calculating Contributions for {metric_name} ({fund_code}) [{start_date_str} - {end_date_str}], Source: {data_source} ---")
    
    # --- Input Validation & Date Parsing --- 
    if not all([start_date_str, end_date_str, fund_code, metric_name]):
        raise ValueError("Missing required parameters for calculation.")

    start_date = pd.to_datetime(start_date_str, errors='coerce')
    end_date = pd.to_datetime(end_date_str, errors='coerce')
    if pd.isna(start_date) or pd.isna(end_date):
        raise ValueError("Invalid date format. Please use YYYY-MM-DD.")
    if start_date >= end_date:
        raise ValueError("Start date must be before end date.")
    
    baseline_date = start_date - pd.Timedelta(days=1)
    current_app.logger.info(f"Calculation Params: Baseline='{baseline_date.strftime('%Y-%m-%d')}', TopN='{top_n}'")

    # --- Determine Filenames & ID Vars --- 
    data_folder = current_app.config['DATA_FOLDER']
    weights_filename = "w_secs.csv"
    if data_source == 'Original':
        metric_filename = f"sec_{metric_name}.csv"
    elif data_source == 'SP':
        metric_filename = f"sp_sec_{metric_name}.csv" # Assuming S&P file prefix
    else:
        raise ValueError(f"Unsupported data_source: {data_source}")
        
    weights_filepath = os.path.join(data_folder, weights_filename)
    metric_filepath = os.path.join(data_folder, metric_filename)
    # --- CORRECTED: Use reference.csv for security names ---
    reference_filepath = os.path.join(data_folder, "reference.csv")

    weight_id_vars = ['ISIN', 'Funds'] 
    metric_id_vars = ['ISIN', 'Funds']
    # --- CORRECTED: Define ID vars for reference.csv ---
    reference_id_vars = ['ISIN', 'Security Name']

    # --- Load and Process Data --- 
    # Weights Data
    current_app.logger.info(f"Loading weights: {weights_filepath}")
    weights_df_raw = load_simple_csv(weights_filepath, weights_filename)
    if weights_df_raw is None:
        raise FileNotFoundError(f"Could not load weights file: {weights_filename}")
    weights_long = _melt_data(weights_df_raw, weight_id_vars, fund_code)
    if weights_long is None:
        # Raise specific error - _melt_data logs details
        raise ValueError(f"Could not process weights data for fund '{fund_code}' from {weights_filename}.")
    if weights_long.empty:
         raise ValueError(f"No weight data found for fund '{fund_code}' in {weights_filename}. Calculation cannot proceed.")

    weights_long.rename(columns={'Value': 'Weight'}, inplace=True)
    weights_long['Weight'] = pd.to_numeric(weights_long['Weight'], errors='coerce')
    weights_long = weights_long.sort_values(by=['ISIN', 'Date'])
    weights_long['Weight'] = weights_long.groupby('ISIN')['Weight'].ffill()
    weights_long = weights_long.dropna(subset=['Weight'])
    if weights_long.empty:
        raise ValueError("No valid weight data remaining after processing NAs.")
    current_app.logger.info(f"Processed {len(weights_long)} weight records.")

    # Metric Data
    current_app.logger.info(f"Loading metric values: {metric_filepath}")
    metric_df_raw = load_simple_csv(metric_filepath, metric_filename)
    if metric_df_raw is None:
        raise FileNotFoundError(f"Metric data file not found or failed to load: {metric_filename}. Ensure the file exists and is readable.")
    metric_long = _melt_data(metric_df_raw, metric_id_vars, fund_code)
    if metric_long is None:
        raise ValueError(f"Could not process metric data for fund '{fund_code}' from {metric_filename}.")
    if metric_long.empty:
         raise ValueError(f"No metric data found for fund '{fund_code}' in {metric_filename}. Calculation cannot proceed.")
         
    metric_long.rename(columns={'Value': 'MetricValue'}, inplace=True)
    metric_long['MetricValue'] = pd.to_numeric(metric_long['MetricValue'], errors='coerce')
    metric_long = metric_long.dropna(subset=['MetricValue'])
    if metric_long.empty:
         raise ValueError("No valid metric data remaining after processing NAs.")
    current_app.logger.info(f"Processed {len(metric_long)} metric value records.")

    # --- Merge, Calculate, Rank --- 
    current_app.logger.info("Merging weights and metric data...")
    merged_data = pd.merge(metric_long, weights_long[['ISIN', 'Date', 'Weight']], on=['ISIN', 'Date'], how='inner')
    if merged_data.empty:
        raise ValueError("No matching data found between weights and metric values for the specified fund and dates.")
    current_app.logger.info(f"Merged data has {len(merged_data)} records.")

    merged_data['DailyContribution'] = merged_data['Weight'] * merged_data['MetricValue']
    merged_data = merged_data.dropna(subset=['DailyContribution'])
    if merged_data.empty:
         raise ValueError("Could not calculate daily contributions (check for NaNs in weights or metric values).")
    current_app.logger.info("Daily contributions calculated.")

    baseline_data = merged_data[merged_data['Date'] == baseline_date].copy()
    baseline_contribs = baseline_data.drop_duplicates(subset=['ISIN'], keep='last')[['ISIN', 'DailyContribution']]
    baseline_contribs = baseline_contribs.set_index('ISIN')['DailyContribution']
    current_app.logger.info(f"Found {len(baseline_contribs)} baseline contributions for date {baseline_date.strftime('%Y-%m-%d')}.")

    period_data = merged_data[(merged_data['Date'] >= start_date) & (merged_data['Date'] <= end_date)].copy()
    if period_data.empty:
         raise ValueError(f"No data found within the selected period {start_date_str} to {end_date_str}.")
    
    average_contribs = period_data.groupby('ISIN')['DailyContribution'].mean()
    current_app.logger.info(f"Calculated average contributions for {len(average_contribs)} securities over the period.")

    results_df = pd.DataFrame(average_contribs).rename(columns={'DailyContribution': 'AverageContribution'})
    results_df['BaselineContribution'] = results_df.index.map(baseline_contribs)
    
    results_df = results_df.dropna(subset=['BaselineContribution', 'AverageContribution'])
    if results_df.empty:
        raise ValueError("Could not compare average to baseline (possibly missing baseline data for all relevant securities).")
            
    results_df['ContributionDifference'] = results_df['AverageContribution'] - results_df['BaselineContribution']
    results_df = results_df[results_df['ContributionDifference'] != 0]
    if results_df.empty:
        current_app.logger.warning("No securities found with non-zero contribution difference.")
        # Return empty lists instead of raising error here
        top_contributors_list = []
        top_detractors_list = []
    else:
        current_app.logger.info(f"Calculated contribution difference for {len(results_df)} securities.")

        # --- Optional: Merge Security Names ---
        reference_df = None
        try:
            # --- CORRECTED: Load reference.csv ---
            reference_df = load_simple_csv(reference_filepath, "reference.csv")
            if reference_df is not None and not reference_df.empty:
                # --- CORRECTED: Check for ISIN and Security Name in reference.csv ---
                if 'ISIN' in reference_df.columns and 'Security Name' in reference_df.columns:
                     # Prepare the lookup dictionary {ISIN: Security Name}
                     sec_names_lookup = reference_df.drop_duplicates(subset=['ISIN']).set_index('ISIN')['Security Name'].to_dict()
                     # Map the names to the results_df, filling missing ones with the ISIN index
                     # FIX: Use a lambda with .get fallback to ISIN (avoids combine_first error)
                     results_df['Security Name'] = results_df.index.map(lambda isin: sec_names_lookup.get(isin, isin))
                     current_app.logger.info(f"Successfully merged security names from reference.csv for {results_df['Security Name'].notna().sum()} / {len(results_df)} securities.")
                else:
                    # --- CORRECTED: Log message for reference.csv ---
                    current_app.logger.warning("'ISIN' or 'Security Name' column not found in reference.csv. Cannot merge names.")
                    results_df['Security Name'] = results_df.index # Default to ISIN
            else:
                # This handles cases where the file exists but is empty or load_simple_csv returns None (e.g., read error)
                # --- CORRECTED: Log message for reference.csv ---
                current_app.logger.warning("reference.csv empty or could not be loaded. Using ISIN as name.")
                results_df['Security Name'] = results_df.index # Default to ISIN
        except FileNotFoundError:
             # --- CORRECTED: Log message for reference.csv ---
             current_app.logger.warning("reference.csv not found. Using ISIN as name.")
             results_df['Security Name'] = results_df.index # Default to ISIN
        except Exception as e:
            # --- CORRECTED: Log message for reference.csv ---
            current_app.logger.error(f"Error loading or merging reference.csv: {e}. Using ISIN as name.", exc_info=True)
            results_df['Security Name'] = results_df.index # Default to ISIN in case of other errors

        # --- Rank and Format ---
        results_df = results_df.sort_values('ContributionDifference', ascending=False)
        top_contributors = results_df.head(top_n)
        top_detractors = results_df.tail(top_n).iloc[::-1]

        output_columns = ['ISIN', 'Security Name', 'ContributionDifference', 'AverageContribution', 'BaselineContribution']
        # Ensure ISIN is included (as it's the index)
        top_contributors_list = make_json_safe(top_contributors.reset_index()[output_columns].to_dict(orient='records'))
        top_detractors_list = make_json_safe(top_detractors.reset_index()[output_columns].to_dict(orient='records'))

    # --- Construct Success Result --- 
    results_json = {
        "metric_name": metric_name,
        "fund_code": fund_code,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "baseline_date": baseline_date.strftime('%Y-%m-%d'),
        "data_source": data_source,
        "top_contributors": top_contributors_list,
        "top_detractors": top_detractors_list
    }
    current_app.logger.info(f"Successfully calculated contributions. Found {len(top_contributors_list)} contributors, {len(top_detractors_list)} detractors.")
    return results_json

@metric_bp.route('/<string:metric_name>/inspect', methods=['POST'])
def inspect_metric_contribution(metric_name):
    """
    API endpoint to calculate security contributions to a metric's change over a period.
    Uses the _calculate_contributions helper function.
    """
    current_app.logger.info(f"--- API Request: Inspect Metric {metric_name} ---")
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request: No JSON body received."}), 400

    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    fund_code = data.get('fund_code')
    data_source = data.get('data_source', 'Original')
    top_n = data.get('top_n', 10)

    if not all([start_date_str, end_date_str, fund_code]):
        return jsonify({"error": "Missing required parameters: 'start_date', 'end_date', and 'fund_code' are required."}), 400

    try:
        # Call the helper function to perform the calculation
        results = _calculate_contributions(
            metric_name=metric_name,
            fund_code=fund_code,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            data_source=data_source,
            top_n=top_n
        )
        return jsonify(results), 200

    except FileNotFoundError as e:
         current_app.logger.error(f"Inspect API Error: File not found - {e}")
         return jsonify({"error": f"Required data file not found: {e}. Ensure files like '{weights_filename}' and metric files exist."}), 500
    except ValueError as e:
        current_app.logger.error(f"Inspect API Error: Value error - {e}")
        return jsonify({"error": f"Input or data processing error: {e}"}), 400 # Use 400 for client-side input errors / known data issues
    except KeyError as e:
        current_app.logger.error(f"Inspect API Error: Missing column - {e}")
        return jsonify({"error": f"Data schema error: Missing expected column '{e}' in input files."}), 500
    except Exception as e:
        current_app.logger.error(f"Inspect API Error: Unexpected error processing metric {metric_name} for fund {fund_code} - {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500

@metric_bp.route('/inspect/results')
def inspect_results_page():
    """
    Renders the results page for the inspect feature.
    Fetches data by calling the _calculate_contributions helper function.
    """
    metric_name = request.args.get('metric_name')
    fund_code = request.args.get('fund_code')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    data_source = request.args.get('data_source', 'Original') # Get data source from query param
    top_n = request.args.get('top_n', 10, type=int) # Allow overriding top_n via query param if needed

    if not all([metric_name, fund_code, start_date_str, end_date_str]):
         return render_template('error_page.html', error_message="Missing parameters for inspect results (metric_name, fund_code, start_date, end_date required)."), 400

    current_app.logger.info(f"Rendering Inspect results page for {metric_name}, {fund_code} [{start_date_str} - {end_date_str}], Source: {data_source}")

    contribution_data = {}
    error_message = None

    try:
        # Call the helper function to get the data
        contribution_data = _calculate_contributions(
            metric_name=metric_name,
            fund_code=fund_code,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            data_source=data_source,
            top_n=top_n
        )
        # Check if the helper returned an error dictionary itself (though it now raises exceptions)
        if 'error' in contribution_data:
            error_message = contribution_data['error']
            contribution_data = {} # Clear data on error

    except (FileNotFoundError, ValueError, KeyError) as e:
        current_app.logger.error(f"Error calculating inspect results for page: {e}")
        error_message = f"Could not retrieve contribution details: {e}"
        contribution_data = {} # Ensure empty dict on error
    except Exception as e:
        current_app.logger.error(f"Unexpected error calculating inspect results for page: {e}", exc_info=True)
        error_message = f"An unexpected server error occurred while calculating results."
        contribution_data = {} # Ensure empty dict on error

    # Prepare context for template, ensuring keys exist even if empty/error
    template_context = {
        'metric_name': metric_name,
        'fund_code': fund_code,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'data_source': data_source,
        'baseline_date': contribution_data.get('baseline_date', 'N/A'),
        'top_contributors': contribution_data.get('top_contributors', []),
        'top_detractors': contribution_data.get('top_detractors', []),
        'error_message': error_message
    }

    return render_template('inspect_results.html', **template_context)

# --- End Inspect Feature Routes ---