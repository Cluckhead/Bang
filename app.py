# This file contains the main Flask application and routes.
from flask import Flask, render_template, jsonify
import os
import pandas as pd
import numpy as np
from data_processing import load_and_process_data, calculate_latest_metrics
# Import the new security processing functions
from security_processing import load_and_process_security_data, calculate_security_latest_metrics
import traceback # Import traceback for detailed error logging
import re # Import regex for parsing

app = Flask(__name__)
# Serve static files (for JS)
app.static_folder = 'static'

DATA_FOLDER = 'Data'

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    'blue', 'red', 'green', 'purple', '#FF7F50', # Coral
    '#6495ED', # CornflowerBlue
    '#DC143C', # Crimson
    '#00FFFF'  # Aqua
]

# --- Helper Function for Parsing Funds Column ---
def parse_fund_list(fund_string):
    """Safely parses the fund list string like '[FUND1,FUND2]' or '[FUND1]' into a list.
       Handles potential errors and variations in spacing.
    """
    if not isinstance(fund_string, str) or not fund_string.startswith('[') or not fund_string.endswith(']'):
        return [] # Return empty list if format is unexpected
    try:
        # Remove brackets and split by comma
        content = fund_string[1:-1]
        # Split by comma, strip whitespace from each element
        funds = [f.strip() for f in content.split(',') if f.strip()] 
        return funds
    except Exception as e:
        print(f"Error parsing fund string '{fund_string}': {e}")
        return []

@app.route('/')
def index():
    """Renders the main dashboard page with a summary table of Z-scores for ts_ files."""
    # Find only files starting with ts_ and ending with .csv
    files = [f for f in os.listdir(DATA_FOLDER) if f.startswith('ts_') and f.endswith('.csv')]
    
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
            print(f"Error: Data file '{filename}' not found.")
        except ValueError as ve:
            print(f"Value Error processing {metric_filename}: {ve}") # Log with filename
        except Exception as e:
            print(f"Error processing {metric_filename} during dashboard aggregation: {e}") # Log with filename
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
        print("Successfully combined Change Z-scores.")
        print(f"Summary DF columns: {summary_df.columns.tolist()}")
    else:
        print("No Change Z-scores could be extracted for the summary.")

    return render_template('index.html', 
                           metrics=metric_display_names, # Still used for top-level metric links
                           summary_data=summary_df,
                           summary_metrics=processed_summary_columns) # Pass the NEW list of combined column names

@app.route('/metric/<metric_name>')
def metric_page(metric_name):
    """Renders the page for a specific metric (identified by display name) from a ts_ file."""
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
        all_cols_for_z = [benchmark_col] + fund_cols
        z_score_cols = [f'{col} Change Z-Score' for col in all_cols_for_z 
                        if f'{col} Change Z-Score' in latest_metrics.columns]
        
        if not z_score_cols:
            print(f"Warning: No 'Change Z-Score' columns found in latest_metrics for {metric_name} (from {filename})")
            latest_val_cols = [f'{col} Latest Value' for col in all_cols_for_z 
                               if f'{col} Latest Value' in latest_metrics.columns]
            if latest_val_cols:
                 missing_latest = latest_metrics[latest_metrics[latest_val_cols].isna().any(axis=1)]
            else:
                 missing_latest = pd.DataFrame(index=latest_metrics.index) 
        else:
             missing_latest = latest_metrics[latest_metrics[z_score_cols].isna().any(axis=1)]

        # --- Prepare data for JavaScript --- 
        charts_data_for_js = {}
        for fund_code in latest_metrics.index: 
            # Retrieve historical data for the specific fund (needed for charts)
            # Use .copy() to avoid potential warnings
            fund_hist_data = df.xs(fund_code, level=1).sort_index().copy()
            
            # Retrieve the calculated latest metrics (flattened row) for this fund
            # This now contains keys like 'Benchmark Spread Duration Latest Value', 'Fund Spread Duration Change Z-Score', etc.
            fund_latest_metrics_row = latest_metrics.loc[fund_code]
            
            # Check if this fund was flagged as missing (based on Z-score or fallback)
            is_missing_latest = fund_code in missing_latest.index

            # Prepare labels (dates) for the chart
            labels = fund_hist_data.index.strftime('%Y-%m-%d').tolist()
            datasets = []

            # Create datasets for the chart (raw values)
            # Add benchmark dataset
            if benchmark_col in fund_hist_data.columns:
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
            
            # Convert metrics row to dictionary (structure is already correct)
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

