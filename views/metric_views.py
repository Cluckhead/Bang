"""
# views/metric_views.py
# This file contains the Blueprint for the metric-specific routes (from ts_ files).
"""

from flask import Blueprint, render_template, jsonify
import os
import pandas as pd
import numpy as np
import traceback

# Import necessary functions from parent directory modules
from data_loader import load_and_process_data
from metric_calculator import calculate_latest_metrics

# Import constants from the main app or a config file
from app import DATA_FOLDER, COLOR_PALETTE 

# Create the Blueprint
metric_bp = Blueprint('metric_bp', __name__,
                      template_folder='../templates',
                      static_folder='../static')

@metric_bp.route('/metric/<metric_name>')
def metric_page(metric_name):
    """Renders the page for a specific metric (identified by display name) from a ts_ file."""
    # metric_name is the display name (e.g., 'Spread Duration')
    # Prepend 'ts_' to get the actual filename base
    metric_filename_base = f"ts_{metric_name}" 
    filename = f"{metric_filename_base}.csv"
    data_filepath = os.path.join(DATA_FOLDER, filename)
    
    fund_code = 'N/A' # Initialize for potential use in exception handling
    try:
        print(f"Loading data for display metric '{metric_name}' from file '{filename}'...")
        # Load data using ONLY the filename (let loader handle path construction)
        # df, fund_cols, benchmark_col = load_and_process_data(data_filepath)
        df, fund_cols, benchmark_col = load_and_process_data(filename)
        latest_date_overall = df.index.get_level_values(0).max()
        
        # Calculate metrics (function doesn't need display name)
        latest_metrics = calculate_latest_metrics(df, fund_cols, benchmark_col)
        
        # Determine missing funds based on ANY NaN Change Z-score
        # Construct the list of all possible Change Z-Score columns
        all_cols_for_z = ([benchmark_col] if benchmark_col else []) + fund_cols # Handle case where benchmark_col might be None
        z_score_cols = [f'{col} Change Z-Score' for col in all_cols_for_z 
                        if f'{col} Change Z-Score' in latest_metrics.columns]
        
        missing_latest = pd.DataFrame(index=latest_metrics.index) # Initialize as empty
        if not z_score_cols:
            print(f"Warning: No 'Change Z-Score' columns found in latest_metrics for {metric_name} (from {filename})")
            latest_val_cols = [f'{col} Latest Value' for col in all_cols_for_z 
                               if f'{col} Latest Value' in latest_metrics.columns]
            if latest_val_cols:
                 # Check for NaNs in 'Latest Value' columns if Z-scores are missing
                 missing_mask = latest_metrics[latest_val_cols].isna().any(axis=1)
                 missing_latest = latest_metrics[missing_mask]
        else:
             # Check for NaNs in existing Z-score columns
             missing_mask = latest_metrics[z_score_cols].isna().any(axis=1)
             missing_latest = latest_metrics[missing_mask]

        # --- Prepare data for JavaScript --- 
        charts_data_for_js = {}
        for fund_code in latest_metrics.index: 
            # Retrieve historical data for the specific fund (needed for charts)
            # Use .copy() to avoid potential warnings
            try:
                # Use .loc for potentially multi-level index access if df structure changes
                fund_hist_data = df.xs(fund_code, level=1).sort_index().copy()
            except KeyError:
                print(f"Warning: Fund code '{fund_code}' not found at level 1 of the index for metric '{metric_name}'. Skipping chart generation for this fund.")
                continue # Skip to the next fund code
                
            # Retrieve the calculated latest metrics (flattened row) for this fund
            # This now contains keys like 'Benchmark Spread Duration Latest Value', 'Fund Spread Duration Change Z-Score', etc.
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            
            # Check if this fund was flagged as missing
            is_missing_latest = fund_code in missing_latest.index

            # Prepare labels (dates) for the chart
            labels = fund_hist_data.index.strftime('%Y-%m-%d').tolist()
            datasets = []

            # Create datasets for the chart (raw values)
            # Add benchmark dataset
            if benchmark_col and benchmark_col in fund_hist_data.columns:
                bench_values = fund_hist_data[benchmark_col].round(3).fillna(np.nan).tolist()
                datasets.append({
                    'label': benchmark_col,
                    'data': bench_values,
                    'borderColor': 'black', 'backgroundColor': 'grey',
                    'borderDash': [5, 5], 'tension': 0.1
                })
            # Add dataset for each fund column
            for i, fund_col in enumerate(fund_cols):
                 if fund_col in fund_hist_data.columns:
                    fund_values = fund_hist_data[fund_col].round(3).fillna(np.nan).tolist()
                    color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
                    datasets.append({
                        'label': fund_col,
                        'data': fund_values,
                        'borderColor': color, 'backgroundColor': color + '40',
                        'tension': 0.1
                    })
            
            # Convert metrics row to dictionary (handle potential NaNs)
            fund_latest_metrics_dict = fund_latest_metrics_row.round(3).where(pd.notnull(fund_latest_metrics_row), None).to_dict()
            
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
                               missing_funds=missing_latest, # Pass the DataFrame of missing funds
                               fund_col_names = fund_cols, 
                               benchmark_col_name = benchmark_col)

    except FileNotFoundError:
        # Use the display name in the error message for user clarity
        print(f"Error: Data file '{filename}' not found for metric '{metric_name}'.")
        return f"Error: Data file for metric '{metric_name}' (expected: '{filename}') not found.", 404 
    except ValueError as ve:
        # Use display name in error message
        print(f"Value Error processing {metric_name} (from {filename}): {ve}")
        traceback.print_exc() # Log traceback for value errors too
        return f"Error processing {metric_name}: {ve}", 400
    except Exception as e:
        # Use display name in error message
        print(f"Error processing {metric_name} (from {filename}) for fund {fund_code}: {e}")
        traceback.print_exc()
        return f"An error occurred processing {metric_name}: {e}", 500 