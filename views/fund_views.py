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
    """Renders a page displaying all available time-series charts for a specific fund."""
    print(f"--- Requesting Detail Page for Fund: {fund_code} ---")
    all_chart_data = []
    available_metrics = []
    processed_files = 0
    skipped_files = 0

    try:
        # Find all time-series files
        ts_files_pattern = os.path.join(DATA_FOLDER, 'ts_*.csv')
        ts_files = glob.glob(ts_files_pattern)
        print(f"Found {len(ts_files)} potential ts_ files: {ts_files}")

        if not ts_files:
            print("No ts_*.csv files found in Data folder.")
            return render_template('fund_detail_page.html',
                                   fund_code=fund_code,
                                   chart_data_json='[]', # Empty JSON array
                                   available_metrics=[],
                                   message="No time-series data files (ts_*.csv) found.")

        # Process each file
        for file_path in ts_files:
            filename = os.path.basename(file_path)
            # Extract metric name from filename (e.g., ts_Yield.csv -> Yield)
            match = re.match(r'ts_(.+?)(?:_processed)?\.csv', filename, re.IGNORECASE)
            if not match:
                print(f"Could not extract metric name from filename: {filename}. Skipping.")
                skipped_files += 1
                continue

            metric_name = match.group(1).replace('_', ' ').title() # Format nicely
            print(f"\nProcessing {filename} for metric: {metric_name}")

            try:
                # Corrected unpacking: Expecting 3 values, not 4
                df, fund_cols, benchmark_col = load_and_process_data(filename, DATA_FOLDER)

                if df is None or df.empty:
                    print(f"No data loaded from {filename}. Skipping.")
                    skipped_files += 1
                    continue

                # Check if the fund_code exists in this metric's data
                if fund_code not in df.index.get_level_values('Code'):
                    print(f"Fund code '{fund_code}' not found in {filename}. Skipping metric.")
                    skipped_files += 1
                    continue

                print(f"Fund code '{fund_code}' found. Preparing chart data for '{metric_name}'...")
                available_metrics.append(metric_name)

                # Filter data for the specific fund
                fund_df = df.loc[pd.IndexSlice[:, fund_code], :]
                fund_df = fund_df.droplevel('Code') # Remove fund code level for easier plotting

                # Prepare chart data structure
                chart_data = {
                    'metricName': metric_name,
                    'labels': fund_df.index.strftime('%Y-%m-%d').tolist(), # X-axis labels (Dates)
                    'datasets': []
                }

                # Add fund dataset (use original column name if available)
                fund_col_name = next((col for col in fund_cols if col in fund_df.columns), None)
                if fund_col_name:
                    fund_values = fund_df[fund_col_name].where(pd.notna(fund_df[fund_col_name]), None).tolist() # Handle NaN for JSON
                    chart_data['datasets'].append({
                        'label': f"{fund_code} {metric_name}",
                        'data': fund_values,
                        'borderColor': current_app.config['COLOR_PALETTE'][0 % len(current_app.config['COLOR_PALETTE'])], # Use first color
                        'tension': 0.1,
                        'pointRadius': 1,
                        'borderWidth': 1.5
                    })
                else:
                    print(f"Warning: Could not find primary fund data column in {filename} for fund {fund_code}")


                # Add benchmark dataset if it exists for this fund
                if benchmark_col and benchmark_col in fund_df.columns:
                    bench_values = fund_df[benchmark_col].where(pd.notna(fund_df[benchmark_col]), None).tolist() # Handle NaN for JSON
                    chart_data['datasets'].append({
                        'label': f"Benchmark ({benchmark_col})",
                        'data': bench_values,
                        'borderColor': current_app.config['COLOR_PALETTE'][1 % len(current_app.config['COLOR_PALETTE'])], # Use second color
                        'tension': 0.1,
                        'pointRadius': 1,
                        'borderDash': [5, 5], # Dashed line for benchmark
                        'borderWidth': 1
                    })

                # Only add chart if we have at least one dataset
                if chart_data['datasets']:
                    all_chart_data.append(chart_data)
                    processed_files += 1
                else:
                     print(f"No valid datasets generated for metric '{metric_name}' from {filename}. Skipping chart.")
                     skipped_files += 1


            except Exception as e:
                print(f"Error processing file {filename} for fund {fund_code}: {e}")
                logging.exception(f"Error processing file {filename} for fund {fund_code}") # Log detailed traceback
                skipped_files += 1
                continue # Skip this file on error

        print(f"\nFinished processing. Processed {processed_files} metrics, Skipped {skipped_files} files/metrics for fund {fund_code}.")

        # Safely convert chart data to JSON for embedding in the template
        # Replace NaN/inf with None (handled above in .where())
        chart_data_json = jsonify(all_chart_data).get_data(as_text=True)

        return render_template('fund_detail_page.html',
                               fund_code=fund_code,
                               chart_data_json=chart_data_json,
                               available_metrics=available_metrics,
                               message=f"Displaying {len(all_chart_data)} charts for fund {fund_code}." if all_chart_data else f"No metrics found with data for fund '{fund_code}'.")

    except Exception as e:
        print(f"General error rendering detail page for fund {fund_code}: {e}")
        traceback.print_exc()
        logging.exception(f"General error rendering detail page for fund {fund_code}") # Log detailed traceback
        # Render the template with an error message
        return render_template('fund_detail_page.html',
                               fund_code=fund_code,
                               chart_data_json='[]',
                               available_metrics=[],
                               message=f"An unexpected error occurred while generating the page for fund {fund_code}.") 