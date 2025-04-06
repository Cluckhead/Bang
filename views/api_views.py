'''
Defines the Flask Blueprint for handling API data retrieval requests.
'''
import os
import pandas as pd
from flask import Blueprint, render_template, request, current_app, jsonify
import datetime
from pandas.tseries.offsets import BDay
#import tqs
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
    '''Placeholder for fetching real data from the TQS API.

    This function is called when USE_REAL_TQS_API is True.
    Replace the placeholder logic with the actual API interaction code.

    Args:
        QueryID: The query identifier.
        FundCodeList: List of fund codes.
        StartDate: Start date string (dd/mm/yy).
        EndDate: End date string (dd/mm/yy).

    Returns:
        pd.DataFrame or None: The DataFrame containing the fetched data,
                              or None if the API call fails or returns no data.
    '''
    current_app.logger.info(f"Attempting real TQS API call for QueryID: {QueryID}")
    print(f"--- EXECUTING REAL TQS API CALL (USE_REAL_TQS_API = True) --- ")
    print(f"tqs({QueryID}, {FundCodeList}, {StartDate}, {EndDate})") # Log the call
    print(f"--------------------------------------------------------")

    # --- Replace this section with the actual TQS API call --- 
    # Example using a hypothetical library `tqs_api_library`
    try:
        # dataframe = tqs_api_library.fetch_data(query_id=QueryID,
        #                                        funds=FundCodeList,
        #                                        start=StartDate,
        #                                        end=EndDate,
        #                                        timeout=300) # Example 5 min timeout
        # Mock success for demonstration when USE_REAL_TQS_API is True
        print("    [Placeholder] Real API call would happen here.")
        # Create a simple dummy DataFrame for testing the flow
        num_rows = len(FundCodeList) * 5 # Different dummy calculation for real mode
        if num_rows > 0:
             dummy_data = {'Date': pd.to_datetime([datetime.date.today() - datetime.timedelta(days=i) for i in range(num_rows//len(FundCodeList))]*len(FundCodeList)),
                           'Code': [f for f in FundCodeList for _ in range(num_rows//len(FundCodeList))],
                           'Value': [100+i for i in range(num_rows)]}
             dataframe = pd.DataFrame(dummy_data)
             print(f"    [Placeholder] Successfully created dummy DataFrame with {len(dataframe)} rows.")
        else:
             dataframe = pd.DataFrame() # Return empty df if no funds
             print("    [Placeholder] No funds selected, returning empty DataFrame.")

        # Check if the API returned valid data (e.g., a DataFrame)
        if dataframe is not None and isinstance(dataframe, pd.DataFrame):
            current_app.logger.info(f"Real TQS API call successful for QueryID: {QueryID}, Rows: {len(dataframe)}")
            return dataframe
        else:
            current_app.logger.warning(f"Real TQS API call for QueryID: {QueryID} returned no data or invalid format.")
            return None
    except Exception as e:
        # Handle API call errors (timeout, connection issues, authentication, etc.)
        current_app.logger.error(f"Real TQS API call failed for QueryID: {QueryID}. Error: {e}", exc_info=True)
        print(f"    [Placeholder] Real API call FAILED. Error: {e}")
        return None
    # --- End of placeholder section ---


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

    except Exception as e:
        current_app.logger.error(f"Error preparing get_data page: {e}", exc_info=True)
        # Provide a user-friendly error message, specific details are logged
        return f"An error occurred while preparing the data retrieval page: {e}", 500

    return render_template('get_data.html', funds=funds, default_end_date=default_end_date)


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
        # Format dates as DD/MM/YY for the tqs call simulation
        start_date_tqs_str = start_date.strftime('%d/%m/%y')
        end_date_tqs_str = end_date.strftime('%d/%m/%y')

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

                    if actual_df is not None:
                        rows_returned = len(actual_df)
                        # Validate the DataFrame structure
                        is_valid, validation_errors = validate_data(actual_df, file_name)
                        if not is_valid:
                            current_app.logger.warning(f"Data validation failed for {file_name}: {validation_errors}")
                            status = f"Validation Failed: {'; '.join(validation_errors)}"
                            lines_in_file = 0 # Don't save invalid data
                        else:
                            # Save the DataFrame to CSV
                            try:
                                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                                actual_df.to_csv(output_path, index=False)
                                current_app.logger.info(f"Successfully saved data to {output_path}")
                                lines_in_file = rows_returned + 1 # +1 for header
                                status = "Saved OK"
                            except Exception as e:
                                current_app.logger.error(f"Error saving DataFrame to {output_path}: {e}", exc_info=True)
                                status = f"Save Error: {e}"
                                lines_in_file = 0 # Save failed
                    else:
                        # _fetch_real_tqs_data returned None (API call failed or no data)
                        current_app.logger.warning(f"Real API call for {query_id} ({file_name}) returned no data or failed.")
                        status = "No Data/API Error"
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
                # Use consistent key names regardless of mode
                "simulated_rows": rows_returned, # Keep key name for template consistency
                "simulated_lines": lines_in_file, # Keep key name for template consistency
                "status": status
            })
            completed_queries += 1
            # In an async setup, you would emit progress here (e.g., via SocketIO)
            # print(f"Progress: {completed_queries}/{total_queries} queries simulated.")

        # Return results
        return jsonify({
            "status": "completed",
            "message": f"Processed {completed_queries}/{total_queries} API calls ({'REAL' if USE_REAL_TQS_API else 'SIMULATED'} mode).",
            "summary": results_summary
        })

    except ValueError as ve:
        current_app.logger.error(f"Value error processing API call request: {ve}", exc_info=True)
        return jsonify({"status": "error", "message": f"Invalid input: {ve}"}), 400
    except FileNotFoundError as fnf:
        current_app.logger.error(f"File not found during API call processing: {fnf}", exc_info=True)
        return jsonify({"status": "error", "message": f"Configuration file missing: {fnf.filename}"}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error running API calls: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected error occurred."}), 500

# Removed the placeholder validate_data function from here as it's now imported 