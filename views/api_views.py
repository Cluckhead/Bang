'''
Defines the Flask Blueprint for handling API data retrieval requests.
'''
import os
import pandas as pd
from flask import Blueprint, render_template, request, current_app, jsonify
import datetime
from pandas.tseries.offsets import BDay
import time # Import the time module
#from tqs import tqs_query as tqs
# # Import the placeholder validation function
from data_validation import validate_data

# --- Feature Switch --- 
# Set to True to attempt real API calls, validation, and saving.
# Set to False to only simulate the API call (print to console).
USE_REAL_TQS_API = False
# ----------------------

# Blueprint Configuration
api_bp = Blueprint(
    'api_bp', __name__,
    template_folder='../templates',
    static_folder='../static'
)


def _simulate_and_print_tqs_call(QueryID, FundCodeList, StartDate, EndDate):
    '''Simulates calling the TQS API by printing the call signature.

    This function is used when USE_REAL_TQS_API is False.
    It does NOT interact with any external API.

    Returns:
        int: A simulated number of rows for status reporting.
    '''
    # Format the call signature exactly as requested: tqs(QueryID,[FundList],StartDate,EndDate)
    call_signature = f"tqs({QueryID}, {FundCodeList}, {StartDate}, {EndDate})"
    print(f"--- SIMULATING TQS API CALL (USE_REAL_TQS_API = False) ---")
    print(call_signature)
    print(f"--------------------------------------------------------")
    # Return a simulated row count for the summary table
    simulated_row_count = len(FundCodeList) * 10 if FundCodeList else 0 # Dummy calculation
    return simulated_row_count

def _fetch_real_tqs_data(QueryID, FundCodeList, StartDate, EndDate):
    '''Fetches real data from the TQS API.

    This function is called when USE_REAL_TQS_API is True.
    Replace the placeholder logic with the actual API interaction code.

    Args:
        QueryID: The query identifier.
        FundCodeList: List of fund codes.
        StartDate: Start date string (YYYY-MM-DD).
        EndDate: End date string (YYYY-MM-DD).

    Returns:
        pd.DataFrame or None: The DataFrame containing the fetched data,
                              or None if the API call fails or returns no data.
    '''
    current_app.logger.info(f"Attempting real TQS API call for QueryID: {QueryID}")
    print(f"--- EXECUTING REAL TQS API CALL (USE_REAL_TQS_API = True) --- ")
    print(f"tqs({QueryID}, {FundCodeList}, {StartDate}, {EndDate})")
    print(f"--------------------------------------------------------")

    dataframe = None # Initialize dataframe to None
    try:
        # --- !!! Replace this comment and the line below with the actual API call !!! ---
        # Ensure the `tqs` function/library is imported (commented out at the top)
        # dataframe = tqs.get_data(QueryID, FundCodeList, StartDate, EndDate) # Example real call
        print(dataframe.head()) if dataframe is not None else print("No data to display")
        pass # Remove this pass when uncommenting the line above
        # --- End of section to replace --- 
        
        # Check if the API returned valid data (e.g., a DataFrame)
        if dataframe is not None and isinstance(dataframe, pd.DataFrame):
            current_app.logger.info(f"Real TQS API call successful for QueryID: {QueryID}, Rows: {len(dataframe)}")
            return dataframe
        elif dataframe is None:
             # Explicitly handle the case where the API call itself returned None (e.g., planned failure or empty result coded as None)
             current_app.logger.warning(f"Real TQS API call for QueryID: {QueryID} returned None.")
             return None
        else:
            # Handle cases where the API returned something unexpected (not a DataFrame)
            current_app.logger.warning(f"Real TQS API call for QueryID: {QueryID} returned an unexpected data type: {type(dataframe)}.")
            return None # Treat unexpected types as failure

    except NameError as ne:
         # Specific handling if the tqs function isn't defined (import is commented out)
         current_app.logger.error(f"Real TQS API call failed for QueryID: {QueryID}. TQS function not imported/defined. Error: {ne}")
         print(f"    ERROR: TQS function not available. Ensure 'from tqs import tqs_query as tqs' is uncommented and the library is installed.")
         return None
    except Exception as e:
        # Handle API call errors (timeout, connection issues, authentication, etc.)
        current_app.logger.error(f"Real TQS API call failed for QueryID: {QueryID}. Error: {e}", exc_info=True)
        print(f"    ERROR during real API call: {e}")
        return None


