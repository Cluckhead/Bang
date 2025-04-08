# This file defines the routes for displaying detailed views of specific time-series metrics.
# It handles requests where the user wants to see the data and charts for a single metric
# (like 'Yield' or 'Spread Duration') across all applicable funds.

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
from data_loader import load_and_process_data
from metric_calculator import calculate_latest_metrics

# Define the blueprint for metric routes, using '/metric' as the URL prefix
metric_bp = Blueprint('metric', __name__, url_prefix='/metric')

@metric_bp.route('/<metric_name>')
def metric_page(metric_name):
    """Renders the detailed page (`metric_page_js.html`) for a specific metric.

    This view takes the display name of a metric (e.g., 'Yield') from the URL,
    finds the corresponding data file (e.g., 'ts_Yield.csv'), and performs the following:
    1. Loads and processes the data using `data_loader.load_and_process_data`.
    2. Calculates summary metrics (latest value, change, Z-score, etc.) for each fund code
       within that metric using `metric_calculator.calculate_latest_metrics`.
    3. Identifies funds that might have missing data for the latest period (based on NaN Z-scores).
    4. Prepares data specifically for charting with Chart.js:
       - Extracts historical time-series data (dates and values) for the benchmark and each fund column
         for every fund code.
       - Packages this historical data along with the calculated summary metrics and a flag indicating
         if data was missing into a dictionary structure (`charts_data_for_js`).
    5. Converts the prepared data structure into a JSON string.
    6. Renders the `metric_page_js.html` template, passing:
       - The `metric_name` (for display).
       - The JSON string (`charts_data_json`) containing all data needed by the JavaScript.
       - The overall latest date found in the data.
       - A DataFrame (`missing_funds`) containing rows for funds flagged as potentially missing data.
       - The names of the fund and benchmark columns.
    This allows the template and its associated JavaScript to dynamically generate tables and charts
    for the selected metric.
    """
    # metric_name is the display name (e.g., 'Spread Duration')
    # Prepend 'ts_' to get the actual filename base
    metric_filename_base = f"ts_{metric_name}"
    filename = f"{metric_filename_base}.csv"

    fund_code = 'N/A' # Initialize for potential use in exception handling
    try:
        print(f"Loading data for display metric '{metric_name}' from file '{filename}'...")
        # Load data using the filename with the prefix
        df, fund_cols, benchmark_col = load_and_process_data(filename)
        latest_date_overall = df.index.get_level_values(0).max()

        # Calculate metrics (function doesn't need display name)
        latest_metrics = calculate_latest_metrics(df, fund_cols, benchmark_col)

        # Determine missing funds based on ANY NaN Change Z-score
        # Construct the list of all possible Change Z-Score columns
        all_cols_for_z = []
        if benchmark_col: # Check if benchmark_col is not None
            all_cols_for_z.append(benchmark_col)
        all_cols_for_z.extend(fund_cols)

        z_score_cols = [f'{col} Change Z-Score' for col in all_cols_for_z
                        if f'{col} Change Z-Score' in latest_metrics.columns]

        if not z_score_cols:
            print(f"Warning: No 'Change Z-Score' columns found in latest_metrics for {metric_name} (from {filename})")
            # Fallback: Check for missing Latest Value if Z-score is absent
            latest_val_cols = [f'{col} Latest Value' for col in all_cols_for_z
                               if f'{col} Latest Value' in latest_metrics.columns]
            if latest_val_cols:
                 missing_latest = latest_metrics[latest_metrics[latest_val_cols].isna().any(axis=1)]
            else:
                 # If neither Z-score nor Latest Value columns exist, create an empty DataFrame
                 missing_latest = pd.DataFrame(index=latest_metrics.index)
        else:
             # If Z-score columns exist, use them to identify missing data
             missing_latest = latest_metrics[latest_metrics[z_score_cols].isna().any(axis=1)]

        # --- Prepare data for JavaScript --- 
        charts_data_for_js = {}
        for fund_code in latest_metrics.index:
            # Retrieve historical data for the specific fund (needed for charts)
            # Use .copy() to avoid potential warnings
            fund_hist_data = df.xs(fund_code, level=1).sort_index().copy()

            # Filter to include only business days (Mon-Fri)
            if isinstance(fund_hist_data.index, pd.DatetimeIndex):
                fund_hist_data = fund_hist_data[fund_hist_data.index.dayofweek < 5]
            else:
                print(f"Warning: Index for {fund_code} in {metric_name} is not DatetimeIndex, skipping business day filter.")

            # Retrieve the calculated latest metrics (flattened row) for this fund
            fund_latest_metrics_row = latest_metrics.loc[fund_code]

            # Check if this fund was flagged as missing (based on Z-score or fallback)
            is_missing_latest = fund_code in missing_latest.index

            # Prepare labels (dates) for the chart
            labels = fund_hist_data.index.strftime('%Y-%m-%d').tolist()
            datasets = []

            # Create datasets for the chart (raw values)
            # Add benchmark dataset
            if benchmark_col in fund_hist_data.columns:
                # Replace NaN with 0 for JSON compatibility
                bench_values = fund_hist_data[benchmark_col].round(3).fillna(0).tolist()
                datasets.append({
                    'label': benchmark_col,
                    'data': bench_values,
                    'borderColor': 'black', 'backgroundColor': 'grey',
                    'borderDash': [5, 5], 'tension': 0.1
                })
            # Add dataset for each fund column
            for i, fund_col in enumerate(fund_cols):
                 if fund_col in fund_hist_data.columns:
                    # Replace NaN with 0 for JSON compatibility
                    fund_values = fund_hist_data[fund_col].round(3).fillna(0).tolist()
                    color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
                    datasets.append({
                        'label': fund_col,
                        'data': fund_values,
                        'borderColor': color, 'backgroundColor': color + '40',
                        'tension': 0.1
                    })

            # Convert metrics row to dictionary, replacing NaN with 0
            fund_latest_metrics_dict = fund_latest_metrics_row.round(3).fillna(0).to_dict()

            # Assemble data for JS
            charts_data_for_js[fund_code] = {
                'labels': labels,
                'datasets': datasets,
                'metrics': fund_latest_metrics_dict,
                'is_missing_latest': is_missing_latest,
                'fund_column_names': fund_cols,
                'benchmark_column_name': benchmark_col
            }

        # Render the template, passing the *display name* (metric_name) for the title
        return render_template('metric_page_js.html',
                               metric_name=metric_name, # Pass display name for title
                               charts_data_json=jsonify(charts_data_for_js).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y'),
                               missing_funds=missing_latest,
                               fund_col_names = fund_cols,
                               benchmark_col_name = benchmark_col)

    except FileNotFoundError:
        # Use the display name in the error message for user clarity
        return f"Error: Data file for metric '{metric_name}' (expected: '{filename}') not found.", 404
    except ValueError as ve:
        # Use display name in error message
        print(f"Value Error processing {metric_name} (from {filename}): {ve}")
        return f"Error processing {metric_name}: {ve}", 400
    except Exception as e:
        # Use display name in error message
        print(f"Error processing {metric_name} (from {filename}) for fund {fund_code}: {e}")
        traceback.print_exc()
        return f"An error occurred processing {metric_name}: {e}", 500