# --- New Route for Securities --- 
@app.route('/securities')
def securities_page():
    """Renders a page summarizing potential issues in security-level data from sec_ files."""
    print("--- Starting Security Data Processing for Spread --- ")
    spread_filename = "sec_Spread.csv"
    data_filepath = os.path.join(DATA_FOLDER, spread_filename)

    all_metrics_list = []
    all_static_columns = set() # Keep track of all unique static columns across files
    filter_options = {} # Dictionary to store unique values for each filterable static column
    combined_metrics_df = pd.DataFrame() # Initialize DataFrame

    if not os.path.exists(data_filepath):
        print(f"Error: The required file '{spread_filename}' was not found in the '{DATA_FOLDER}' directory.")
        return render_template('securities_page.html', 
                           securities_data={}, 
                           filter_options={}, 
                           all_static_cols=[], 
                           message=f"Error: Required data file '{spread_filename}' not found.")

    try:
        print(f"Processing security file: {spread_filename}")
        # 1. Load and process (melts data to long format)
        df_long, static_cols = load_and_process_security_data(spread_filename)
        
        if df_long is None or df_long.empty:
            print(f"Skipping {spread_filename} due to load/process errors or empty data after processing.")
            # Render template with a specific error message for the spread file
            return render_template('securities_page.html', 
                                   securities_data={}, 
                                   filter_options={}, 
                                   all_static_cols=[], 
                                   message=f"Error loading or processing '{spread_filename}'.")
            
        print(f"Loaded {spread_filename}. Identifying static columns: {static_cols}")
        all_static_columns.update(static_cols) # Add newly found static columns

        # 2. Calculate latest metrics
        latest_sec_metrics = calculate_security_latest_metrics(df_long, static_cols)

        if latest_sec_metrics.empty:
            print(f"No metrics calculated for {spread_filename}. Skipping.")
             # Render template indicating no metrics calculated
            return render_template('securities_page.html', 
                                   securities_data={}, 
                                   filter_options={}, 
                                   all_static_cols=[], 
                                   message=f"Could not calculate metrics from '{spread_filename}'.")
            
        # 3. Store the calculated metrics (No need to add Source Metric anymore)
        # metric_name = spread_filename.replace('sec_', '').replace('.csv', '') # Not needed
        # latest_sec_metrics['Source Metric'] = metric_name # REMOVED
        # all_metrics_list.append(latest_sec_metrics) # Not needed if only one file
        combined_metrics_df = latest_sec_metrics # Assign directly
        print(f"Successfully calculated metrics for {spread_filename}")
        
        # 4. Collect filter options from static columns 
        current_static_in_df = [col for col in static_cols if col in combined_metrics_df.columns]
        for col in current_static_in_df:
            unique_vals = combined_metrics_df[col].unique().tolist()
            unique_vals = [item.item() if isinstance(item, np.generic) else item for item in unique_vals]
            unique_vals = [val for val in unique_vals if pd.notna(val)] # Remove NaN
            
            if col not in filter_options:
                filter_options[col] = set(unique_vals)
            else:
                filter_options[col].update(unique_vals)
        
    except Exception as e:
        print(f"Error processing security file {spread_filename}: {e}")
        traceback.print_exc()
        return render_template('securities_page.html', 
                               securities_data={}, 
                               filter_options={}, 
                               all_static_cols=[], 
                               message=f"An error occurred while processing '{spread_filename}'.")

    # Combine all metrics DataFrames - Not needed anymore as we process only one file
    # if not all_metrics_list:
    #     print("No security metrics were successfully generated from any file.")
    #     return render_template('securities_page.html', 
    #                            securities_data={}, 
    #                            filter_options={}, 
    #                            all_static_cols=[], 
    #                            message="Could not generate metrics from any security data files.")
    # combined_metrics_df = pd.concat(all_metrics_list) # Not needed

    if combined_metrics_df.empty:
         print("No security metrics were generated from sec_Spread.csv.")
         # This case should be caught earlier, but added as a safeguard
         return render_template('securities_page.html', 
                                securities_data={}, 
                                filter_options={}, 
                                all_static_cols=[], 
                                message=f"Could not generate metrics from '{spread_filename}'.")

    # --- Sorting by Change Z-Score --- 
    if 'Change Z-Score' in combined_metrics_df.columns:
        # Handle potential NaNs before calculating absolute value and sorting
        combined_metrics_df['Abs Change Z-Score'] = combined_metrics_df['Change Z-Score'].fillna(0).abs()
        combined_metrics_df.sort_values(by='Abs Change Z-Score', ascending=False, inplace=True)
        combined_metrics_df.drop(columns=['Abs Change Z-Score'], inplace=True)
        print("Sorted combined security metrics by absolute Change Z-Score.")
    else:
        print("Warning: 'Change Z-Score' column not found in combined metrics. Cannot sort.")

    # Convert final filter options sets to sorted lists
    final_filter_options = {k: sorted(list(v)) for k, v in filter_options.items()}
    
    # Convert DataFrame to list of dictionaries for easier template processing
    securities_data_list = combined_metrics_df.reset_index().round(3).to_dict(orient='records')
    for row in securities_data_list:
        for key, value in row.items():
            if pd.isna(value):
                row[key] = None 
                
    # Define order of columns for display (Security ID first, then Static, then Metrics)
    id_col_name = combined_metrics_df.index.name or 'Security ID' # Get index name
    ordered_static_cols = sorted(list(all_static_columns))
    metric_cols_ordered = ['Latest Value', 'Change', 'Change Z-Score', 'Mean', 'Max', 'Min']
    # Ensure only existing columns are included, REMOVE 'Source Metric'
    final_col_order = [id_col_name] + \
                      [col for col in ordered_static_cols if col in combined_metrics_df.columns] + \
                      [col for col in metric_cols_ordered if col in combined_metrics_df.columns]
                      
    print(f"Final column order for display: {final_col_order}")

    return render_template('securities_page.html',
                           securities_data=securities_data_list,
                           filter_options=final_filter_options,
                           column_order=final_col_order, # Pass column order to template
                           id_col_name=id_col_name, # Pass the identified ID column name
                           message=None)

