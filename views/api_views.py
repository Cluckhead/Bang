'''
Defines the Flask Blueprint for handling API data retrieval requests.
'''
import os
import pandas as pd
from flask import Blueprint, render_template, request, current_app, jsonify
import datetime
from pandas.tseries.offsets import BDay

# Import the placeholder validation function
from data_validation import validate_data

# Blueprint Configuration
api_bp = Blueprint(
    'api_bp', __name__,
    template_folder='../templates',
    static_folder='../static'
)

# Simulated REX API function (replace with actual API call later)
def Rex(QueryID, FundCodeList, StartDate, EndDate):
    '''Simulates calling the REX API.

    In a real scenario, this function would interact with the external REX API.
    For now, it prints the intended call signature and returns a dummy result.
    '''
    # Format the call signature exactly as requested: rex(QueryID,[FundList],StartDate,EndDate)
    call_signature = f"rex({QueryID}, {FundCodeList}, {StartDate}, {EndDate})"
    print(f"--- SIMULATING API CALL ---")
    print(call_signature)
    print(f"--------------------------")
    # Simulate returning a DataFrame structure or row count
    # In a real implementation, return the actual DataFrame
    # For demonstration, we'll return a simulated row count
    # The checks should not fail in simulation, return a positive dummy count
    simulated_row_count = len(FundCodeList) * 10 if FundCodeList else 0 # Dummy calculation
    return simulated_row_count


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
    '''Handles the form submission to trigger (simulated) API calls.'''
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
        # Format dates as DD/MM/YY for the rex call simulation
        start_date_rex_str = start_date.strftime('%d/%m/%y')
        end_date_rex_str = end_date.strftime('%d/%m/%y')

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
            status = "Simulated OK"
            actual_df = None # Placeholder for real API result

            try:
                # Simulate API call
                # Add error handling (try/except) and timeout for real API calls
                # A 5-minute timeout per query would be implemented here in a real scenario.
                simulated_rows = Rex(query_id, selected_funds, start_date_rex_str, end_date_rex_str)

                # --- Placeholder for processing/saving the *actual* DataFrame ---
                # In a real scenario, the Rex function would return the DataFrame:
                # actual_df = Rex(query_id, selected_funds, start_date_rex_str, end_date_rex_str)

                # if actual_df is not None and not actual_df.empty:
                #     # 1. Validate the DataFrame structure (using imported validate_data)
                #     is_valid, validation_errors = validate_data(actual_df, file_name)
                #     if not is_valid:
                #         current_app.logger.warning(f"Data validation failed for {file_name}: {validation_errors}")
                #         status = f"Validation Failed: {'; '.join(validation_errors)}"
                #         simulated_file_lines = 0 # Or based on df if saved despite errors
                #     else:
                #         # 2. Save the DataFrame to CSV (Uncomment to enable saving)
                #         try:
                #             # Ensure the directory exists before saving
                #             # os.makedirs(os.path.dirname(output_path), exist_ok=True)
                #             # actual_df.to_csv(output_path, index=False)
                #             # current_app.logger.info(f"Successfully saved data to {output_path}")
                #             # simulated_file_lines = len(actual_df) + 1 # +1 for header
                #             pass # Keep pass here until uncommenting above lines
                #             status = "Saved OK"
                #         except Exception as e:
                #             current_app.logger.error(f"Error saving DataFrame to {output_path}: {e}")
                #             status = f"Save Error: {e}"
                #             simulated_file_lines = 0
                # else:
                #     current_app.logger.warning(f"Simulated API call for {query_id} ({file_name}) returned no data or failed.")
                #     status = "No Data Returned"
                #     simulated_file_lines = 0
                # ---- End Placeholder -----

                # Simulate file lines based on simulated rows (very rough estimate for now)
                simulated_file_lines = simulated_rows + 1 if simulated_rows > 0 else 0

            except Exception as api_error:
                 # Catch potential errors during the *simulated* call phase
                 current_app.logger.error(f"Error during simulated API call for QueryID {query_id}: {api_error}")
                 status = f"Simulation Error: {api_error}"
                 simulated_rows = 0
                 simulated_file_lines = 0

            results_summary.append({
                "query_id": query_id,
                "file_name": file_name,
                "simulated_rows": simulated_rows,
                "simulated_lines": simulated_file_lines,
                "status": status
            })
            completed_queries += 1
            # In an async setup, you would emit progress here (e.g., via SocketIO)
            # print(f"Progress: {completed_queries}/{total_queries} queries simulated.")

        # Return results
        return jsonify({
            "status": "completed",
            "message": f"Simulated {completed_queries}/{total_queries} API calls.",
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