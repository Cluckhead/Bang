# This file defines the routes for displaying detailed views of specific time-series metrics.
# It handles requests where the user wants to see the data and charts for a single metric
# (like 'Yield' or 'Spread Duration') across all applicable funds.
# It loads primary and optionally secondary data, calculates key metrics,
# handles filtering based on 'SS Project - In Scope' status via a query parameter,
# prepares data for visualization, and renders the metric detail page.
# All charts use the full Dates.csv list for the x-axis, handling weekends and holidays.

"""
Blueprint for metric-specific routes (e.g., displaying individual metric charts).
"""
from flask import Blueprint, render_template, jsonify, current_app, request # Added request
import os
import pandas as pd
import numpy as np
import traceback
import math

# Import necessary functions/constants from other modules
from config import COLOR_PALETTE
from data_loader import load_and_process_data, LoadResult # Import LoadResult type
from metric_calculator import calculate_latest_metrics
from process_data import read_and_sort_dates

# Define the blueprint for metric routes, using '/metric' as the URL prefix
metric_bp = Blueprint('metric', __name__, url_prefix='/metric')

@metric_bp.route('/<string:metric_name>')
def metric_page(metric_name):
    """Renders the detailed page (`metric_page_js.html`) for a specific metric. X-axis always uses Dates.csv."""
    primary_filename = f"ts_{metric_name}.csv"
    secondary_filename = f"sp_{primary_filename}"
    fund_code = 'N/A' # Default for logging fallback in case of early error
    latest_date_overall = pd.Timestamp.min # Initialize
    error_message = None # Initialize error message

    try:
        # --- Get Filter State from Query Parameter ---
        # Default to 'true' if parameter is missing or invalid
        sp_valid_param = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid = sp_valid_param == 'true'
        current_app.logger.info(f"--- Processing metric: {metric_name}, S&P Valid Filter: {filter_sp_valid} ---")
        current_app.logger.info(f"URL Query Params: {request.args}") # Log query params for debugging

        # --- Load Data (Primary and Secondary) with Filtering ---
        current_app.logger.info(f"Loading data: Primary='{primary_filename}', Secondary='{secondary_filename}', Filter='{filter_sp_valid}'")
        load_result: LoadResult = load_and_process_data(
            primary_filename=primary_filename,
            secondary_filename=secondary_filename,
            filter_sp_valid=filter_sp_valid # Pass the filter flag
        )
        primary_df, pri_fund_cols, pri_bench_col, secondary_df, sec_fund_cols, sec_bench_col = load_result

        # --- Validate Primary Data (Post-Filtering) ---
        if primary_df is None or primary_df.empty:
            data_folder_for_error = current_app.config['DATA_FOLDER']
            primary_filepath = os.path.join(data_folder_for_error, primary_filename)
            if not os.path.exists(primary_filepath):
                 current_app.logger.error(f"Error: Primary data file not found: {primary_filepath} (Filter: {filter_sp_valid})")
                 error_message = f"Error: Data file for metric '{metric_name}' (expected: '{primary_filename}') not found."
                 # Render template with error message and filter state
                 return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}', # Empty data
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(), # Empty dataframe
                               sp_valid_state=filter_sp_valid, # Pass filter state
                               secondary_data_initially_available=False,
                               error_message=error_message), 404
            else:
                 current_app.logger.error(f"Error: Failed to process primary data file '{primary_filename}' or file became empty after filtering (Filter: {filter_sp_valid}).")
                 error_message = f"Error: Could not process required data for metric '{metric_name}' (file: '{primary_filename}')."
                 if filter_sp_valid:
                     error_message += " The data might be missing, empty, or contain no rows marked as 'TRUE' in 'SS Project - In Scope' when the S&P Valid filter is ON."
                 else:
                      error_message += " Check file format or logs."
                 # Render template with error message and filter state
                 return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               error_message=error_message), 500

        # Add check for pri_fund_cols after ensuring primary_df is not None
        if pri_fund_cols is None:
            current_app.logger.error(f"Error: Could not identify primary fund value columns in '{primary_filename}' after loading.")
            error_message = f"Error: Failed to identify fund value columns in '{primary_filename}'. Check file structure."
            return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               error_message=error_message), 500

        # --- Determine Combined Metadata (Post-Filtering) ---
        all_dfs = [df for df in [primary_df, secondary_df] if df is not None and not df.empty]
        if not all_dfs:
            current_app.logger.error(f"Error: No valid data loaded for {metric_name} (Filter: {filter_sp_valid})")
            error_message = f"Error: No data found for metric '{metric_name}' (Filter Applied: {filter_sp_valid})."
            return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json='{}',
                               latest_date="N/A",
                               missing_funds=pd.DataFrame(),
                               sp_valid_state=filter_sp_valid,
                               secondary_data_initially_available=False,
                               error_message=error_message), 404

        # --- Calculate Latest Date Overall ---
        try:
            combined_index = pd.concat(all_dfs).index
            latest_date_overall = combined_index.get_level_values(0).max()
            latest_date_str = latest_date_overall.strftime('%Y-%m-%d') if pd.notna(latest_date_overall) else "N/A"
        except Exception as idx_err:
            current_app.logger.error(f"Error combining indices or getting latest date for {metric_name}: {idx_err}")
            latest_date_overall = primary_df.index.get_level_values(0).max() # Fallback to primary
            latest_date_str = latest_date_overall.strftime('%Y-%m-%d') if pd.notna(latest_date_overall) else "N/A"
            current_app.logger.warning(f"Warning: Using latest date from primary data only: {latest_date_str}")

        # --- Check Secondary Data Availability ---
        secondary_data_available = secondary_df is not None and not secondary_df.empty and sec_fund_cols is not None
        current_app.logger.info(f"Secondary data available for {metric_name}: {secondary_data_available}")

        # --- Calculate Metrics (based on potentially filtered data) ---
        current_app.logger.info(f"Calculating metrics for {metric_name}...")
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
                           error_message=None) # No error message here specifically

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
            missing_latest = latest_metrics[latest_metrics[check_cols_for_missing].isna().any(axis=1)]
        else:
            current_app.logger.warning(f"Warning: No primary Z-Score or Latest Value columns found for {metric_name} to check for missing data.")
            missing_latest = pd.DataFrame(index=latest_metrics.index) # Assume none missing

        # --- Prepare Data Structure for JavaScript --- 
        current_app.logger.info(f"Preparing chart and metric data for JavaScript for {metric_name}...")
        funds_data_for_js = {}
        fund_codes_in_metrics = latest_metrics.index
        primary_df_index = primary_df.index
        secondary_df_index = secondary_df.index if secondary_data_available and secondary_df is not None else None
        
        def nan_to_none(data_list):
             return [None if pd.isna(x) else x for x in data_list]
             
        data_folder = current_app.config['DATA_FOLDER']
        dates_file_path = os.path.join(data_folder, 'Dates.csv')
        full_date_list = read_and_sort_dates(dates_file_path) or []

        for fund_code in fund_codes_in_metrics:
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            is_missing_latest = fund_code in missing_latest.index
            fund_charts = [] # Initialize list to hold chart configs for this fund

            primary_labels = full_date_list
            primary_dt_index = None
            fund_hist_primary = None
            relative_primary_hist = None
            relative_secondary_hist = None # Initialize

            # --- Get Primary Historical Data ---
            if fund_code in primary_df_index.get_level_values(1):
                fund_hist_primary = primary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_primary.index, pd.DatetimeIndex):
                    # Reindex to full_date_list
                    fund_hist_primary = fund_hist_primary.reindex(pd.to_datetime(full_date_list))
                    primary_dt_index = pd.to_datetime(full_date_list)
                else:
                    fund_hist_primary = fund_hist_primary.reindex(full_date_list)
                    current_app.logger.warning(f"Warning: Primary index for {fund_code} is not DatetimeIndex.")

            # --- Get Secondary Historical Data ---
            fund_hist_secondary = None
            if secondary_data_available and secondary_df_index is not None and fund_code in secondary_df_index.get_level_values(1):
                fund_hist_secondary_raw = secondary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_secondary_raw.index, pd.DatetimeIndex):
                    fund_hist_secondary_raw = fund_hist_secondary_raw.reindex(pd.to_datetime(full_date_list))
                    fund_hist_secondary = fund_hist_secondary_raw
                else:
                    fund_hist_secondary = fund_hist_secondary_raw.reindex(full_date_list)
                    current_app.logger.warning(f"Warning: Secondary index for {fund_code} is not DatetimeIndex.")

            # --- Prepare Main Chart Datasets (Primary Data) ---
            main_datasets = []
            if fund_hist_primary is not None:
                # Add primary fund column(s)
                if pri_fund_cols:
                    for i, col in enumerate(pri_fund_cols):
                        if col in fund_hist_primary.columns:
                            main_datasets.append({
                                "label": col,
                                "data": nan_to_none(fund_hist_primary[col].tolist()), # Convert NaN to None
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
                        "data": nan_to_none(fund_hist_primary[pri_bench_col].tolist()), # Convert NaN to None
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
                                "data": nan_to_none(fund_hist_secondary[col].tolist()), # Convert NaN to None
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
                        "data": nan_to_none(fund_hist_secondary[sec_bench_col].tolist()), # Convert NaN to None
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
                for f_col in pri_fund_cols:
                    if f_col in fund_hist_primary.columns:
                        pri_fund_col_used = f_col
                        break
            if pri_fund_col_used and pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                port_col_hist = fund_hist_primary[pri_fund_col_used]
                bench_col_hist = fund_hist_primary[pri_bench_col]
                if not port_col_hist.dropna().empty and not bench_col_hist.dropna().empty:
                    relative_primary_hist = (port_col_hist - bench_col_hist).round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None)
                    relative_datasets.append({
                        'label': 'Relative (Port - Bench)',
                        'data': nan_to_none(relative_primary_hist.tolist()),
                        'borderColor': '#1f77b4', # Specific color for primary relative
                        'backgroundColor': '#aec7e8',
                        'tension': 0.1,
                        'source': 'primary_relative',
                        'isSpData': False
                    })
                    # Extract primary relative metrics
                    for col in fund_latest_metrics_row.index:
                        if col.startswith('Relative '):
                             relative_metrics_for_js[col] = fund_latest_metrics_row[col] if pd.notna(fund_latest_metrics_row[col]) else None

            # 2. Calculate Secondary Relative Series (if applicable)
            sec_fund_col_used = None
            if fund_hist_secondary is not None and sec_fund_cols:
                 for f_col in sec_fund_cols:
                    if f_col in fund_hist_secondary.columns:
                        sec_fund_col_used = f_col
                        break
            if sec_fund_col_used and sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                port_col_hist_sec = fund_hist_secondary[sec_fund_col_used]
                bench_col_hist_sec = fund_hist_secondary[sec_bench_col]
                # Check if S&P Relative metrics exist, indicating calculation happened
                if 'S&P Relative Change Z-Score' in fund_latest_metrics_row.index and pd.notna(fund_latest_metrics_row['S&P Relative Change Z-Score']):
                    if not port_col_hist_sec.dropna().empty and not bench_col_hist_sec.dropna().empty:
                        relative_secondary_hist = (port_col_hist_sec - bench_col_hist_sec).round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None)
                        relative_datasets.append({
                            'label': 'S&P Relative (Port - Bench)',
                            'data': nan_to_none(relative_secondary_hist.tolist()),
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
                                relative_metrics_for_js[col] = fund_latest_metrics_row[col] if pd.notna(fund_latest_metrics_row[col]) else None

            # 3. Create Relative Chart Config if primary relative data exists
            if relative_primary_hist is not None:
                relative_chart_config = {
                    'chart_type': 'relative',
                    'title': f'{fund_code} - Relative ({metric_name})',
                    'labels': primary_labels,
                    'datasets': relative_datasets,
                    'latest_metrics': relative_metrics_for_js
                }
                # We will add this later, after the main chart
                # fund_charts.append(relative_chart_config) # Add relative chart first

            # --- Prepare Main Chart Config
            main_chart_config = None
            if main_datasets: # Only create if there's actual data
                main_chart_config = {
                    'chart_type': 'main',
                    'title': f'{fund_code} - {metric_name}',
                    'labels': primary_labels,
                    'datasets': main_datasets,
                    'latest_metrics': fund_latest_metrics_row.to_dict()
                }
                # Add main chart FIRST
                fund_charts.append(main_chart_config)
            
            # Now add the relative chart config if it exists
            if relative_chart_config:
                fund_charts.append(relative_chart_config)

            # --- Store Fund Data ---
            # Ensure all values in latest_metrics_raw are JSON-safe (no NaN/inf)
            safe_latest_metrics_raw = fund_latest_metrics_row.where(pd.notnull(fund_latest_metrics_row), None).replace([np.inf, -np.inf], None).to_dict()
            funds_data_for_js[fund_code] = {
                'latest_metrics_html': "<td>Placeholder</td>", # Replace with actual table generation if needed separately
                'latest_metrics_raw': safe_latest_metrics_raw, # Use safe dict
                'charts': fund_charts,
                'is_missing_latest': is_missing_latest,
                'max_abs_z': fund_latest_metrics_row.filter(like='Z-Score').abs().max() if hasattr(fund_latest_metrics_row.filter(like='Z-Score'), 'abs') else None
            }

        # --- Final JSON Payload ---
        # Recursively ensure all values in json_payload are JSON-safe (no NaN/inf)
        def make_json_safe(obj):
            if isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_safe(x) for x in obj]
            elif isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            return obj

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
            "funds": funds_data_for_js
        }
        json_payload = make_json_safe(json_payload)

        # --- Render Template --- 
        current_app.logger.info(f"Rendering template for {metric_name} with filter_sp_valid={filter_sp_valid}")
        return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json=jsonify(json_payload).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y') if pd.notna(latest_date_overall) else "N/A",
                               missing_funds=missing_latest,
                               sp_valid_state=filter_sp_valid, # Pass filter state
                               secondary_data_initially_available=secondary_data_available, # Pass initial availability for JS logic
                               error_message=error_message # Pass potential error message
                               )

    except FileNotFoundError as e:
        current_app.logger.error(f"Error: File not found during processing for {metric_name}. Details: {e}")
        traceback.print_exc()
        error_message = f"Error: Required data file not found for metric '{metric_name}'. {e}"
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid_except = sp_valid_param_except == 'true'
        return render_template('metric_page_js.html',
                               metric_name=metric_name, charts_data_json='{}', latest_date="N/A",
                               missing_funds=pd.DataFrame(), sp_valid_state=filter_sp_valid_except,
                               secondary_data_initially_available=False, error_message=error_message), 404

    except Exception as e:
        current_app.logger.error(f"Unexpected error processing metric {metric_name}: {e}\n{traceback.format_exc()}")
        error_message = f"An unexpected error occurred while processing metric '{metric_name}'. Please check the logs for details."
        # Determine filter state even in exception for consistent template rendering
        sp_valid_param_except = request.args.get('sp_valid', 'true').lower()
        filter_sp_valid_except = sp_valid_param_except == 'true'
        return render_template('metric_page_js.html',
                               metric_name=metric_name, charts_data_json='{}', latest_date="N/A",
                               missing_funds=pd.DataFrame(), sp_valid_state=filter_sp_valid_except,
                               secondary_data_initially_available=False, error_message=error_message), 500