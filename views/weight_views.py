# views/weight_views.py
# Purpose: Handles routes related to weight checks (e.g., ensuring weights are 100%).

import os
import pandas as pd
import traceback
import logging
from flask import Blueprint, render_template
from config import DATA_FOLDER

# Define the blueprint
weight_bp = Blueprint('weight', __name__, url_prefix='/weights')

def _parse_percentage(value):
    """Attempts to parse a string like '99.5%' into a float 99.5."""
    if pd.isna(value) or value == '':
        return None
    try:
        # Remove '%' and convert to float
        return float(str(value).replace('%', '').strip())
    except (ValueError, TypeError):
        logging.warning(f"Could not parse percentage value: {value}")
        return None # Indicate parsing failure

def _is_date_like_column(col_name):
    """Checks if a column name matches YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format."""
    try:
        # Attempt to parse using pandas with flexible inference first
        # errors='raise' will fail if it's not recognizable as a date/datetime
        pd.to_datetime(col_name, errors='raise')
        # Optionally, add more specific format checks if needed, but `to_datetime` is quite good
        # e.g., check if it matches common regex patterns if `to_datetime` is too broad
        return True
    except (ValueError, TypeError):
        return False

def load_and_process_weight_data(filename):
    """Loads a wide weight file, processes percentages, checks against 100%."""
    filepath = os.path.join(DATA_FOLDER, filename)
    if not os.path.exists(filepath):
        logging.error(f"Weight file not found: {filepath}")
        return None, [] # Return None for data, empty list for headers

    try:
        df = pd.read_csv(filepath, encoding='utf-8')
        df.columns = df.columns.str.strip() # Ensure no leading/trailing spaces

        # Identify ID column (assuming 'Fund Code')
        id_col = 'Fund Code'
        if id_col not in df.columns:
            logging.error(f"Required column '{id_col}' not found in {filename}")
            return None, []
        
        # Identify date columns based on ISO format
        date_cols = [col for col in df.columns if _is_date_like_column(col)]
        if not date_cols:
            logging.warning(f"No date-like columns found in {filename}")
            return None, []

        # Sort date columns chronologically
        # Convert to datetime objects for reliable sorting
        datetime_objs = [pd.to_datetime(d) for d in date_cols]
        # Sort based on datetime objects
        datetime_objs.sort()
        # Convert back to display format (YYYY-MM-DD) after sorting
        date_headers_display = [dt.strftime('%Y-%m-%d') for dt in datetime_objs]
        # Get the original column names corresponding to the sorted display headers
        # We need this to access the correct columns in the DataFrame later
        # Create a map from display format back to original format
        display_to_original_map = {pd.to_datetime(d).strftime('%Y-%m-%d'): d for d in date_cols}
        original_date_cols_sorted = [display_to_original_map[d] for d in date_headers_display]

        processed_data = {}
        # Set index for easier access
        df.set_index(id_col, inplace=True)

        for fund_code in df.index:
            processed_data[fund_code] = {}
            # Iterate using the sorted original column names and the sorted display headers
            for original_date_col, display_date_header in zip(original_date_cols_sorted, date_headers_display):
                original_value_str = str(df.loc[fund_code, original_date_col])
                parsed_value_float = _parse_percentage(original_value_str)
                
                is_100 = False
                if parsed_value_float is not None:
                    # Check if the value is within the tolerance range [99.99, 100.01]
                    is_100 = abs(parsed_value_float - 100.0) <= 0.01
                
                processed_data[fund_code][display_date_header] = {
                    'value_str': original_value_str if not pd.isna(original_value_str) else 'N/A',
                    'is_100': is_100,
                    'parsed_value': parsed_value_float # Keep for potential future use/debugging
                }
                
        return processed_data, date_headers_display

    except Exception as e:
        logging.error(f"Error processing weight file {filename}: {e}")
        traceback.print_exc()
        return None, []


@weight_bp.route('/check')
def weight_check():
    """Displays the weight check page."""
    fund_filename = 'w_Funds.csv'
    bench_filename = 'w_Bench.csv'

    fund_data, fund_date_headers = load_and_process_weight_data(fund_filename)
    bench_data, bench_date_headers = load_and_process_weight_data(bench_filename)

    # Use the longer list of dates as the canonical header list, assuming they might differ slightly
    all_date_headers = sorted(list(set(fund_date_headers + bench_date_headers)))

    return render_template('weight_check_page.html',
                           fund_data=fund_data,
                           bench_data=bench_data,
                           date_headers=all_date_headers, # Pass combined, sorted list
                           fund_filename=fund_filename,
                           bench_filename=bench_filename) 