# This file defines the routes for displaying detailed views of specific time-series metrics.
# It handles requests where the user wants to see the data and charts for a single metric
# (like 'Yield' or 'Spread Duration') across all applicable funds.
# Updated to optionally load and display a secondary data source (prefixed with 'sp_').

"""
Blueprint for metric-specific routes (e.g., displaying individual metric charts).
"""
from flask import Blueprint, render_template, jsonify, current_app
import os
import pandas as pd
import numpy as np
import traceback

# Import necessary functions/constants from other modules
from config import COLOR_PALETTE
from data_loader import load_and_process_data, LoadResult # Import LoadResult type
from metric_calculator import calculate_latest_metrics

# Define the blueprint for metric routes, using '/metric' as the URL prefix
metric_bp = Blueprint('metric', __name__, url_prefix='/metric')

@metric_bp.route('/<string:metric_name>')
def metric_page(metric_name):
    """Renders the detailed page (`metric_page_js.html`) for a specific metric.

    Loads primary data (e.g., 'ts_Yield.csv') and optionally secondary data ('sp_ts_Yield.csv').
    Calculates metrics for both, prepares data for Chart.js, and passes it to the template.
    Includes a flag to indicate if secondary data is available.
    """
    primary_filename = f"ts_{metric_name}.csv"
    secondary_filename = f"sp_{primary_filename}"
    fund_code = 'N/A' # Default for logging fallback in case of early error
    latest_date_overall = pd.Timestamp.min # Initialize

    try:
        print(f"--- Processing metric: {metric_name} ---")
        print(f"Primary file: {primary_filename}, Secondary file: {secondary_filename}")
        
        # Load Data (Primary and Secondary)
        load_result: LoadResult = load_and_process_data(primary_filename, secondary_filename)
        primary_df, pri_fund_cols, pri_bench_col, secondary_df, sec_fund_cols, sec_bench_col = load_result

        # --- Validate Primary Data --- 
        if primary_df is None or primary_df.empty or pri_fund_cols is None:
            # Retrieve the configured absolute data folder path for error reporting
            data_folder_for_error = current_app.config['DATA_FOLDER']
            # Construct the full path using the absolute data_folder path
            primary_filepath = os.path.join(data_folder_for_error, primary_filename)
            if not os.path.exists(primary_filepath):
                 current_app.logger.error(f"Error: Primary data file not found: {primary_filepath}")
                 return f"Error: Data file for metric '{metric_name}' (expected: '{primary_filename}') not found.", 404
            else:
                 print(f"Error: Failed to process primary data file: {primary_filename}")
                 return f"Error: Could not process required data for metric '{metric_name}' (file: {primary_filename}). Check file format or logs.", 500

        # --- Determine Combined Metadata --- 
        all_dfs = [df for df in [primary_df, secondary_df] if df is not None and not df.empty]
        if not all_dfs:
             # Should be caught by primary check, but safeguard
            print(f"Error: No valid data loaded for {metric_name}")
            return f"Error: No data found for metric '{metric_name}'.", 404

        try:
            combined_index = pd.concat(all_dfs).index
            latest_date_overall = combined_index.get_level_values(0).max()
            latest_date_str = latest_date_overall.strftime('%Y-%m-%d')
        except Exception as idx_err:
            print(f"Error combining indices or getting latest date for {metric_name}: {idx_err}")
            # Fallback or re-raise? Let's try to proceed if possible, using primary date
            latest_date_overall = primary_df.index.get_level_values(0).max()
            latest_date_str = latest_date_overall.strftime('%Y-%m-%d')
            print(f"Warning: Using latest date from primary data only: {latest_date_str}")

        secondary_data_available = secondary_df is not None and not secondary_df.empty and sec_fund_cols is not None
        print(f"Secondary data available for {metric_name}: {secondary_data_available}")
        
        # --- Calculate Metrics --- 
        print(f"Calculating metrics for {metric_name}...")
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
        if latest_metrics.empty:
            print(f"Warning: Metric calculation returned empty DataFrame for {metric_name}. Rendering page with no fund data.")
            missing_latest = pd.DataFrame()
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
                           latest_date=latest_date_overall.strftime('%d/%m/%Y'), 
                           missing_funds=missing_latest)

        # --- Identify Missing Funds (based on primary data) --- 
        print(f"Identifying potentially missing latest data for {metric_name}...")
        primary_cols_for_check = []
        if pri_bench_col:
            primary_cols_for_check.append(pri_bench_col)
        if pri_fund_cols:
            primary_cols_for_check.extend(pri_fund_cols)
        
        # Prefer checking Z-Score, fallback to Latest Value
        primary_z_score_cols = [f'{col} Change Z-Score' for col in primary_cols_for_check 
                                if f'{col} Change Z-Score' in latest_metrics.columns]
        primary_latest_val_cols = [f'{col} Latest Value' for col in primary_cols_for_check
                                   if f'{col} Latest Value' in latest_metrics.columns]
        
        check_cols_for_missing = primary_z_score_cols if primary_z_score_cols else primary_latest_val_cols
        
        if check_cols_for_missing:
            missing_latest = latest_metrics[latest_metrics[check_cols_for_missing].isna().any(axis=1)]
        else:
            print(f"Warning: No primary Z-Score or Latest Value columns found for {metric_name} to check for missing data.")
            missing_latest = pd.DataFrame(index=latest_metrics.index) # Assume none are missing if no check cols

        # --- Prepare Data Structure for JavaScript --- 
        print(f"Preparing chart and metric data for JavaScript for {metric_name}...")
        funds_data_for_js = {}
        fund_codes_in_metrics = latest_metrics.index
        primary_df_index = primary_df.index
        secondary_df_index = secondary_df.index if secondary_data_available and secondary_df is not None else None

        # Loop through funds present in the calculated metrics
        for fund_code in fund_codes_in_metrics:
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            is_missing_latest = fund_code in missing_latest.index
            fund_charts = [] # Initialize list to hold chart configs for this fund

            primary_labels = []
            primary_dt_index = None
            fund_hist_primary = None
            relative_primary_hist = None
            relative_secondary_hist = None # Initialize

            # --- Get Primary Historical Data ---
            if fund_code in primary_df_index.get_level_values(1):
                fund_hist_primary = primary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_primary.index, pd.DatetimeIndex):
                    primary_dt_index = fund_hist_primary.index # Store before filtering
                    # Filter out weekends (assuming data is daily/business daily)
                    fund_hist_primary = fund_hist_primary[primary_dt_index.dayofweek < 5]
                    primary_dt_index = fund_hist_primary.index # Update after filtering
                    primary_labels = primary_dt_index.strftime('%Y-%m-%d').tolist()
                else:
                    primary_labels = fund_hist_primary.index.astype(str).tolist()
                    print(f"Warning: Primary index for {fund_code} is not DatetimeIndex.")

            # --- Get Secondary Historical Data ---
            fund_hist_secondary = None
            if secondary_data_available and secondary_df_index is not None and fund_code in secondary_df_index.get_level_values(1):
                fund_hist_secondary_raw = secondary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_secondary_raw.index, pd.DatetimeIndex):
                    fund_hist_secondary_raw = fund_hist_secondary_raw[fund_hist_secondary_raw.index.dayofweek < 5]
                    # Reindex to primary date index if possible
                    if primary_dt_index is not None and not primary_dt_index.empty:
                         try:
                             if isinstance(fund_hist_secondary_raw.index, pd.DatetimeIndex):
                                 fund_hist_secondary = fund_hist_secondary_raw.reindex(primary_dt_index)
                                 print(f"Successfully reindexed secondary data for {fund_code}.")
                             else:
                                 print(f"Warning: Cannot reindex - Secondary index for {fund_code} is not DatetimeIndex after filtering.")
                         except Exception as reindex_err:
                             print(f"Warning: Reindexing secondary data for {fund_code} failed: {reindex_err}. Chart may be misaligned.")
                             fund_hist_secondary = fund_hist_secondary_raw # Use unaligned as fallback
                    else:
                         print(f"Warning: Cannot reindex secondary for {fund_code} - Primary DatetimeIndex unavailable.")
                         fund_hist_secondary = fund_hist_secondary_raw # Use unaligned as fallback
                else:
                    print(f"Warning: Secondary index for {fund_code} is not DatetimeIndex.")
                    fund_hist_secondary = fund_hist_secondary_raw # Use raw if not datetime

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
                        'data': relative_primary_hist.tolist(),
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
                            'data': relative_secondary_hist.tolist(),
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

            # --- Prepare Main Chart Data ---
            main_datasets = []
            main_metrics_for_js = {}

            # 1. Primary Datasets (Portfolio/Benchmark)
            if fund_hist_primary is not None:
                if pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                    bench_values = fund_hist_primary[pri_bench_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                    main_datasets.append({
                        'label': pri_bench_col,
                        'data': bench_values,
                        'borderColor': 'black', 'backgroundColor': 'grey',
                        'borderDash': [5, 5], 'tension': 0.1,
                        'source': 'primary', 'isSpData': False
                    })
                if pri_fund_cols:
                    for i, fund_col in enumerate(pri_fund_cols):
                        if fund_col in fund_hist_primary.columns:
                            fund_values = fund_hist_primary[fund_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
                            main_datasets.append({
                                'label': fund_col,
                                'data': fund_values,
                                'borderColor': color, 'backgroundColor': color + '40',
                                'tension': 0.1,
                                'source': 'primary', 'isSpData': False
                            })
                # Extract primary non-relative metrics
                for col in fund_latest_metrics_row.index:
                    if not col.startswith('Relative ') and not col.startswith('S&P Relative '):
                        main_metrics_for_js[col] = fund_latest_metrics_row[col] if pd.notna(fund_latest_metrics_row[col]) else None

            # 2. Secondary Datasets (Portfolio/Benchmark)
            if fund_hist_secondary is not None:
                if sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                    bench_values_sec = fund_hist_secondary[sec_bench_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                    # Check if S&P benchmark metrics exist
                    if f'S&P {sec_bench_col} Change Z-Score' in fund_latest_metrics_row.index and pd.notna(fund_latest_metrics_row[f'S&P {sec_bench_col} Change Z-Score']):
                         main_datasets.append({
                            'label': f"S&P {sec_bench_col}",
                            'data': bench_values_sec,
                            'borderColor': '#FFA500', 'backgroundColor': '#FFDAB9',
                            'borderDash': [2, 2], 'tension': 0.1,
                            'source': 'secondary', 'isSpData': True, 'hidden': True
                        })
                if sec_fund_cols:
                    for i, fund_col in enumerate(sec_fund_cols):
                        if fund_col in fund_hist_secondary.columns:
                             # Check if S&P fund metrics exist
                             if f'S&P {fund_col} Change Z-Score' in fund_latest_metrics_row.index and pd.notna(fund_latest_metrics_row[f'S&P {fund_col} Change Z-Score']):
                                fund_values_sec = fund_hist_secondary[fund_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                                color_index = i
                                if pri_fund_cols:
                                    try: color_index = pri_fund_cols.index(fund_col)
                                    except ValueError: pass
                                base_color = COLOR_PALETTE[color_index % len(COLOR_PALETTE)]
                                main_datasets.append({
                                    'label': f"S&P {fund_col}",
                                    'data': fund_values_sec,
                                    'borderColor': base_color, 'backgroundColor': base_color + '20',
                                    'borderDash': [2, 2], 'tension': 0.1,
                                    'source': 'secondary', 'isSpData': True, 'hidden': True
                                })
                 # Extract secondary non-relative metrics
                for col in fund_latest_metrics_row.index:
                    if col.startswith('S&P ') and not col.startswith('S&P Relative '):
                         main_metrics_for_js[col] = fund_latest_metrics_row[col] if pd.notna(fund_latest_metrics_row[col]) else None

            # 3. Create Main Chart Config
            main_chart_config = None # Initialize
            if main_datasets: # Only create if there's actual data
                main_chart_config = {
                    'chart_type': 'main',
                    'title': f'{fund_code} - {metric_name}',
                    'labels': primary_labels,
                    'datasets': main_datasets,
                    'latest_metrics': main_metrics_for_js
                }
                # Add main chart FIRST
                fund_charts.append(main_chart_config)
            
            # Now add the relative chart config if it exists
            if relative_chart_config:
                fund_charts.append(relative_chart_config)

            # --- Store Fund Data ---
            funds_data_for_js[fund_code] = {
                'charts': fund_charts,
                'is_missing_latest': is_missing_latest
            }

        # --- Final JSON Payload ---
        json_payload = {
            "metadata": {
                "metric_name": metric_name,
                "latest_date": latest_date_str,
                 # Keep original column names for potential reference, though chart uses specific labels now
                "fund_col_names": pri_fund_cols or [],
                "benchmark_col_name": pri_bench_col,
                "secondary_fund_col_names": sec_fund_cols if secondary_data_available else [],
                "secondary_benchmark_col_name": sec_bench_col if secondary_data_available else None,
                "secondary_data_available": secondary_data_available
            },
            "funds": funds_data_for_js # Use the new structure
        }

        print(f"--- Completed processing metric: {metric_name} ---")

        return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json=jsonify(json_payload).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y'),
                               missing_funds=missing_latest,
                               error_message=None) # Explicitly set error to None on success

    except FileNotFoundError as e:
        print(f"Error: File not found during processing for {metric_name}. Details: {e}")
        traceback.print_exc()
        error_msg = f"Error: Required data file not found for metric '{metric_name}'. {e}"
        return render_template('metric_page_js.html', metric_name=metric_name, charts_data_json='{}', latest_date='N/A', missing_funds=pd.DataFrame(), error_message=error_msg), 404

    except Exception as e:
        print(f"Error processing metric page for {metric_name} (Fund: {fund_code}): {e}")
        traceback.print_exc() # Log the full traceback to console/log file
        error_msg = f"An error occurred while processing metric '{metric_name}'. Please check the server logs for details. Error: {e}"
        # Attempt to render template with error message
        return render_template('metric_page_js.html', metric_name=metric_name, charts_data_json='{}', latest_date='N/A', missing_funds=pd.DataFrame(), error_message=error_msg), 500