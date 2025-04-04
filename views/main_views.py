"""
# views/main_views.py
# This file contains the Blueprint for the main application routes (e.g., the index page).
"""

from flask import Blueprint, render_template
import os
import pandas as pd
import traceback

# Import necessary functions from parent directory modules
from data_loader import load_and_process_data
from metric_calculator import calculate_latest_metrics

# Import DATA_FOLDER from the main app file
# This assumes app.py is in the parent directory
# A config file would be a more robust solution for larger apps
from app import DATA_FOLDER

# Create the Blueprint
main_bp = Blueprint('main_bp', __name__,
                    template_folder='../templates', # Point to templates relative to app.py location
                    static_folder='../static')    # Point to static relative to app.py location

@main_bp.route('/')
def index():
    """Renders the main dashboard page with a summary table of Z-scores for ts_ files."""
    # Find only files starting with ts_ and ending with .csv
    try:
        all_files = os.listdir(DATA_FOLDER)
    except FileNotFoundError:
        print(f"Error: Data folder '{DATA_FOLDER}' not found.")
        return "Error: Data folder not found.", 500
    
    files = [f for f in all_files if f.startswith('ts_') and f.endswith('.csv')]
    
    # Create two lists: one for filenames (with ts_), one for display (without ts_)
    metric_filenames = sorted([os.path.splitext(f)[0] for f in files])
    metric_display_names = sorted([name[3:] for name in metric_filenames]) # Remove 'ts_' prefix
    
    all_z_scores_list = []
    # Store the unique combined column names for the summary table header
    processed_summary_columns = [] 

    print("Starting Change Z-score aggregation for dashboard (ts_ files only)...")

    # Iterate using the filenames with prefix
    for metric_filename in metric_filenames:
        filename = f"{metric_filename}.csv"
        # Get the corresponding display name for this file
        display_name = metric_filename[3:] 
        
        try:
            print(f"Processing {filename}...")
            # Pass ONLY the filename to the loader function
            df, fund_cols, benchmark_col = load_and_process_data(filename)

            # Skip if no benchmark AND no fund columns identified
            if not benchmark_col and not fund_cols:
                 print(f"Warning: No benchmark or fund columns identified in {filename}. Skipping.")
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
                    print(f"Warning: No columns to check for Z-scores in {filename} despite loading data.")
                    continue

                print(f"Checking for Z-scores for columns: {columns_to_check} in metric {display_name}")
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
                        print(f"  -> Extracted: {summary_col_name}")
                    else:
                        print(f"  -> Z-score column '{z_score_col_name}' not found.")
                
                if not found_z_for_metric:
                    print(f"Warning: No Z-score columns found for any checked column in metric {display_name} (from {filename}).")

            else:
                 print(f"Warning: Could not calculate latest_metrics for {filename}. Skipping Z-score extraction.")

        except FileNotFoundError:
            # This specific error is handled by the loader, but catch again just in case
            print(f"Error: Data file '{filename}' not found during dashboard aggregation.") 
        except ValueError as ve:
            print(f"Value Error processing {metric_filename}: {ve}") # Log with filename
        except Exception as e:
            print(f"Error processing {metric_filename} during dashboard aggregation: {e}") # Log with filename
            traceback.print_exc()

    # Combine all Z-score Series/DataFrames into one
    summary_df = pd.DataFrame()
    if all_z_scores_list:
        try:
            summary_df = pd.concat(all_z_scores_list, axis=1) 
            # Ensure the columns are in the order they were discovered
            if processed_summary_columns: 
                 # Handle potential missing columns if a file failed processing midway
                 cols_available_in_summary = [col for col in processed_summary_columns if col in summary_df.columns]
                 summary_df = summary_df[cols_available_in_summary] 
                 # Update the list of columns to only those actually present
                 processed_summary_columns = cols_available_in_summary 
            print("Successfully combined Change Z-scores.")
            print(f"Summary DF columns: {summary_df.columns.tolist()}")
        except Exception as e_concat:
            print(f"Error combining Z-scores: {e_concat}")
            traceback.print_exc()
            # Set summary_df back to empty if concat fails
            summary_df = pd.DataFrame()
            processed_summary_columns = []
    else:
        print("No Change Z-scores could be extracted for the summary.")

    return render_template('index.html', 
                           metrics=metric_display_names, # Still used for top-level metric links
                           summary_data=summary_df,
                           summary_metrics=processed_summary_columns) # Pass the NEW list of combined column names 