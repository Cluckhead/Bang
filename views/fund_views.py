"""Blueprint for fund-specific routes, including duration details and a general fund overview page."""

from flask import Blueprint, render_template, current_app, jsonify
import os
import pandas as pd
import traceback
import logging # Added for logging
import glob # Added for finding files
import re # Added for extracting metric name

# Import necessary functions from other modules
from config import DATA_FOLDER
from utils import _is_date_like, parse_fund_list # Import required utils
# Updated import to include data loader
from data_loader import load_and_process_data

# Define the blueprint
fund_bp = Blueprint('fund', __name__, url_prefix='/fund')

@fund_bp.route('/duration_details/<fund_code>') # Corresponds to /fund/duration_details/...
def fund_duration_details(fund_code):
    """Renders a page showing duration changes for securities held by a specific fund."""
    duration_filename = "sec_duration.csv"
    data_filepath = os.path.join(DATA_FOLDER, duration_filename)
    print(f"--- Requesting Duration Details for Fund: {fund_code} --- File: {duration_filename}")

    if not os.path.exists(data_filepath):
        print(f"Error: Duration file '{duration_filename}' not found.")
        return f"Error: Data file '{duration_filename}' not found.", 404

    try:
        # 1. Load the duration data (only header first for column identification)
        header_df = pd.read_csv(data_filepath, nrows=0, encoding='utf-8')
        all_cols = [col.strip() for col in header_df.columns.tolist()]

        # Define ID column (specific to this file/route)
        id_col_name = 'Security Name' # Assuming this remains the ID for this specific file
        if id_col_name not in all_cols:
            print(f"Error: Expected ID column '{id_col_name}' not found in {duration_filename}.")
            return f"Error: Required ID column '{id_col_name}' not found in '{duration_filename}'.", 500

        # 2. Identify static and date columns dynamically
        date_cols = []
        static_cols = []
        for col in all_cols:
            if col == id_col_name:
                continue # Skip the ID column
            if _is_date_like(col): # Use the helper function from utils
                date_cols.append(col)
            else:
                static_cols.append(col) # Treat others as static

        print(f"Dynamically identified Static Cols: {static_cols}")
        print(f"Dynamically identified Date Cols (first 5): {date_cols[:5]}...")

        if not date_cols or len(date_cols) < 2:
             print("Error: Not enough date columns found in duration file to calculate change.")
             return f"Error: Insufficient date columns in '{duration_filename}' to calculate change.", 500

        # Now read the full data
        df = pd.read_csv(data_filepath, encoding='utf-8')
        df.columns = df.columns.str.strip() # Strip again after full read

        # Ensure the Funds column exists (still needed for filtering)
        funds_col = 'Funds' # Keep this assumption for now as it's key to filtering
        if funds_col not in static_cols:
             print(f"Warning: Expected column '{funds_col}' for filtering not found among static columns.")
             # Decide how to handle this - error or proceed without fund filtering? Let's error for now.
             return f"Error: Required column '{funds_col}' for fund filtering not found.", 500

        # Ensure date columns are sortable (attempt conversion if needed, basic check)
        try:
            # Check and sort date columns using the correct YYYY-MM-DD format
            pd.to_datetime(date_cols, format='%Y-%m-%d', errors='raise')
            date_cols = sorted(date_cols, key=lambda d: pd.to_datetime(d, format='%Y-%m-%d'))
            print(f"Identified and sorted date columns (YYYY-MM-DD): {date_cols[-5:]} (last 5 shown)")
        except ValueError:
            print("Warning: Could not parse all date columns using YYYY-MM-DD format. Using original order.")
            # Fallback remains, but hopefully won't be needed as often

        # Identify last two date columns based on sorted list (or original if parsing failed)
        if len(date_cols) < 2: # Double check after potential parsing failure
            return f"Error: Insufficient valid date columns in '{duration_filename}' to calculate change after sorting attempt.", 500
        last_date_col = date_cols[-1]
        second_last_date_col = date_cols[-2]
        print(f"Using dates for change calculation: {second_last_date_col} and {last_date_col}")

        # Ensure the relevant date columns are numeric for calculation
        df[last_date_col] = pd.to_numeric(df[last_date_col], errors='coerce')
        df[second_last_date_col] = pd.to_numeric(df[second_last_date_col], errors='coerce')

        # 3. Filter by Fund Code
        # Apply the parsing function from utils to the 'Funds' column
        fund_lists = df['Funds'].apply(parse_fund_list)
        # Create a boolean mask to filter rows where the fund_code is in the parsed list
        mask = fund_lists.apply(lambda funds: fund_code in funds)
        filtered_df = df[mask].copy() # Use copy to avoid SettingWithCopyWarning

        if filtered_df.empty:
            print(f"No securities found for fund '{fund_code}' in {duration_filename}.")
            # Render a template indicating no data found for this fund
            return render_template('fund_duration_details.html',
                                   fund_code=fund_code,
                                   securities_data=[],
                                   column_order=[],
                                   id_col_name=None,
                                   message=f"No securities found held by fund '{fund_code}' in {duration_filename}.")

        print(f"Found {len(filtered_df)} securities for fund '{fund_code}'. Calculating changes...")

        # 4. Calculate 1-day Change
        change_col_name = '1 Day Duration Change'
        filtered_df[change_col_name] = filtered_df[last_date_col] - filtered_df[second_last_date_col]

        # 5. Sort by Change (descending, NaN last)
        filtered_df.sort_values(by=change_col_name, ascending=False, na_position='last', inplace=True)
        print(f"Sorted securities by {change_col_name}.")

        # 6. Prepare data for template
        # Select columns for display - use the dynamically identified static_cols
        # ID column is already defined as id_col_name
        # Filter static_cols to ensure they exist in the filtered_df after operations
        existing_static_cols = [col for col in static_cols if col in filtered_df.columns]
        display_cols = [id_col_name] + existing_static_cols + [second_last_date_col, last_date_col, change_col_name]
        final_col_order = [col for col in display_cols if col in filtered_df.columns] # Ensure only existing columns are kept

        securities_data_list = filtered_df[final_col_order].round(3).to_dict(orient='records')
        # Handle potential NaN values for template rendering
        for row in securities_data_list:
             for key, value in row.items():
                 if pd.isna(value):
                     row[key] = None

        print(f"Final column order for display: {final_col_order}")

        return render_template('fund_duration_details.html',
                               fund_code=fund_code,
                               securities_data=securities_data_list,
                               column_order=final_col_order,
                               id_col_name=id_col_name,
                               message=None)

    except FileNotFoundError:
         return f"Error: Data file '{duration_filename}' not found.", 404
    except Exception as e:
        print(f"Error processing duration details for fund {fund_code}: {e}")
        traceback.print_exc()
        return f"An error occurred processing duration details for fund {fund_code}: {e}", 500