# --- New Route for Security Details/Charts --- 
@app.route('/security_details/<metric_name>/<security_id>')
def security_details_page(metric_name, security_id):
    """Renders a page showing the time series chart for a specific security from a specific metric file."""
    filename = f"sec_{metric_name}.csv"
    price_filename = "sec_Price.csv" # Define price filename
    print(f"--- Requesting Security Details --- Metric: {metric_name}, Security ID: {security_id}, File: {filename}")

    try:
        # 1. Load and process the specific security data file (for the primary metric)
        df_long, static_cols = load_and_process_security_data(filename)

        if df_long is None or df_long.empty:
            return f"Error: Could not load or process data for file '{filename}'", 404
            
        # Check if the requested security ID exists in the data
        # Get the actual name of the ID level in the index
        actual_id_col_name = df_long.index.names[1]
        if security_id not in df_long.index.get_level_values(actual_id_col_name):
             return f"Error: Security ID '{security_id}' not found in file '{filename}'.", 404

        # 2. Extract historical data for the specific security
        # Use .copy() to avoid potential SettingWithCopyWarning if we modify later
        security_data = df_long.xs(security_id, level=actual_id_col_name).sort_index().copy()

        if security_data.empty:
            return f"Error: No historical data found for Security ID '{security_id}' in file '{filename}'.", 404
            
        # Extract static dimension values for display
        static_info = {} 
        first_row = security_data.iloc[0]
        for col in static_cols:
            if col in first_row.index:
                static_info[col] = first_row[col]
                
        # 3. Prepare data for Chart.js
        labels = security_data.index.strftime('%Y-%m-%d').tolist()
        datasets = [{
            'label': f'{security_id} - {metric_name} Value',
            'data': security_data['Value'].round(3).fillna(np.nan).tolist(),
            'borderColor': COLOR_PALETTE[0], # Use first color
            'backgroundColor': COLOR_PALETTE[0] + '40',
            'tension': 0.1,
            'yAxisID': 'y' # Assign primary metric to the default 'y' axis
        }]

        # --- Attempt to load and add Price data ---
        try:
            print(f"Attempting to load price data from {price_filename} for {security_id}...")
            price_df_long, _ = load_and_process_security_data(price_filename) # Ignore static cols from price file

            if price_df_long is not None and not price_df_long.empty:
                if security_id in price_df_long.index.get_level_values(actual_id_col_name):
                    price_data = price_df_long.xs(security_id, level=actual_id_col_name).sort_index().copy()
                    # Reindex price data to align dates with the main metric data
                    price_data = price_data.reindex(security_data.index) 
                    
                    if not price_data.empty:
                        price_dataset = {
                            'label': f'{security_id} - Price',
                            'data': price_data['Value'].round(3).fillna(np.nan).tolist(),
                            'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)], # Use second color
                            'backgroundColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)] + '40',
                            'tension': 0.1,
                            'yAxisID': 'y1' # Assign price data to the second y-axis
                        }
                        datasets.append(price_dataset)
                        print("Successfully added Price data overlay.")
                    else:
                         print(f"Warning: Price data found for {security_id}, but was empty after aligning dates.")
                else:
                     print(f"Warning: Security ID {security_id} not found in {price_filename}.")
            else:
                 print(f"Warning: Could not load or process {price_filename}.")
        except FileNotFoundError:
            print(f"Warning: Price data file '{price_filename}' not found. Skipping price overlay.")
        except Exception as e_price:
            print(f"Warning: Error processing price data for {security_id} from {price_filename}: {e_price}")
            traceback.print_exc() # Log the price processing error but continue

        # --- End of Price data loading ---

        chart_data_for_js = {
            'labels': labels,
            'datasets': datasets # Now contains metric and potentially price datasets
        }
        
        latest_date_overall = security_data.index.max()

        # 4. Render a new template
        return render_template('security_details_page.html',
                               metric_name=metric_name,
                               security_id=security_id,
                               static_info=static_info,
                               chart_data_json=jsonify(chart_data_for_js).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y'))

    except FileNotFoundError:
        return f"Error: Data file '{filename}' not found.", 404
    except ValueError as ve:
        print(f"Value Error processing security details for {metric_name}/{security_id}: {ve}")
        return f"Error processing details for {security_id}: {ve}", 400
    except Exception as e:
        print(f"Error processing security details for {metric_name}/{security_id}: {e}")
        traceback.print_exc()
        return f"An error occurred processing details for {security_id}: {e}", 500

# --- New Route for Fund-Specific Duration Details ---
@app.route('/fund_duration_details/<fund_code>')
def fund_duration_details(fund_code):
    """Renders a page showing duration changes for securities held by a specific fund."""
    duration_filename = "sec_duration.csv"
    data_filepath = os.path.join(DATA_FOLDER, duration_filename)
    print(f"--- Requesting Duration Details for Fund: {fund_code} --- File: {duration_filename}")

    if not os.path.exists(data_filepath):
        print(f"Error: Duration file '{duration_filename}' not found.")
        return f"Error: Data file '{duration_filename}' not found.", 404

    try:
        # 1. Load the duration data
        df = pd.read_csv(data_filepath)
        print(f"Loaded {duration_filename}")

        # 2. Identify static and date columns
        # Assuming first few columns are static based on observation
        # A more robust method might involve config or pattern matching if format varies widely
        potential_static_cols = ['Security Name', 'Funds', 'Type', 'Callable', 'Currency']
        static_cols = [col for col in potential_static_cols if col in df.columns]
        date_cols = [col for col in df.columns if col not in static_cols]
        
        if not date_cols or len(date_cols) < 2:
             print("Error: Not enough date columns found in duration file to calculate change.")
             return f"Error: Insufficient date columns in '{duration_filename}' to calculate change.", 500

        # Ensure date columns are sortable (attempt conversion if needed, basic check)
        try:
            # Basic check assuming 'DD/MM/YYYY' format, adjust if different
            pd.to_datetime(date_cols, format='%d/%m/%Y', errors='raise') 
            # Sort date columns to ensure correct order for last two days calculation
            date_cols = sorted(date_cols, key=lambda d: pd.to_datetime(d, format='%d/%m/%Y'))
            print(f"Identified and sorted date columns: {date_cols[-5:]} (last 5 shown)")
        except ValueError:
            print("Warning: Could not parse all date columns using DD/MM/YYYY format. Using original order.")
            # Fallback: Use original order if parsing fails
            # This might be incorrect if columns are not ordered chronologically in the CSV
        
        # Identify last two date columns based on sorted list (or original if parsing failed)
        last_date_col = date_cols[-1]
        second_last_date_col = date_cols[-2]
        print(f"Using dates for change calculation: {second_last_date_col} and {last_date_col}")

        # Ensure the relevant date columns are numeric for calculation
        df[last_date_col] = pd.to_numeric(df[last_date_col], errors='coerce')
        df[second_last_date_col] = pd.to_numeric(df[second_last_date_col], errors='coerce')

        # 3. Filter by Fund Code
        # Apply the parsing function to the 'Funds' column
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
        # Select columns for display
        id_col_name = 'Security Name' # Assuming this is the primary ID
        display_cols = [id_col_name] + [col for col in static_cols if col != id_col_name] + [second_last_date_col, last_date_col, change_col_name]
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

if __name__ == '__main__':
    app.run(debug=True) 