# --- Helper Function to Get File Statuses ---
def get_data_file_statuses(data_folder):
    """
    Scans the data folder based on QueryMap.csv and returns status for each file.
    """
    statuses = []
    query_map_path = os.path.join(data_folder, 'QueryMap.csv')

    if not os.path.exists(query_map_path):
        current_app.logger.warning(f"QueryMap.csv not found at {query_map_path} for status check.")
        return statuses # Return empty list if map is missing

    try:
        query_map_df = pd.read_csv(query_map_path)
        if 'FileName' not in query_map_df.columns:
             current_app.logger.warning(f"QueryMap.csv at {query_map_path} is missing 'FileName' column.")
             return statuses

        date_column_candidates = ['Date', 'date', 'AsOfDate', 'ASOFDATE', 'Effective Date', 'Trade Date'] # Add more candidates if needed

        for index, row in query_map_df.iterrows():
            filename = row['FileName']
            file_path = os.path.join(data_folder, filename)
            status_info = {
                'filename': filename,
                'exists': False,
                'last_modified': 'N/A',
                'latest_data_date': 'N/A'
            }

            if os.path.exists(file_path):
                status_info['exists'] = True
                try:
                    # Get file modification time
                    mod_timestamp = os.path.getmtime(file_path)
                    status_info['last_modified'] = datetime.datetime.fromtimestamp(mod_timestamp).strftime('%Y-%m-%d %H:%M:%S')

                    # Try to read the CSV and find the latest date
                    try:
                        df = pd.read_csv(file_path, low_memory=False) # low_memory=False can help with mixed types
                        latest_date_found = None

                        for col_name in date_column_candidates:
                            if col_name in df.columns:
                                try:
                                    # Attempt conversion, coercing errors
                                    dates = pd.to_datetime(df[col_name], errors='coerce')
                                    # Drop NaT values resulting from coercion errors
                                    valid_dates = dates.dropna()
                                    if not valid_dates.empty:
                                        latest_date_found = valid_dates.max()
                                        status_info['latest_data_date'] = latest_date_found.strftime('%Y-%m-%d')
                                        break # Found a valid date column, stop searching
                                except Exception as date_parse_err:
                                     current_app.logger.warning(f"Could not parse date column '{col_name}' in {filename}: {date_parse_err}")
                                     continue # Try next candidate column

                        if latest_date_found is None:
                            status_info['latest_data_date'] = 'No Date Column Found/Parsed'


                    except pd.errors.EmptyDataError:
                         status_info['latest_data_date'] = 'File is Empty'
                         current_app.logger.warning(f"CSV file is empty: {file_path}")
                    except Exception as read_err:
                        status_info['latest_data_date'] = 'Read Error'
                        current_app.logger.error(f"Error reading CSV {file_path} for status check: {read_err}", exc_info=True)

                except Exception as file_err:
                     current_app.logger.error(f"Error accessing file properties for {file_path}: {file_err}", exc_info=True)
                     status_info['last_modified'] = 'Error Accessing File'

            statuses.append(status_info)

    except Exception as e:
        current_app.logger.error(f"Failed to process QueryMap.csv for file statuses: {e}", exc_info=True)
        # Optionally return a status indicating the map couldn't be processed
        return [{'filename': 'QueryMap Error', 'exists': False, 'last_modified': str(e), 'latest_data_date': ''}]


    return statuses
# --- End Helper Function ---


