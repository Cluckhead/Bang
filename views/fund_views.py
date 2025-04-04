"""Blueprint for fund-specific routes, currently focusing on duration details."""

from flask import Blueprint, render_template
import os
import pandas as pd
import traceback

# Import necessary functions from other modules
from config import DATA_FOLDER
from utils import _is_date_like, parse_fund_list # Import required utils

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