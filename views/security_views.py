"""
Blueprint for security-related routes (e.g., summary page and individual details).
"""
from flask import Blueprint, render_template, jsonify
import os
import pandas as pd
import numpy as np
import traceback

# Import necessary functions/constants from other modules
from config import DATA_FOLDER, COLOR_PALETTE
from security_processing import load_and_process_security_data, calculate_security_latest_metrics

# Define the blueprint
security_bp = Blueprint('security', __name__, url_prefix='/security')

@security_bp.route('/summary') # Renamed route for clarity, corresponds to /security/summary
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

        # 3. Store the calculated metrics
        combined_metrics_df = latest_sec_metrics # Assign directly
        print(f"Successfully calculated metrics for {spread_filename}")

        # 4. Collect filter options from static columns
        current_static_in_df = [col for col in static_cols if col in combined_metrics_df.columns]
        for col in current_static_in_df:
            unique_vals = combined_metrics_df[col].unique().tolist()
            # Convert numpy types to standard Python types if necessary
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
    # Ensure only existing columns are included
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

@security_bp.route('/details/<metric_name>/<security_id>') # Corresponds to /security/details/...
def security_details_page(metric_name, security_id):
    """Renders a page showing the time series chart for a specific security from a specific metric file."""
    filename = f"sec_{metric_name}.csv"
    price_filename = "sec_Price.csv" # Define price filename
    duration_filename = "sec_Duration.csv" # Define duration filename
    print(f"--- Requesting Security Details --- Metric: {metric_name}, Security ID: {security_id}, File: {filename}")

    try:
        # 1. Load and process the specific security data file (for the primary metric)
        df_long, static_cols = load_and_process_security_data(filename)

        if df_long is None or df_long.empty:
            return f"Error: Could not load or process data for file '{filename}'", 404

        # Check if the requested security ID exists in the data
        actual_id_col_name = df_long.index.names[1]
        if security_id not in df_long.index.get_level_values(actual_id_col_name):
             return f"Error: Security ID '{security_id}' not found in file '{filename}'.", 404

        # 2. Extract historical data for the specific security
        security_data = df_long.xs(security_id, level=actual_id_col_name).sort_index().copy()

        if security_data.empty:
            return f"Error: No historical data found for Security ID '{security_id}' in file '{filename}'.", 404

        # Extract static dimension values for display
        static_info = {}
        if not security_data.empty:
            first_row = security_data.iloc[0]
            for col in static_cols:
                if col in first_row.index:
                    static_info[col] = first_row[col]

        # 3. Prepare data for Chart.js
        labels = security_data.index.strftime('%Y-%m-%d').tolist()
        # Initialize datasets list for the primary chart
        primary_datasets = [{
            'label': f'{security_id} - {metric_name} Value',
            'data': security_data['Value'].round(3).fillna(np.nan).tolist(),
            'borderColor': COLOR_PALETTE[0], # Use first color
            'backgroundColor': COLOR_PALETTE[0] + '40',
            'tension': 0.1,
            'yAxisID': 'y' # Assign primary metric to the default 'y' axis
        }]

        # Initialize chart_data_for_js with primary data
        chart_data_for_js = {
            'labels': labels,
            'primary_datasets': primary_datasets, # Use a specific key for primary chart datasets
            'duration_dataset': None # Initialize duration dataset as None
        }

        latest_date_overall = security_data.index.max()

        # --- Attempt to load and add Price data to the primary chart ---
        try:
            print(f"Attempting to load price data from {price_filename} for {security_id}...")
            price_df_long, _ = load_and_process_security_data(price_filename) # Ignore static cols from price file

            if price_df_long is not None and not price_df_long.empty:
                price_actual_id_col = price_df_long.index.names[1] # Get ID column name from price file
                if security_id in price_df_long.index.get_level_values(price_actual_id_col):
                    price_data = price_df_long.xs(security_id, level=price_actual_id_col).sort_index().copy()
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
                        # Append price dataset to the primary_datasets list
                        chart_data_for_js['primary_datasets'].append(price_dataset)
                        print("Successfully added Price data overlay to primary chart.")
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

        # --- Attempt to load and add Duration data for the second chart ---
        try:
            print(f"Attempting to load duration data from {duration_filename} for {security_id}...")
            duration_df_long, _ = load_and_process_security_data(duration_filename) # Ignore static cols

            if duration_df_long is not None and not duration_df_long.empty:
                duration_actual_id_col = duration_df_long.index.names[1] # Get ID column name
                if security_id in duration_df_long.index.get_level_values(duration_actual_id_col):
                    duration_data = duration_df_long.xs(security_id, level=duration_actual_id_col).sort_index().copy()
                    # Reindex duration data to align dates with the main metric data
                    duration_data = duration_data.reindex(security_data.index)

                    if not duration_data.empty:
                        duration_dataset = {
                            'label': f'{security_id} - Duration',
                            'data': duration_data['Value'].round(3).fillna(np.nan).tolist(),
                            'borderColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)], # Use third color
                            'backgroundColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)] + '40',
                            'tension': 0.1
                            # No yAxisID needed if it's a separate chart with its own scale
                        }
                        # Assign duration dataset to its specific key
                        chart_data_for_js['duration_dataset'] = duration_dataset
                        print("Successfully prepared Duration data for separate chart.")
                    else:
                         print(f"Warning: Duration data found for {security_id}, but was empty after aligning dates.")
                else:
                     print(f"Warning: Security ID {security_id} not found in {duration_filename}.")
            else:
                 print(f"Warning: Could not load or process {duration_filename}.")
        except FileNotFoundError:
            print(f"Warning: Duration data file '{duration_filename}' not found. Skipping duration chart.")
        except Exception as e_duration:
            print(f"Warning: Error processing duration data for {security_id} from {duration_filename}: {e_duration}")
            traceback.print_exc() # Log the duration processing error but continue

        # 4. Render the template
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