@api_bp.route('/get_data')
def get_data_page():
    '''Renders the page for users to select parameters for API data retrieval.'''
    try:
        # Construct the path to FundList.csv relative to the app's instance path or root
        # Assuming DATA_FOLDER is configured relative to the app root
        data_folder = current_app.config.get('DATA_FOLDER', 'Data')
        fund_list_path = os.path.join(data_folder, 'FundList.csv')

        if not os.path.exists(fund_list_path):
            current_app.logger.error(f"FundList.csv not found at {fund_list_path}")
            return "Error: FundList.csv not found.", 500

        fund_df = pd.read_csv(fund_list_path)

        # Ensure required columns exist
        if not {'Fund Code', 'Total Asset Value USD', 'Picked'}.issubset(fund_df.columns):
             current_app.logger.error(f"FundList.csv is missing required columns.")
             return "Error: FundList.csv is missing required columns (Fund Code, Total Asset Value USD, Picked).", 500

        # Convert Total Asset Value to numeric, coercing errors
        fund_df['Total Asset Value USD'] = pd.to_numeric(fund_df['Total Asset Value USD'], errors='coerce')
        fund_df.dropna(subset=['Total Asset Value USD'], inplace=True) # Remove rows where conversion failed

        # Sort by Total Asset Value USD descending
        fund_df = fund_df.sort_values(by='Total Asset Value USD', ascending=False)

        # Convert Picked to boolean
        fund_df['Picked'] = fund_df['Picked'].astype(bool)

        # Prepare fund data for the template
        funds = fund_df.to_dict('records')

        # Calculate default end date (previous business day)
        default_end_date = (datetime.datetime.today() - BDay(1)).strftime('%Y-%m-%d')

        # --- Get Data File Statuses ---
        data_file_statuses = get_data_file_statuses(data_folder)
        # --- End Get Data File Statuses ---

    except Exception as e:
        current_app.logger.error(f"Error preparing get_data page: {e}", exc_info=True)
        # Provide a user-friendly error message, specific details are logged
        return f"An error occurred while preparing the data retrieval page: {e}", 500

    return render_template('get_data.html', funds=funds, default_end_date=default_end_date, data_file_statuses=data_file_statuses)


