'''
Defines the Flask Blueprint for handling API data retrieval requests, including simulation,
fetching real data, saving data (with options for merging or overwriting),
and rerunning specific API calls.
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
         print(f"     ERROR: TQS function not available. Ensure 'from tqs import tqs_query as tqs' is uncommented and the library is installed.")
         return None
    except Exception as e:
        # Handle API call errors (timeout, connection issues, authentication, etc.)
        current_app.logger.error(f"Real TQS API call failed for QueryID: {QueryID}. Error: {e}", exc_info=True)
        print(f"     ERROR during real API call: {e}")
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

        date_column_candidates = ['Date', 'date', 'AsOfDate', 'ASOFDATE', 'Effective Date', 'Trade Date', 'Position Date'] # Add more candidates if needed

        for index, row in query_map_df.iterrows():
            filename = row['FileName']
            file_path = os.path.join(data_folder, filename)
            status_info = {
                'filename': filename,
                'exists': False,
                'last_modified': 'N/A',
                'latest_data_date': 'N/A',
                'funds_included': 'N/A' # Initialize new key
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
                        df_head = df.head()
                        # Determine the actual date column name
                        date_col = None
                        # --- Update Date Column Candidates ---
                        date_column_candidates = ['Date', 'date', 'AsOfDate', 'ASOFDATE', 'Effective Date', 'Trade Date', 'Position Date']
                        found_cols = df_head.columns.str.strip()
                        current_app.logger.info(f"[{filename}] Checking for date columns: {date_column_candidates} in columns {found_cols.tolist()}")
                        for candidate in date_column_candidates:
                            # Case-insensitive check
                            matching_cols = [col for col in found_cols if col.lower() == candidate.lower()]
                            if matching_cols:
                                date_col = matching_cols[0] # Use the actual name found
                                current_app.logger.info(f"[{filename}] Found date column: '{date_col}'")
                                break # Found the first match

                        if date_col:
                            try:
                                # --- FIX: Use the full DataFrame's date column ---
                                if date_col not in df.columns:
                                    # Handle case where column name from head differs slightly after full read (e.g., whitespace)
                                    # Find it again in the full df columns, case-insensitively
                                    corrected_date_col = None
                                    for col in df.columns:
                                        if col.strip().lower() == date_col.lower():
                                            corrected_date_col = col
                                            break
                                    if not corrected_date_col:
                                         raise ValueError(f"Date column '{date_col}' found in header but not in full DataFrame columns: {df.columns.tolist()}")
                                    date_col = corrected_date_col # Use the name from the full df

                                date_series = df[date_col] # Use the full series from the complete DataFrame
                                # --------------------------------------------------

                                current_app.logger.info(f"[{filename}] Attempting to parse full date column '{date_col}' (length: {len(date_series)}). Top 5 values: {date_series.head().to_list()}")

                                # Try standard YYYY-MM-DD first
                                parsed_dates = pd.to_datetime(date_series, format='%Y-%m-%d', errors='coerce')

                                # If all are NaT, try DD/MM/YYYY
                                if parsed_dates.isnull().all():
                                    current_app.logger.info(f"[{filename}] Format YYYY-MM-DD failed, trying DD/MM/YYYY...")
                                    parsed_dates = pd.to_datetime(date_series, format='%d/%m/%Y', errors='coerce')

                                # If still all NaT, try inferring (less reliable but fallback)
                                if parsed_dates.isnull().all():
                                     current_app.logger.warning(f"[{filename}] Both specific formats failed, trying to infer date format...")
                                     parsed_dates = pd.to_datetime(date_series, errors='coerce', infer_datetime_format=True)

                                # Check if any dates were successfully parsed
                                if not parsed_dates.isnull().all():
                                    latest_date = parsed_dates.max()
                                    if pd.notna(latest_date):
                                        status_info['latest_data_date'] = latest_date.strftime('%Y-%m-%d')
                                        current_app.logger.info(f"[{filename}] Successfully found latest date: {status_info['latest_data_date']}")
                                    else:
                                        status_info['latest_data_date'] = 'No Valid Dates Found'
                                        current_app.logger.warning(f"[{filename}] Parsed dates but found no valid max date (all NaT?).")
                                else:
                                    status_info['latest_data_date'] = 'Date Parsing Failed'
                                    current_app.logger.warning(f"[{filename}] All parsing attempts failed for date column '{date_col}'.")

                            except Exception as date_err:
                                current_app.logger.error(f"Error parsing date column '{date_col}' in {file_path}: {date_err}", exc_info=True)
                                status_info['latest_data_date'] = f'Error Parsing Date ({date_col})'
                        else:
                            status_info['latest_data_date'] = 'No Date Column Found/Parsed'
                            current_app.logger.warning(f"[{filename}] Could not find a suitable date column.")

                        # --- Add Fund Code Extraction ---
                        code_col = None
                        # FIX: Search for 'code' OR 'fund code' (case-insensitive)
                        code_candidates = ['code', 'fund code']
                        found_code_col_name = None
                        for candidate in code_candidates:
                              matches = [c for c in df.columns if c.strip().lower() == candidate]
                              if matches:
                                  found_code_col_name = matches[0] # Use the actual column name found
                                  break # Stop searching once found

                        if found_code_col_name:
                            code_col = found_code_col_name # Assign the found name to code_col
                            current_app.logger.info(f"[{filename}] Found Code column: '{code_col}'")
                            if not df.empty and code_col in df:
                                try:
                                    unique_funds = sorted([str(f) for f in df[code_col].unique() if pd.notna(f)])
                                    if unique_funds:
                                        if len(unique_funds) <= 5:
                                            status_info['funds_included'] = ', '.join(unique_funds)
                                        else:
                                            status_info['funds_included'] = ', '.join(unique_funds[:5]) + f' ... ({len(unique_funds)} total)'
                                        current_app.logger.info(f"[{filename}] Found funds: {status_info['funds_included']}")
                                    else:
                                        status_info['funds_included'] = 'No Codes Found'
                                except Exception as fund_err:
                                     current_app.logger.error(f"[{filename}] Error extracting funds from column '{code_col}': {fund_err}")
                                     status_info['funds_included'] = 'Error Extracting Funds'
                            else:
                                status_info['funds_included'] = 'Code Column Empty?' # Should be covered by EmptyDataError usually
                        else:
                            status_info['funds_included'] = 'Code Column Missing'
                            current_app.logger.warning(f"[{filename}] Code column ('Code' or 'Fund Code') not found.")
                        # --- End Fund Code Extraction ---

                    except pd.errors.EmptyDataError:
                         status_info['latest_data_date'] = 'File is Empty'
                         status_info['funds_included'] = 'File is Empty' # Also set for funds
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
        return [{'filename': 'QueryMap Error', 'exists': False, 'last_modified': str(e), 'latest_data_date': '', 'funds_included': ''}]


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


# --- Helper function to find key columns ---
def _find_key_columns(df, filename):
    """Attempts to find the date and fund/identifier columns."""
    date_col = None
    fund_col = None

    # Date column candidates (add more if needed)
    date_candidates = ['Date', 'date', 'AsOfDate', 'ASOFDATE', 'Effective Date', 'Trade Date', 'Position Date']
    # Fund/ID column candidates
    fund_candidates = ['Code', 'Fund Code', 'Fundcode', 'security id', 'SecurityID', 'Security Name'] # Broadened list

    found_cols = df.columns.str.strip().str.lower()

    for candidate in date_candidates:
        if candidate.lower() in found_cols:
            # Find the original casing
            original_cols = [col for col in df.columns if col.strip().lower() == candidate.lower()]
            if original_cols:
                date_col = original_cols[0]
                current_app.logger.info(f"[{filename}] Found date column: '{date_col}'")
                break

    for candidate in fund_candidates:
        if candidate.lower() in found_cols:
            # Find the original casing
            original_cols = [col for col in df.columns if col.strip().lower() == candidate.lower()]
            if original_cols:
                fund_col = original_cols[0]
                current_app.logger.info(f"[{filename}] Found fund/ID column: '{fund_col}'")
                break

    if not date_col:
        current_app.logger.warning(f"[{filename}] Could not reliably identify a date column from candidates: {date_candidates}")
    if not fund_col:
        current_app.logger.warning(f"[{filename}] Could not reliably identify a fund/ID column from candidates: {fund_candidates}")

    return date_col, fund_col

@api_bp.route('/run_api_calls', methods=['POST'])
def run_api_calls():
    '''Handles the form submission to trigger API calls (real or simulated).
    Now supports:
    - date_mode: 'quick' (days_back + end_date) or 'range' (start_date + custom_end_date)
    - write_mode: 'expand' (append/overwrite overlaps) or 'overwrite_all' (start every file from scratch)
    '''
    try:
        # Get data from form
        data = request.get_json()
        date_mode = data.get('date_mode', 'quick')
        write_mode = data.get('write_mode', 'expand')
        days_back = int(data.get('days_back', 30)) # Default to 30 days if not provided
        end_date_str = data.get('end_date')
        start_date_str = data.get('start_date')
        custom_end_date_str = data.get('custom_end_date')
        selected_funds = data.get('funds', [])
        # Determine overwrite mode
        overwrite_mode = (write_mode == 'overwrite_all')

        # Date range logic
        if date_mode == 'range':
            if not start_date_str or not custom_end_date_str:
                return jsonify({"status": "error", "message": "Start and end date are required for custom range."}), 400
            start_date = pd.to_datetime(start_date_str)
            end_date = pd.to_datetime(custom_end_date_str)
        else:
            if not end_date_str:
                return jsonify({"status": "error", "message": "End date is required."}), 400
            end_date = pd.to_datetime(end_date_str)
            start_date = end_date - pd.Timedelta(days=days_back)
        # Format dates as YYYY-MM-DD for the TQS call
        start_date_tqs_str = start_date.strftime('%Y-%m-%d')
        end_date_tqs_str = end_date.strftime('%Y-%m-%d')

        if not selected_funds:
            return jsonify({"status": "error", "message": "At least one fund must be selected."}), 400

        # --- Get Query Map ---
        data_folder = current_app.config.get('DATA_FOLDER', 'Data')
        query_map_path = os.path.join(data_folder, 'QueryMap.csv')
        if not os.path.exists(query_map_path):
            return jsonify({"status": "error", "message": f"QueryMap.csv not found at {query_map_path}"}), 500

        query_map_df = pd.read_csv(query_map_path)
        if not {'QueryID', 'FileName'}.issubset(query_map_df.columns):
            return jsonify({"status": "error", "message": "QueryMap.csv missing required columns (QueryID, FileName)."}), 500

        # Sort queries: ts_*, pre_*, others
        def sort_key(query):
            filename = query.get('FileName', '').lower()
            if filename.startswith('ts_'):
                return 0
            elif filename.startswith('pre_'):
                return 1
            else:
                return 2
        queries_with_indices = list(enumerate(query_map_df.to_dict('records')))
        def sort_key_with_index(item):
            index, query = item
            filename = query.get('FileName', '').lower()
            if filename.startswith('ts_'):
                return (0, index)
            elif filename.startswith('pre_'):
                return (1, index)
            else:
                return (2, index)
        queries_with_indices.sort(key=sort_key_with_index)
        queries = [item[1] for item in queries_with_indices]
        current_app.logger.info(f"Processing order after sorting: {[q.get('FileName', 'N/A') for q in queries]}")

        results_summary = []
        total_queries = len(queries)
        completed_queries = 0
        all_ts_files_succeeded = True
        current_mode_desc = "SIMULATED mode" if not USE_REAL_TQS_API else ("REAL API mode (Overwrite Enabled)" if overwrite_mode else "REAL API mode (Merge/Append)")
        current_app.logger.info(f"--- Starting /run_api_calls in {current_mode_desc} ---")

        # Loop through sorted queries
        for query_info in queries:
            query_id = query_info.get('QueryID')
            file_name = query_info.get('FileName')
            if not query_id or not file_name:
                current_app.logger.warning(f"Skipping entry due to missing QueryID or FileName: {query_info}")
                summary = {
                    "query_id": query_id or "N/A", "file_name": file_name or "N/A",
                    "status": "Skipped (Missing QueryID/FileName)",
                    "simulated_rows": None, "simulated_lines": None,
                    "actual_rows": None, "actual_lines": None,
                    "save_action": "N/A", "validation_status": "Not Run",
                    "last_written": None
                }
                results_summary.append(summary)
                continue
            output_path = os.path.join(data_folder, file_name)
            summary = {
                "query_id": query_id,
                "file_name": file_name,
                "status": "Pending",
                "simulated_rows": None,
                "simulated_lines": None,
                "actual_rows": None,
                "actual_lines": None,
                "save_action": "N/A",
                "validation_status": "Not Run",
                "last_written": None
            }
            file_type = 'other'
            if file_name.lower().startswith('ts_'):
                file_type = 'ts'
            elif file_name.lower().startswith('pre_'):
                file_type = 'pre'
            current_app.logger.info(f"--- Starting Process for QueryID: {query_id}, File: {file_name} (Type: {file_type}) ---")
            if file_type == 'pre' and not all_ts_files_succeeded:
                current_app.logger.warning(f"[{file_name}] Skipping pre_ file because a previous ts_ file failed processing.")
                summary['status'] = 'Skipped (Previous TS Failure)'
                summary['validation_status'] = 'Not Run'
                summary['save_action'] = 'Skipped'
                results_summary.append(summary)
                completed_queries += 1
                continue
            try:
                if USE_REAL_TQS_API:
                    df_new = None
                    df_to_save = None
                    force_overwrite = overwrite_mode
                    try:
                        df_new = _fetch_real_tqs_data(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)
                        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        if df_new is None:
                            current_app.logger.warning(f"[{file_name}] No data returned from API call for QueryID {query_id}.")
                            summary['status'] = 'Warning - No data returned from API'
                            summary['validation_status'] = 'Skipped (API Returned None)'
                            summary['last_written'] = now_str
                            if file_type == 'ts': all_ts_files_succeeded = False
                        elif df_new.empty:
                            current_app.logger.warning(f"[{file_name}] Empty DataFrame returned from API call for QueryID {query_id}.")
                            summary['status'] = 'Warning - Empty data returned from API'
                            summary['validation_status'] = 'OK (Empty Data)'
                            df_to_save = df_new
                            summary['actual_rows'] = 0
                            summary['last_written'] = now_str
                        else:
                            current_app.logger.info(f"[{file_name}] Fetched {len(df_new)} new rows.")
                            summary['actual_rows'] = len(df_new)
                            df_to_save = df_new
                            summary['last_written'] = now_str
                        if df_new is not None:
                            if file_type == 'ts':
                                current_app.logger.info(f"[{file_name}] Processing as ts_ file (Overwrite Mode: {force_overwrite}).")
                                try:
                                    if not df_new.empty:
                                        date_col_new, fund_col_new = _find_key_columns(df_new, f"{file_name} (New TS Data)")
                                        if not date_col_new or not fund_col_new:
                                            err_msg = f"Could not find essential date/fund columns in fetched ts_ data for {file_name}. Cannot proceed."
                                            current_app.logger.error(f"[{file_name}] {err_msg}")
                                            raise ValueError(err_msg)
                                    else:
                                        date_col_new, fund_col_new = None, None
                                        current_app.logger.info(f"[{file_name}] Skipping key column check for empty TS data.")
                                    if force_overwrite:
                                        current_app.logger.info(f"[{file_name}] Overwrite Mode enabled. Skipping check for existing file.")
                                        if os.path.exists(output_path):
                                            summary['save_action'] = 'Overwritten (User Request)'
                                        else:
                                            summary['save_action'] = 'Created (Overwrite Mode)'
                                    elif os.path.exists(output_path):
                                        current_app.logger.info(f"[{file_name}] TS file exists. Reading existing data for merge/append.")
                                        try:
                                            df_existing = pd.read_csv(output_path, low_memory=False)
                                            if not df_existing.empty:
                                                if date_col_new and fund_col_new:
                                                    date_col_existing, fund_col_existing = _find_key_columns(df_existing, f"{file_name} (Existing TS)")
                                                    if date_col_existing == date_col_new and fund_col_existing == fund_col_new:
                                                        date_col = date_col_new
                                                        fund_col = fund_col_new
                                                        df_existing[fund_col] = df_existing[fund_col].astype(str)
                                                        df_new[fund_col] = df_new[fund_col].astype(str)
                                                        funds_in_new_data = [str(f) for f in df_new[fund_col].unique()]
                                                        if date_col in df_existing.columns and date_col in df_new.columns:
                                                            dates_in_new = df_new[date_col].astype(str).unique()
                                                            mask = ~((df_existing[fund_col].isin(funds_in_new_data)) & (df_existing[date_col].astype(str).isin(dates_in_new)))
                                                            df_existing_filtered = df_existing[mask]
                                                        else:
                                                            df_existing_filtered = df_existing[~df_existing[fund_col].isin(funds_in_new_data)]
                                                        df_combined = pd.concat([df_existing_filtered, df_new], ignore_index=True)
                                                        try:
                                                            df_combined = df_combined.sort_values(by=[date_col, fund_col])
                                                        except Exception as sort_err:
                                                            current_app.logger.warning(f"[{file_name}] Could not sort combined data: {sort_err}")
                                                        df_to_save = df_combined
                                                        summary['save_action'] = 'Combined (Append/Overwrite)'
                                                        summary['last_written'] = now_str
                                                        current_app.logger.info(f"[{file_name}] Prepared combined data ({len(df_to_save)} rows).")
                                                    else:
                                                        current_app.logger.warning(f"[{file_name}] Key columns mismatch between existing ({date_col_existing}, {fund_col_existing}) and new ({date_col_new}, {fund_col_new}). Overwriting entire file.")
                                                        summary['save_action'] = 'Overwritten (Column Mismatch)'
                                                        summary['last_written'] = now_str
                                                else:
                                                    current_app.logger.warning(f"[{file_name}] Cannot merge TS data as key columns were not identified in new data. Overwriting.")
                                                    summary['save_action'] = 'Overwritten (Merge Skipped)'
                                                    summary['last_written'] = now_str
                                            else:
                                                current_app.logger.warning(f"[{file_name}] Existing TS file is empty. Overwriting.")
                                                summary['save_action'] = 'Overwritten (Existing Empty)'
                                                summary['last_written'] = now_str
                                        except pd.errors.EmptyDataError:
                                            current_app.logger.warning(f"[{file_name}] Existing TS file is empty (EmptyDataError). Overwriting.")
                                            summary['save_action'] = 'Overwritten (Existing Empty)'
                                            summary['last_written'] = now_str
                                        except Exception as read_err:
                                            current_app.logger.error(f"[{file_name}] Error reading existing TS file: {read_err}. Overwriting.", exc_info=True)
                                            summary['save_action'] = 'Overwritten (Read Error)'
                                            summary['last_written'] = now_str
                                            all_ts_files_succeeded = False
                                    else:
                                        current_app.logger.info(f"[{file_name}] TS file does not exist (or overwrite mode is on and file was absent). Creating new file.")
                                        summary['save_action'] = 'Created'
                                        summary['last_written'] = now_str
                                except ValueError as ve:
                                    current_app.logger.error(f"[{file_name}] TS validation failed: {ve}")
                                    summary['status'] = f'Error - TS Validation Failed: {ve}'
                                    summary['validation_status'] = 'Failed (Missing Columns)'
                                    summary['last_written'] = now_str
                                    all_ts_files_succeeded = False
                                    df_to_save = None
                            elif file_type == 'pre':
                                current_app.logger.info(f"[{file_name}] Processing as pre_ file (checking column count).")
                                if os.path.exists(output_path):
                                    try:
                                        if not df_new.empty:
                                            existing_header_df = pd.read_csv(output_path, nrows=0, low_memory=False)
                                            existing_cols = existing_header_df.columns.tolist()
                                            new_cols = df_new.columns.tolist()
                                            if force_overwrite or len(existing_cols) != len(new_cols) or set(existing_cols) != set(new_cols):
                                                if force_overwrite:
                                                    current_app.logger.info(f"[{file_name}] Overwriting pre_ file as requested by user.")
                                                    summary['save_action'] = 'Overwritten (User Request)'
                                                else:
                                                    current_app.logger.warning(f"[{file_name}] Column count/names mismatch between existing pre_ file ({len(existing_cols)} cols: {existing_cols}) and new data ({len(new_cols)} cols: {new_cols}). Overwriting.")
                                                    summary['save_action'] = 'Overwritten (Column Mismatch)'
                                            else:
                                                current_app.logger.info(f"[{file_name}] Existing pre_ file found with matching columns. Overwriting.")
                                                summary['save_action'] = 'Overwritten'
                                        else:
                                            current_app.logger.info(f"[{file_name}] New data for pre_ file is empty. Overwriting existing file.")
                                            summary['save_action'] = 'Overwritten (New Data Empty)'
                                    except pd.errors.EmptyDataError:
                                        current_app.logger.warning(f"[{file_name}] Existing pre_ file is empty (EmptyDataError). Overwriting.")
                                        summary['save_action'] = 'Overwritten (Existing Empty)'
                                    except Exception as read_err:
                                        current_app.logger.error(f"[{file_name}] Error reading existing pre_ file header: {read_err}. Overwriting.", exc_info=True)
                                        summary['save_action'] = 'Overwritten (Read Error)'
                                else:
                                    current_app.logger.info(f"[{file_name}] Pre_ file does not exist. Creating new file.")
                                    summary['save_action'] = 'Created'
                            else:
                                current_app.logger.info(f"[{file_name}] Processing as 'other' file type (using column count check).")
                                if os.path.exists(output_path):
                                    try:
                                        if not df_new.empty:
                                            existing_header_df = pd.read_csv(output_path, nrows=0, low_memory=False)
                                            existing_cols = existing_header_df.columns.tolist()
                                            new_cols = df_new.columns.tolist()
                                            if force_overwrite or len(existing_cols) != len(new_cols) or set(existing_cols) != set(new_cols):
                                                if force_overwrite:
                                                    current_app.logger.info(f"[{file_name}] Overwriting 'other' file as requested by user.")
                                                    summary['save_action'] = 'Overwritten (User Request)'
                                                else:
                                                    current_app.logger.warning(f"[{file_name}] Column count/names mismatch for 'other' file. Overwriting.")
                                                    summary['save_action'] = 'Overwritten (Column Mismatch)'
                                            else:
                                                current_app.logger.info(f"[{file_name}] Existing 'other' file found with matching columns. Overwriting.")
                                                summary['save_action'] = 'Overwritten'
                                        else:
                                            current_app.logger.info(f"[{file_name}] New data for 'other' file is empty. Overwriting existing file.")
                                            summary['save_action'] = 'Overwritten (New Data Empty)'
                                    except pd.errors.EmptyDataError:
                                        current_app.logger.warning(f"[{file_name}] Existing 'other' file is empty (EmptyDataError). Overwriting.")
                                        summary['save_action'] = 'Overwritten (Existing Empty)'
                                    except Exception as read_err:
                                        current_app.logger.error(f"[{file_name}] Error reading existing 'other' file header: {read_err}. Overwriting.", exc_info=True)
                                        summary['save_action'] = 'Overwritten (Read Error)'
                                else:
                                    current_app.logger.info(f"[{file_name}] 'Other' file does not exist. Creating new file.")
                                    summary['save_action'] = 'Created'
                            # 4. Save the Final DataFrame (Common step, if df_to_save is valid)
                            if df_to_save is not None:
                                current_app.logger.info(f"[{file_name}] Attempting to save {len(df_to_save)} rows to {output_path} (Action: {summary['save_action']})")
                                try:
                                    df_to_save.to_csv(output_path, index=False, header=True)
                                    current_app.logger.info(f"[{file_name}] Successfully saved data to {output_path}")
                                    summary['status'] = 'OK - Data Saved'
                                    try:
                                        with open(output_path, 'r', encoding='utf-8') as f:
                                            summary['actual_lines'] = sum(1 for line in f)
                                    except Exception:
                                        summary['actual_lines'] = 'N/A'
                                    summary['validation_status'] = validate_data(df_to_save, file_name)
                                    current_app.logger.info(f"[{file_name}] Validation status: {summary['validation_status']})")
                                except Exception as write_err:
                                    current_app.logger.error(f"[{file_name}] Error writing final data to {output_path}: {write_err}", exc_info=True)
                                    summary['status'] = f'Error - Failed to save file: {write_err}'
                                    summary['validation_status'] = 'Failed (Save Error)'
                                    if file_type == 'ts': all_ts_files_succeeded = False
                            elif df_new is None:
                                pass
                            elif df_to_save is None and file_type == 'ts':
                                pass
                            else:
                                current_app.logger.error(f"[{file_name}] Reached unexpected state where df_to_save is None but no prior error logged.")
                                summary['status'] = 'Error - Internal Logic Error (df_to_save is None)'
                    except Exception as proc_err:
                        current_app.logger.error(f"Error processing real data for QueryID {query_id}, File {file_name}: {proc_err}", exc_info=True)
                        summary['status'] = f'Error - Processing failed: {proc_err}'
                        summary['validation_status'] = 'Failed (Processing Error)'
                        summary['last_written'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        if file_type == 'ts': all_ts_files_succeeded = False
                else:
                    # Simulation Mode
                    simulated_rows = _simulate_and_print_tqs_call(query_id, selected_funds, start_date_tqs_str, end_date_tqs_str)
                    summary['simulated_rows'] = simulated_rows
                    summary['simulated_lines'] = simulated_rows + 1 if simulated_rows > 0 else 0
                    summary['status'] = 'Simulated OK'
                    summary['save_action'] = 'Not Applicable'
                    summary['validation_status'] = 'Not Run (Simulated)'
                    summary['last_written'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            except Exception as outer_err:
                current_app.logger.error(f"Unexpected outer error processing QueryID {query_id} ({file_name}): {outer_err}", exc_info=True)
                if summary['status'] == 'Pending' or summary['status'].startswith('Warning'):
                    summary['status'] = f"Outer Processing Error: {outer_err}"
                if file_type == 'ts': all_ts_files_succeeded = False
                summary['last_written'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            results_summary.append(summary)
            completed_queries += 1
            if USE_REAL_TQS_API and completed_queries < total_queries:
                print(f"Pausing for 3 seconds before next real API call ({completed_queries}/{total_queries})...")
                time.sleep(3)

        mode_message = "SIMULATED mode" if not USE_REAL_TQS_API else ("REAL API mode (Overwrite Enabled)" if overwrite_mode else "REAL API mode (Merge/Append)")
        final_status = "completed"
        if USE_REAL_TQS_API and not all_ts_files_succeeded:
            completion_message = f"Processed {completed_queries}/{total_queries} API calls ({mode_message}). WARNING: One or more ts_ files failed processing or validation."
            final_status = "completed_with_errors"
        else:
            completion_message = f"Processed {completed_queries}/{total_queries} API calls ({mode_message})."
        return jsonify({
            "status": final_status,
            "message": completion_message,
            "summary": results_summary
        })
    except ValueError as ve:
        current_app.logger.error(f"Value error in /run_api_calls: {ve}", exc_info=True)
        return jsonify({"status": "error", "message": f"Invalid input value: {ve}"}), 400
    except FileNotFoundError as fnf:
        current_app.logger.error(f"File not found error in /run_api_calls: {fnf}", exc_info=True)
        return jsonify({"status": "error", "message": f"Required file not found: {fnf}"}), 500
    except Exception as e:
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
        overwrite_mode = data.get('overwrite_mode', False) # Get the new overwrite flag

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
        simulated_rows = None # Initialize simulation keys too
        simulated_lines = None

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
            "simulated_rows": simulated_rows, # Value if simulated, None otherwise
            "actual_rows": rows_returned if USE_REAL_TQS_API else None, # Value if real, None otherwise
            "simulated_lines": simulated_lines, # Value if simulated, None otherwise
            "actual_lines": lines_in_file if USE_REAL_TQS_API else None # Value if real, None otherwise
        }

        return jsonify(result_data)

    except ValueError as ve:
        current_app.logger.error(f"Value error in /rerun-api-call: {ve}", exc_info=True)
        return jsonify({"status": "error", "message": f"Invalid input value: {ve}"}), 400
    except FileNotFoundError as fnf:
        current_app.logger.error(f"File not found error in /rerun-api-call: {fnf}", exc_info=True)
        return jsonify({"status": "error", "message": f"Required file not found: {fnf}"}), 500
    except Exception as e: # <-- Corrected indentation for line 675
        current_app.logger.error(f"Unexpected error in /rerun-api-call: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500

# Ensure no code remains after this point in the file for this function.