# --- New Route for Fund Detail Page ---
@fund_bp.route('/<fund_code>')
def fund_detail(fund_code):
    """Renders a page displaying all available time-series charts for a specific fund,
       optionally including comparison data from sp_ts_* files."""
    current_app.logger.info(f"--- Requesting Detail Page for Fund: {fund_code} ---")
    all_chart_data = []
    available_metrics = []
    processed_files = 0
    skipped_files = 0
    error_messages = [] # Collect specific errors

    try:
        # Find all primary time-series files
        ts_files_pattern = os.path.join(DATA_FOLDER, 'ts_*.csv')
        ts_files = glob.glob(ts_files_pattern)
        # Exclude sp_ts files initially, handle them later
        ts_files = [f for f in ts_files if not os.path.basename(f).startswith('sp_ts_')]
        current_app.logger.info(f"Found {len(ts_files)} primary ts_ files: {[os.path.basename(f) for f in ts_files]}")

        if not ts_files:
            current_app.logger.warning("No primary ts_*.csv files found in Data folder.")
            return render_template('fund_detail_page.html',
                                   fund_code=fund_code,
                                   chart_data_json='[]',
                                   available_metrics=[],
                                   message="No time-series data files (ts_*.csv) found.")

        # Process each file
        for file_path in ts_files:
            filename = os.path.basename(file_path)
            # Extract metric name
            match = re.match(r'ts_(.+?)(?:_processed)?\.csv', filename, re.IGNORECASE)
            if not match:
                current_app.logger.warning(f"Could not extract metric name from filename: {filename}. Skipping.")
                skipped_files += 1
                continue

            metric_name_raw = match.group(1) # Keep raw name for SP file lookup
            metric_name_display = metric_name_raw.replace('_', ' ').title()
            current_app.logger.info(f"\\nProcessing {filename} for metric: {metric_name_display}")

            # --- Prepare SP file path ---
            sp_filename = f"sp_{filename}"
            sp_file_path = os.path.join(DATA_FOLDER, sp_filename)
            sp_df = None
            sp_fund_col_name = None
            sp_load_error = None

            # --- Load primary data ---
            df = None
            fund_cols = None
            benchmark_col = None
            primary_load_error = None
            try:
                load_result = load_and_process_data(filename, data_folder=DATA_FOLDER)
                df = load_result[0]
                fund_cols = load_result[1]
                benchmark_col = load_result[2]

                if df is None or df.empty:
                    current_app.logger.warning(f"No data loaded or DataFrame empty for {filename}. Skipping.")
                    skipped_files += 1
                    continue

                if 'Code' not in df.index.names:
                     current_app.logger.error(f"Index level 'Code' not found in DataFrame loaded from {filename}. Index: {df.index.names}. Skipping.")
                     error_messages.append(f"Failed to process {filename}: Missing 'Code' index level.")
                     skipped_files += 1
                     continue

            except Exception as e:
                current_app.logger.error(f"Error loading primary file {filename}: {e}", exc_info=False)
                primary_load_error = f"Error loading {filename}: {e}"
                error_messages.append(primary_load_error)
                skipped_files += 1
                # Continue processing other files, but skip this metric
                continue # Skip to next ts_file

            # --- Load SP data if primary load was successful and SP file exists ---
            if primary_load_error is None and os.path.exists(sp_file_path):
                current_app.logger.info(f"Found corresponding SP file: {sp_filename}. Attempting to load.")
                try:
                    sp_load_result = load_and_process_data(sp_filename, data_folder=DATA_FOLDER)
                    sp_df = sp_load_result[0]
                    sp_fund_cols = sp_load_result[1] # Assuming same structure for fund cols
                    # SP files typically don't have benchmarks in this context, ignore sp_load_result[2]
                    # --- Correction: Let's check for SP benchmark column too ---
                    sp_benchmark_col = sp_load_result[2] # Get potential SP benchmark col name

                    if sp_df is None or sp_df.empty:
                        current_app.logger.warning(f"No data loaded or DataFrame empty for SP file {sp_filename}.")
                        sp_df = None # Ensure sp_df is None if empty
                    elif 'Code' not in sp_df.index.names:
                         current_app.logger.error(f"Index level 'Code' not found in DataFrame loaded from SP file {sp_filename}. Index: {sp_df.index.names}.")
                         sp_df = None # Ensure sp_df is None if index is wrong
                         sp_load_error = f"SP file {sp_filename} missing 'Code' index."
                         error_messages.append(sp_load_error)
                    else:
                        # Find the fund column name in the SP data
                        sp_fund_col_name = next((col for col in sp_fund_cols if col in sp_df.columns), None)
                        if not sp_fund_col_name:
                             current_app.logger.warning(f"Could not find fund data column in SP file {sp_filename}.")
                             sp_df = None # Cannot use this SP data without fund column
                        # We keep sp_df if benchmark exists, even if fund doesn't

                except Exception as e:
                    current_app.logger.error(f"Error loading SP file {sp_filename}: {e}", exc_info=False)
                    sp_load_error = f"Error loading SP file {sp_filename}: {e}"
                    error_messages.append(sp_load_error)
                    sp_df = None # Ensure sp_df is None on error

            # --- Filter primary data for the fund ---
            fund_mask = df.index.get_level_values('Code') == fund_code
            fund_df = df[fund_mask]

            if fund_df.empty:
                current_app.logger.info(f"Fund code '{fund_code}' not found in primary data from {filename}. Skipping metric.")
                skipped_files += 1 # Processed file, but no data for this fund
                continue # Skip to next ts_file

            current_app.logger.info(f"Fund code '{fund_code}' found in primary data. Preparing chart data for '{metric_name_display}'...")
            available_metrics.append(metric_name_display) # Use display name

            # Drop the 'Code' level now we've filtered
            fund_df = fund_df.droplevel('Code')

            # --- Filter SP data for the fund (if loaded) ---
            sp_fund_df = None
            if sp_df is not None:
                sp_fund_mask = sp_df.index.get_level_values('Code') == fund_code
                sp_fund_df = sp_df[sp_fund_mask]
                if not sp_fund_df.empty:
                    sp_fund_df = sp_fund_df.droplevel('Code')
                    current_app.logger.info(f"Fund code '{fund_code}' found in SP data from {sp_filename}.")
                else:
                    current_app.logger.info(f"Fund code '{fund_code}' *not* found in SP data from {sp_filename}.")
                    sp_fund_df = None # Treat as if no SP data for this fund

            # --- Prepare chart data structure ---
            # Use the primary fund_df index as the master list of labels
            # Align SP data to this index later if needed
            chart_labels = fund_df.index.strftime('%Y-%m-%d').tolist()
            chart_data = {
                'metricName': metric_name_display, # Use display name
                'labels': chart_labels,
                'datasets': []
            }

            # Add primary fund dataset
            fund_col_name = next((col for col in fund_cols if col in fund_df.columns), None)
            if fund_col_name:
                # Reindex to ensure consistent length and alignment, fill missing with None
                fund_values = fund_df[fund_col_name].reindex(fund_df.index).where(pd.notna, None).tolist()
                chart_data['datasets'].append({
                    'label': f"{fund_code} {metric_name_display}",
                    'data': fund_values,
                    'borderColor': current_app.config['COLOR_PALETTE'][0 % len(current_app.config['COLOR_PALETTE'])],
                    'tension': 0.1,
                    'pointRadius': 1,
                    'borderWidth': 1.5,
                    'isSpData': False # Explicitly mark as not SP
                })
            else:
                current_app.logger.warning(f"Warning: Could not find primary fund data column ({fund_cols}) in {filename} for fund {fund_code}")

            # Add benchmark dataset (from primary data)
            if benchmark_col and benchmark_col in fund_df.columns:
                # Reindex to ensure consistent length and alignment
                bench_values = fund_df[benchmark_col].reindex(fund_df.index).where(pd.notna, None).tolist()
                chart_data['datasets'].append({
                    'label': f"Benchmark ({benchmark_col})",
                    'data': bench_values,
                    'borderColor': current_app.config['COLOR_PALETTE'][1 % len(current_app.config['COLOR_PALETTE'])],
                    'tension': 0.1,
                    'pointRadius': 1,
                    'borderDash': [5, 5],
                    'borderWidth': 1,
                    'isSpData': False # Explicitly mark as not SP
                })

            # --- Add SP fund dataset (if available) ---
            if sp_fund_df is not None:
                # Add SP Fund Data (if column exists)
                if sp_fund_col_name:
                    # Reindex SP data to the primary data's date index to ensure alignment for the chart
                    sp_fund_aligned = sp_fund_df[sp_fund_col_name].reindex(fund_df.index)
                    sp_values = sp_fund_aligned.where(pd.notna, None).tolist() # Replace NaN with None for JSON
                    chart_data['datasets'].append({
                        'label': f"{fund_code} {metric_name_display} (SP)",
                        'data': sp_values,
                        'borderColor': current_app.config['COLOR_PALETTE'][2 % len(current_app.config['COLOR_PALETTE'])], # Use a different color
                        'tension': 0.1,
                        'pointRadius': 1,
                        'borderDash': [2, 2], # Different dash style
                        'borderWidth': 1.5,
                        'isSpData': True # Mark this dataset as SP data
                        # 'hidden': True # Optionally start hidden
                    })
                    current_app.logger.info(f"Added SP Fund dataset for metric '{metric_name_display}'.")
                else:
                    current_app.logger.warning(f"SP Fund column ('{sp_fund_cols}') not found in filtered SP data for {sp_filename}, fund {fund_code}.")

                # --- Add SP benchmark dataset (if available) ---
                if sp_benchmark_col and sp_benchmark_col in sp_fund_df.columns:
                    # Reindex SP benchmark data to the primary data's date index
                    sp_bench_aligned = sp_fund_df[sp_benchmark_col].reindex(fund_df.index)
                    sp_bench_values = sp_bench_aligned.where(pd.notna, None).tolist()
                    chart_data['datasets'].append({
                        'label': f"Benchmark ({sp_benchmark_col}) (SP)", # Label appropriately
                        'data': sp_bench_values,
                        'borderColor': current_app.config['COLOR_PALETTE'][3 % len(current_app.config['COLOR_PALETTE'])], # Use another color
                        'tension': 0.1,
                        'pointRadius': 1,
                        'borderDash': [2, 2], # Use dash similar to SP fund
                        'borderWidth': 1,
                        'isSpData': True # Mark this dataset as SP data
                    })
                    current_app.logger.info(f"Added SP Benchmark dataset ('{sp_benchmark_col}') for metric '{metric_name_display}'.")
                elif sp_benchmark_col:
                    current_app.logger.warning(f"SP Benchmark column ('{sp_benchmark_col}') specified but not found in filtered SP data for {sp_filename}, fund {fund_code}.")

            # Only add chart if we have at least one non-empty dataset
            if any(d['data'] for d in chart_data['datasets']):
                all_chart_data.append(chart_data)
                processed_files += 1
            else:
                 current_app.logger.warning(f"No valid datasets generated for metric '{metric_name_display}' from {filename} (and potentially {sp_filename}). Skipping chart.")
                 skipped_files += 1 # Count as skipped if no dataset generated

            # Explicitly remove large dataframes from memory
            del df, fund_df, sp_df, sp_fund_df, load_result
            if 'sp_load_result' in locals(): del sp_load_result
            import gc
            gc.collect()

        # --- After processing all files ---
        current_app.logger.info(f"Finished processing files for fund {fund_code}. Generated charts for: {available_metrics}. Total Processed: {processed_files}, Skipped/No Data/Errors: {skipped_files}")

        if not all_chart_data:
             # Combine specific errors with the generic message if available
             final_message = f"No metrics found with data for fund '{fund_code}'."
             if error_messages:
                 final_message += " Errors encountered: " + "; ".join(error_messages)
             elif skipped_files > 0:
                 final_message += f" ({skipped_files} files skipped or had no data for this fund). Check logs for details."
             current_app.logger.warning(final_message) # Log the final message
             return render_template('fund_detail_page.html',
                                   fund_code=fund_code,
                                   chart_data_json='[]',
                                   available_metrics=[],
                                   message=final_message)

        # Convert chart data to JSON for the template
        chart_data_json = jsonify(all_chart_data).get_data(as_text=True)

        return render_template('fund_detail_page.html',
                               fund_code=fund_code,
                               chart_data_json=chart_data_json,
                               available_metrics=available_metrics,
                               message=None) # No message if data was found

    except Exception as e:
        current_app.logger.error(f"Unexpected error in fund_detail for {fund_code}: {e}", exc_info=True)
        traceback.print_exc()
        # Render the page with an error message
        return render_template('fund_detail_page.html',
                               fund_code=fund_code,
                               chart_data_json='[]',
                               available_metrics=[],
                               message=f"An unexpected error occurred: {e}") 