@api_bp.route('/run_api_calls', methods=['POST'])
def run_api_calls():
    '''Handles the form submission to trigger API calls (real or simulated).'''
    try:
        # Get data from form
        data = request.get_json()
        days_back = int(data.get('days_back', 30)) # Default to 30 days if not provided
        end_date_str = data.get('end_date')
        selected_funds = data.get('funds', [])

        if not end_date_str:
            # Should have been validated client-side, but handle defensively
            return jsonify({"status": "error", "message": "End date is required."}), 400
        if not selected_funds:
             return jsonify({"status": "error", "message": "At least one fund must be selected."}), 400

        # Calculate dates
        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - pd.Timedelta(days=days_back)
        # Format dates as YYYY-MM-DD for the TQS call
        start_date_tqs_str = start_date.strftime('%Y-%m-%d')
        end_date_tqs_str = end_date.strftime('%Y-%m-%d')

        # --- Get Query Map ---
        data_folder = current_app.config.get('DATA_FOLDER', 'Data')
        query_map_path = os.path.join(data_folder, 'QueryMap.csv')
        if not os.path.exists(query_map_path):
            return jsonify({"status": "error", "message": f"QueryMap.csv not found at {query_map_path}"}), 500

        query_map_df = pd.read_csv(query_map_path)
        if not {'QueryID', 'FileName'}.issubset(query_map_df.columns):
            return jsonify({"status": "error", "message": "QueryMap.csv missing required columns (QueryID, FileName)."}), 500

        # --- Loop through Queries and Simulate API Calls ---
        # Note: This is synchronous. For real, long-running API calls,
        # use a task queue (e.g., Celery) and WebSockets/polling for progress.
        results_summary = []
        total_queries = len(query_map_df)
        completed_queries = 0

        for index, row in query_map_df.iterrows():
            query_id = row['QueryID']
            file_name = row['FileName']
            output_path = os.path.join(data_folder, file_name)

            # Reset status variables for each query
            status = "Unknown Error"
            rows_returned = 0
            lines_in_file = 0
            actual_df = None

            try:
                if USE_REAL_TQS_API:
                    # --- Real API Call, Validation, and Save --- 
                    actual_df = _fetch_real_tqs_data(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)

                    if actual_df is not None and isinstance(actual_df, pd.DataFrame):
                        rows_returned = len(actual_df)
                        if actual_df.empty:
                             current_app.logger.info(f"API returned empty DataFrame for {query_id} ({file_name}). Treating as valid, saving empty file.")
                             status = "Saved OK (Empty)"
                             # Proceed to save the empty DataFrame
                        else: 
                             # Validate the non-empty DataFrame structure
                            is_valid, validation_errors = validate_data(actual_df, file_name)
                            if not is_valid:
                                current_app.logger.warning(f"Data validation failed for {file_name}: {validation_errors}")
                                status = f"Validation Failed: {'; '.join(validation_errors)}"
                                lines_in_file = 0 # Don't save invalid data
                            # else: Validation passed (implicit)
                            
                        # Save the DataFrame to CSV (only if validation passed or df was empty)
                        # This block is reached if df is empty OR if df is not empty and is_valid is True
                        if status.startswith("Validation Failed") is False: # Check if validation passed or df was empty
                            try:
                                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                                actual_df.to_csv(output_path, index=False)
                                current_app.logger.info(f"Successfully saved data to {output_path}")
                                lines_in_file = rows_returned + 1 # +1 for header
                                # Update status only if it wasn't set to Saved OK (Empty) already
                                if status != "Saved OK (Empty)": 
                                    status = "Saved OK" 
                            except Exception as e:
                                current_app.logger.error(f"Error saving DataFrame to {output_path}: {e}", exc_info=True)
                                status = f"Save Error: {e}"
                                lines_in_file = 0 # Save failed
                    
                    elif actual_df is None:
                        # _fetch_real_tqs_data returned None (API call failed, returned None explicitly, or TQS not imported)
                        current_app.logger.warning(f"Real API call/fetch for {query_id} ({file_name}) returned None.")
                        status = "No Data / API Error / TQS Missing"
                        rows_returned = 0
                        lines_in_file = 0
                    else:
                        # _fetch_real_tqs_data returned something unexpected (not DataFrame, not None)
                        current_app.logger.error(f"Real API fetch for {query_id} ({file_name}) returned unexpected type: {type(actual_df)}.")
                        status = "API Returned Invalid Type"
                        rows_returned = 0
                        lines_in_file = 0

                else:
                    # --- Simulate API Call --- 
                    simulated_rows = _simulate_and_print_tqs_call(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)
                    rows_returned = simulated_rows
                    lines_in_file = simulated_rows + 1 if simulated_rows > 0 else 0
                    status = "Simulated OK"

            except Exception as e:
                 # Catch unexpected errors during the processing of a single query
                 current_app.logger.error(f"Unexpected error processing QueryID {query_id} ({file_name}): {e}", exc_info=True)
                 status = f"Processing Error: {e}"
                 rows_returned = 0
                 lines_in_file = 0

            # Append results for this query
            results_summary.append({
                "query_id": query_id,
                "file_name": file_name,
                "simulated_rows": rows_returned if not USE_REAL_TQS_API else None, # Only show simulated if simulating
                "actual_rows": rows_returned if USE_REAL_TQS_API else None, # Only show actual if using API
                "simulated_lines": lines_in_file if not USE_REAL_TQS_API else None,
                "actual_lines": lines_in_file if USE_REAL_TQS_API else None,
                "status": status
            })
            completed_queries += 1
            
            # Pause between real API calls
            if USE_REAL_TQS_API:
                print(f"Pausing for 3 seconds before next real API call...") # Optional status message
                time.sleep(3) 

        # After loop
        mode_message = "SIMULATED mode" if not USE_REAL_TQS_API else "REAL API mode"
        completion_message = f"Processed {completed_queries}/{total_queries} API calls ({mode_message})."

        return jsonify({
            "status": "completed",
            "message": completion_message,
            "summary": results_summary
        })

    except ValueError as ve:
        # Handle potential errors like invalid integer conversion for days_back
        current_app.logger.error(f"Value error in /run_api_calls: {ve}", exc_info=True)
        return jsonify({"status": "error", "message": f"Invalid input value: {ve}"}), 400
    except FileNotFoundError as fnf:
        # Specific handling for file not found during setup (e.g., QueryMap)
        current_app.logger.error(f"File not found error in /run_api_calls: {fnf}", exc_info=True)
        return jsonify({"status": "error", "message": f"Required file not found: {fnf}"}), 500
    except Exception as e:
        # Catch-all for other unexpected errors during the process
        current_app.logger.error(f"Unexpected error in /run_api_calls: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500

# === NEW RERUN ROUTE ===
@api_bp.route('/rerun-api-call', methods=['POST'])
def rerun_api_call():
    '''Handles the request to rerun a single API call (real or simulated).'''
    try:
        data = request.get_json()
        query_id = data.get('query_id')
        days_back = int(data.get('days_back', 30))
        end_date_str = data.get('end_date')
        selected_funds = data.get('funds', []) # Get the list of funds

        # --- Basic Input Validation ---
        if not query_id:
            return jsonify({"status": "error", "message": "Query ID is required."}), 400
        if not end_date_str:
            return jsonify({"status": "error", "message": "End date is required."}), 400
        if not selected_funds:
             # Allow rerunning even if no funds are selected? Decide based on API behavior.
             # For now, let's require funds similar to the initial run.
             return jsonify({"status": "error", "message": "At least one fund must be selected."}), 400

        # --- Calculate Dates ---
        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - pd.Timedelta(days=days_back)
        start_date_tqs_str = start_date.strftime('%Y-%m-%d')
        end_date_tqs_str = end_date.strftime('%Y-%m-%d')

        # --- Find FileName from QueryMap ---
        data_folder = current_app.config.get('DATA_FOLDER', 'Data')
        query_map_path = os.path.join(data_folder, 'QueryMap.csv')
        if not os.path.exists(query_map_path):
            return jsonify({"status": "error", "message": f"QueryMap.csv not found at {query_map_path}"}), 500

        query_map_df = pd.read_csv(query_map_path)
        # Ensure comparison is string vs string
        query_map_df['QueryID'] = query_map_df['QueryID'].astype(str)

        if 'QueryID' not in query_map_df.columns or 'FileName' not in query_map_df.columns:
             return jsonify({"status": "error", "message": "QueryMap.csv missing required columns (QueryID, FileName)."}), 500

        # Compare string query_id from request with string QueryID column
        query_row = query_map_df[query_map_df['QueryID'] == query_id]
        if query_row.empty:
            # Log the types for debugging if it still fails
            current_app.logger.warning(f"QueryID '{query_id}' (type: {type(query_id)}) not found in QueryMap QueryIDs (types: {query_map_df['QueryID'].apply(type).unique()}).")
            return jsonify({"status": "error", "message": f"QueryID '{query_id}' not found in QueryMap.csv."}), 404

        file_name = query_row.iloc[0]['FileName']
        output_path = os.path.join(data_folder, file_name)

        # --- Execute Single API Call (Simulated or Real) ---
        status = "Rerun Error: Unknown"
        rows_returned = 0
        lines_in_file = 0
        actual_df = None

        try:
            if USE_REAL_TQS_API:
                # --- Real API Call, Validation, and Save ---
                actual_df = _fetch_real_tqs_data(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)

                if actual_df is not None and isinstance(actual_df, pd.DataFrame):
                    rows_returned = len(actual_df)
                    if actual_df.empty:
                        current_app.logger.info(f"(Rerun) API returned empty DataFrame for {query_id} ({file_name}). Saving empty file.")
                        status = "Saved OK (Empty)"
                    else:
                        is_valid, validation_errors = validate_data(actual_df, file_name)
                        if not is_valid:
                            current_app.logger.warning(f"(Rerun) Data validation failed for {file_name}: {validation_errors}")
                            status = f"Validation Failed: {'; '.join(validation_errors)}"
                            lines_in_file = 0
                        # else: Validation passed

                    if not status.startswith("Validation Failed"):
                        try:
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            actual_df.to_csv(output_path, index=False)
                            current_app.logger.info(f"(Rerun) Successfully saved data to {output_path}")
                            lines_in_file = rows_returned + 1
                            if status != "Saved OK (Empty)":
                                status = "Saved OK"
                        except Exception as e:
                            current_app.logger.error(f"(Rerun) Error saving DataFrame to {output_path}: {e}", exc_info=True)
                            status = f"Save Error: {e}"
                            lines_in_file = 0

                elif actual_df is None:
                    current_app.logger.warning(f"(Rerun) Real API call/fetch for {query_id} ({file_name}) returned None.")
                    status = "No Data / API Error / TQS Missing"
                    rows_returned = 0
                    lines_in_file = 0
                else:
                    current_app.logger.error(f"(Rerun) Real API fetch for {query_id} ({file_name}) returned unexpected type: {type(actual_df)}.")
                    status = "API Returned Invalid Type"
                    rows_returned = 0
                    lines_in_file = 0
            else:
                # --- Simulate API Call ---
                simulated_rows = _simulate_and_print_tqs_call(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)
                rows_returned = simulated_rows
                lines_in_file = simulated_rows + 1 if simulated_rows > 0 else 0
                status = "Simulated OK"

        except Exception as e:
            current_app.logger.error(f"Error during single rerun for query {query_id} ({file_name}): {e}", exc_info=True)
            status = f"Processing Error: {e}"
            rows_returned = 0
            lines_in_file = 0

        # --- Return Result for the Single Query ---
        result_data = {
            "status": status,
             # Provide consistent keys for the frontend to update the table
            "simulated_rows": rows_returned if not USE_REAL_TQS_API else None,
            "actual_rows": rows_returned if USE_REAL_TQS_API else None,
            "simulated_lines": lines_in_file if not USE_REAL_TQS_API else None,
            "actual_lines": lines_in_file if USE_REAL_TQS_API else None
        }
        # The frontend needs the keys it expects based on the JS update logic
        # Adjusting keys slightly to match JS expectations more directly if needed:
        if not USE_REAL_TQS_API:
            result_data["simulated_rows"] = rows_returned
            result_data["simulated_lines"] = lines_in_file
        else:
            # If using real API, maybe the frontend expects these keys regardless?
            # Let's send both sets of keys, JS can pick based on mode if necessary,
            # or we assume JS handles based on the status string.
            # The current JS logic seems to look for simulated_rows/lines explicitly.
            # Let's stick to the original separation for clarity.
             pass # Keep actual_rows/lines separate

        return jsonify(result_data)

    except ValueError as ve:
        current_app.logger.error(f"Value error in /rerun-api-call: {ve}", exc_info=True)
        return jsonify({"status": "error", "message": f"Invalid input value: {ve}"}), 400
    except FileNotFoundError as fnf:
        current_app.logger.error(f"File not found error in /rerun-api-call: {fnf}", exc_info=True)
        return jsonify({"status": "error", "message": f"Required file not found: {fnf}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error in /rerun-api-call: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500

# Ensure no code remains after this point in the file for this function. 