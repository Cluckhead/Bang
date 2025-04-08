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

def _is_iso_date_column(col_name):
    """Checks if a column name matches YYYY-MM-DDTHH:MM:SS format."""
    try:
        # Attempt to parse using pandas, strict match needed
        pd.to_datetime(col_name, format='%Y-%m-%dT%H:%M:%S', errors='raise')
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
        date_cols_iso = [col for col in df.columns if _is_iso_date_column(col)]
        if not date_cols_iso:
            logging.warning(f"No date columns found in expected format in {filename}")
            # Fallback: Try simple YYYY-MM-DD check? For now, let's stick to expected format.
            return None, []

        # Sort date columns chronologically
        date_cols_sorted = sorted(date_cols_iso, key=lambda d: pd.to_datetime(d, format='%Y-%m-%dT%H:%M:%S'))
        
        # Simplify date headers for display (YYYY-MM-DD)
        date_headers_display = [pd.to_datetime(d).strftime('%Y-%m-%d') for d in date_cols_sorted]

        processed_data = {}
        # Set index for easier access
        df.set_index(id_col, inplace=True)

        for fund_code in df.index:
            processed_data[fund_code] = {}
            for date_col_iso, date_header_display in zip(date_cols_sorted, date_headers_display):
                original_value_str = str(df.loc[fund_code, date_col_iso])
                parsed_value_float = _parse_percentage(original_value_str)
                
                is_100 = False
                if parsed_value_float is not None:
                    # Check for exact equality with 100.0
                    is_100 = (parsed_value_float == 100.0)
                
                processed_data[fund_code][date_header_display] = {
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
    fund_filename = 'w_Fund.csv'
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