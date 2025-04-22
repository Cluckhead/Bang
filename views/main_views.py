# This file defines the routes related to the main, top-level views of the application.
# It primarily handles the dashboard or index page.

"""
Blueprint for main application routes, like the index page.
"""
from flask import Blueprint, render_template, current_app
import os
import pandas as pd
import traceback

# Import necessary functions/constants from other modules
# Removed: from config import DATA_FOLDER
from data_loader import load_and_process_data
from metric_calculator import calculate_latest_metrics

# Define the blueprint for main routes
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Renders the main dashboard page (`index.html`).

    This view performs the following steps:
    1. Scans the configured data directory for time-series metric files (prefixed with `ts_`).
    2. For each `ts_` file found:
        a. Loads and processes the data using `data_loader.load_and_process_data`,
           providing the configured data directory path.
        b. Calculates metrics (including Z-scores) using `metric_calculator.calculate_latest_metrics`.
        c. Extracts the 'Change Z-Score' columns for both the benchmark and any specific fund columns.
    3. Aggregates all extracted 'Change Z-score' columns from all files into a single pandas DataFrame (`summary_df`).
    4. Creates unique column names for the summary table by combining the original column name and the metric file name
       (e.g., 'Benchmark - Yield', 'FUND_A - Duration').
    5. Passes the list of available metric display names (filenames without `ts_`) and the aggregated Z-score
       DataFrame (`summary_df`) along with its corresponding column headers (`summary_metrics`) to the `index.html` template.
    This allows the dashboard to display a consolidated view of the most recent significant changes across all metrics.
    """
    # Retrieve the absolute data folder path from the app context
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    current_app.logger.info(f"Scanning data folder for dashboard: {data_folder}")

    # Find only files starting with ts_ and ending with .csv in the configured data folder
    try:
        files = [f for f in os.listdir(data_folder) if f.startswith('ts_') and f.endswith('.csv')]
    except FileNotFoundError:
        current_app.logger.error(f"Configured DATA_FOLDER does not exist: {data_folder}")
        files = []
    except Exception as e:
        current_app.logger.error(f"Error listing files in data folder {data_folder}: {e}")
        files = []

    # Create two lists: one for filenames (with ts_), one for display (without ts_)
    metric_filenames = sorted([os.path.splitext(f)[0] for f in files])
    metric_display_names = sorted([name[3:] for name in metric_filenames]) # Remove 'ts_' prefix

    all_z_scores_list = []
    # Store the unique combined column names for the summary table header
    processed_summary_columns = []

    current_app.logger.info("Starting Change Z-score aggregation for dashboard (ts_ files only)...")

    # Iterate using the filenames with prefix
    for metric_filename in metric_filenames:
        filename = f"{metric_filename}.csv"
        # Get the corresponding display name for this file
        display_name = metric_filename[3:]

        try:
            current_app.logger.info(f"Processing {filename}...")
            # Unpack all 6 values, but only use the primary ones for the dashboard summary
            # Pass the absolute data folder path to the loader
            df, fund_cols, benchmark_col, _sec_df, _sec_fund_cols, _sec_bench_col = load_and_process_data(
                primary_filename=filename,
                data_folder_path=data_folder # Pass the absolute path
            )

            # Check if data loading failed (df will be None)
            if df is None:
                 current_app.logger.warning(f"Warning: Failed to load data for {filename}. Skipping.")
                 continue # Skip this file if loading failed

            # Skip if no benchmark AND no fund columns identified
            if not benchmark_col and not fund_cols:
                 current_app.logger.warning(f"Warning: No benchmark or fund columns identified in {filename}. Skipping.")
                 continue

            # Calculate metrics using the current function
            latest_metrics = calculate_latest_metrics(df, fund_cols, benchmark_col)

            # --- Extract Change Z-score for ALL columns (benchmark + funds) --- 
            if not latest_metrics.empty:
                columns_to_check = []
                if benchmark_col:
                    columns_to_check.append(benchmark_col)
                if fund_cols:
                    columns_to_check.extend(fund_cols)

                if not columns_to_check:
                    current_app.logger.warning(f"Warning: No columns to check for Z-scores in {filename} despite loading data.")
                    continue

                current_app.logger.info(f"Checking for Z-scores for columns: {columns_to_check} in metric {display_name}")
                found_z_for_metric = False
                for original_col_name in columns_to_check:
                    z_score_col_name = f'{original_col_name} Change Z-Score'

                    if z_score_col_name in latest_metrics.columns:
                        # Create a unique name for the summary table column
                        summary_col_name = f"{original_col_name} - {display_name}"

                        # Extract and rename
                        metric_z_scores = latest_metrics[[z_score_col_name]].rename(columns={z_score_col_name: summary_col_name})
                        all_z_scores_list.append(metric_z_scores)

                        # Add the unique column name to our list if not already present (preserves order of discovery)
                        if summary_col_name not in processed_summary_columns:
                             processed_summary_columns.append(summary_col_name)
                        found_z_for_metric = True
                        current_app.logger.info(f"  -> Extracted: {summary_col_name}")
                    else:
                        current_app.logger.info(f"  -> Z-score column '{z_score_col_name}' not found.")

                if not found_z_for_metric:
                    current_app.logger.warning(f"Warning: No Z-score columns found for any checked column in metric {display_name} (from {filename}).")

            else:
                 current_app.logger.warning(f"Warning: Could not calculate latest_metrics for {filename}. Skipping Z-score extraction.")

        except FileNotFoundError:
            current_app.logger.error(f"Error: Data file '{filename}' not found.")
        except ValueError as ve:
            current_app.logger.error(f"Value Error processing {metric_filename}: {ve}") # Log with filename
        except Exception as e:
            current_app.logger.error(f"Error processing {metric_filename} during dashboard aggregation: {e}") # Log with filename
            traceback.print_exc()

    # Combine all Z-score Series/DataFrames into one
    summary_df = pd.DataFrame()
    if all_z_scores_list:
        summary_df = pd.concat(all_z_scores_list, axis=1)
        # Ensure the columns are in the order they were discovered
        if processed_summary_columns:
             # Handle potential missing columns if a file failed processing midway
             cols_available_in_summary = [col for col in processed_summary_columns if col in summary_df.columns]
             summary_df = summary_df[cols_available_in_summary]
             # Update the list of columns to only those actually present
             processed_summary_columns = cols_available_in_summary
        current_app.logger.info("Successfully combined Change Z-scores.")
        current_app.logger.info(f"Summary DF columns: {summary_df.columns.tolist()}")
    else:
        current_app.logger.info("No Change Z-scores could be extracted for the summary.")

    return render_template('index.html',
                           metrics=metric_display_names, # Still used for top-level metric links
                           summary_data=summary_df,
                           summary_metrics=processed_summary_columns) # Pass the NEW list of combined column names