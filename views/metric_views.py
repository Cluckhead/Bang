# This file defines the routes for displaying detailed views of specific time-series metrics.
# It handles requests where the user wants to see the data and charts for a single metric
# (like 'Yield' or 'Spread Duration') across all applicable funds.
# Updated to optionally load and display a secondary data source (prefixed with 'sp_').

"""
Blueprint for metric-specific routes (e.g., displaying individual metric charts).
"""
from flask import Blueprint, render_template, jsonify
import os
import pandas as pd
import numpy as np
import traceback

# Import necessary functions/constants from other modules
from config import DATA_FOLDER, COLOR_PALETTE
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
            # Check if the file exists before saying it couldn't be processed
            primary_filepath = os.path.join(DATA_FOLDER, primary_filename)
            if not os.path.exists(primary_filepath):
                 print(f"Error: Primary data file not found: {primary_filepath}")
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

            primary_labels = []
            primary_datasets = []
            fund_hist_primary = None
            primary_dt_index = None
            
            # Get Primary Historical Data
            if fund_code in primary_df_index.get_level_values(1):
                fund_hist_primary = primary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_primary.index, pd.DatetimeIndex):
                    primary_dt_index = fund_hist_primary.index # Store before filtering
                    fund_hist_primary = fund_hist_primary[primary_dt_index.dayofweek < 5]
                    primary_dt_index = fund_hist_primary.index # Update after filtering
                    primary_labels = primary_dt_index.strftime('%Y-%m-%d').tolist()
                else:
                    primary_labels = fund_hist_primary.index.astype(str).tolist()
                    print(f"Warning: Primary index for {fund_code} is not DatetimeIndex.")

                # Create Primary Datasets
                if pri_bench_col and pri_bench_col in fund_hist_primary.columns:
                    bench_values = fund_hist_primary[pri_bench_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                    primary_datasets.append({
                        'label': pri_bench_col,
                        'data': bench_values,
                        'borderColor': 'black', 'backgroundColor': 'grey',
                        'borderDash': [5, 5], 'tension': 0.1,
                        'source': 'primary',
                        'isSpData': False
                    })
                if pri_fund_cols:
                    for i, fund_col in enumerate(pri_fund_cols):
                        if fund_col in fund_hist_primary.columns:
                            fund_values = fund_hist_primary[fund_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
                            primary_datasets.append({
                                'label': fund_col,
                                'data': fund_values,
                                'borderColor': color, 'backgroundColor': color + '40',
                                'tension': 0.1,
                                'source': 'primary',
                                'isSpData': False
                            })
            else:
                print(f"Warning: Fund {fund_code} not found in primary source for historical data.")

            # Get Secondary Historical Data (and align to primary labels)
            secondary_datasets = []
            if secondary_data_available and secondary_df_index is not None and fund_code in secondary_df_index.get_level_values(1):
                fund_hist_secondary = secondary_df.xs(fund_code, level=1).sort_index()
                if isinstance(fund_hist_secondary.index, pd.DatetimeIndex):
                    fund_hist_secondary = fund_hist_secondary[fund_hist_secondary.index.dayofweek < 5]
                    # Reindex to primary date index if possible
                    if primary_dt_index is not None and not primary_dt_index.empty:
                         try:
                             # Ensure secondary index is also datetime before reindexing
                             if isinstance(fund_hist_secondary.index, pd.DatetimeIndex):
                                 fund_hist_secondary_aligned = fund_hist_secondary.reindex(primary_dt_index)
                                 # Replace fund_hist_secondary with aligned version for dataset creation
                                 fund_hist_secondary = fund_hist_secondary_aligned
                                 print(f"Successfully reindexed secondary data for {fund_code}.")
                             else:
                                 print(f"Warning: Cannot reindex - Secondary index for {fund_code} is not DatetimeIndex after filtering.")
                         except Exception as reindex_err:
                             print(f"Warning: Reindexing secondary data for {fund_code} failed: {reindex_err}. Chart may be misaligned.")
                    else:
                         print(f"Warning: Cannot reindex secondary for {fund_code} - Primary DatetimeIndex unavailable.")
                else:
                    print(f"Warning: Secondary index for {fund_code} is not DatetimeIndex.")

                # Create Secondary Datasets (using potentially reindexed data)
                if sec_bench_col and sec_bench_col in fund_hist_secondary.columns:
                    bench_values_sec = fund_hist_secondary[sec_bench_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                    secondary_datasets.append({
                        'label': f"S&P {sec_bench_col}",
                        'data': bench_values_sec,
                        'xAxisID': 'x',
                        'borderColor': '#FFA500',
                        'backgroundColor': '#FFDAB9',
                        'borderDash': [2, 2], 'tension': 0.1,
                        'source': 'secondary',
                        'isSpData': True,
                        'hidden': True
                    })
                if sec_fund_cols:
                    for i, fund_col in enumerate(sec_fund_cols):
                        if fund_col in fund_hist_secondary.columns:
                            fund_values_sec = fund_hist_secondary[fund_col].round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).tolist()
                            color_index = i # Default index
                            if pri_fund_cols: # Try to match color with primary
                                try:
                                    color_index = pri_fund_cols.index(fund_col)
                                except ValueError:
                                    pass # Keep default index if no match
                            base_color = COLOR_PALETTE[color_index % len(COLOR_PALETTE)]
                            secondary_datasets.append({
                                'label': f"S&P {fund_col}",
                                'data': fund_values_sec,
                                'xAxisID': 'x',
                                'borderColor': base_color,
                                'backgroundColor': base_color + '20',
                                'borderDash': [2, 2],
                                'tension': 0.1,
                                'source': 'secondary',
                                'isSpData': True,
                                'hidden': True
                            })
            elif secondary_data_available:
                 print(f"Info: Fund {fund_code} not found in secondary source for historical data.")

            # Combine metrics and chart data for the fund
            fund_latest_metrics_dict = fund_latest_metrics_row.round(3).replace([np.inf, -np.inf], np.nan).where(pd.notnull, None).to_dict()
            funds_data_for_js[fund_code] = {
                'labels': primary_labels, # Use primary labels for the chart axis
                'datasets': primary_datasets + secondary_datasets,
                'metrics': fund_latest_metrics_dict,
                'is_missing_latest': is_missing_latest
            }
        
        # --- Prepare Final JSON Payload --- 
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
        print(f"Finished preparing data for {metric_name}. Sending to template.")
        
        # --- Render Template --- 
        return render_template('metric_page_js.html',
                               metric_name=metric_name,
                               charts_data_json=jsonify(json_payload).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y') if pd.notna(latest_date_overall) else 'N/A', 
                               missing_funds=missing_latest)

    # --- Exception Handling --- 
    except FileNotFoundError:
        # Specific handling for primary file not found is done within the try block
        # This except block catches potential FileNotFoundError from dependencies (less likely)
        print(f"Unexpected FileNotFoundError during processing of {metric_name}: {primary_filename} or {secondary_filename}")
        traceback.print_exc()
        return f"An unexpected file error occurred while processing {metric_name}.", 500
        
    except ValueError as ve:
        print(f"Value Error processing {metric_name}: {ve}")
        traceback.print_exc()
        return f"Error processing data for metric '{metric_name}'. Details: {ve}", 400
        
    except Exception as e:
        print(f"Unhandled Error processing {metric_name} for fund {fund_code}: {e}")
        traceback.print_exc()
        return f"An unexpected server error occurred while processing metric '{metric_name}'. Details: {e}", 500