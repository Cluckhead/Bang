# views/weight_views.py
# Purpose: Handles routes related to weight checks (e.g., ensuring weights are 100%).

import os
import pandas as pd
import traceback
import logging
from flask import Blueprint, render_template, current_app
from utils import _is_date_like
from typing import Tuple, Dict, List, Any

# Define the blueprint
weight_bp = Blueprint("weight", __name__, url_prefix="/weights")


def _parse_percentage(value):
    """Attempts to parse a string like '99.5%' into a float 99.5."""
    if pd.isna(value) or value == "":
        return None
    try:
        # Remove '%' and convert to float
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        logging.warning(f"Could not parse percentage value: {value}")
        return None  # Indicate parsing failure


def load_and_process_weight_data(
    data_folder_path: str, filename: str
) -> Tuple[Dict[str, Any], List[str]]:
    """Loads a wide weight file, converts decimal values to percentages, checks against 100%.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        filename (str): The name of the weight file (e.g., 'w_Funds.csv').

    Returns:
        tuple: (dict | None, list[str])
               - Dictionary of processed data {fund_code: {date: {data}}} or None on error.
               - List of sorted date headers (YYYY-MM-DD) found in the file.
    """
    if not data_folder_path:
        logging.error(f"No data_folder_path provided for file {filename}")
        return None, []
    filepath = os.path.join(data_folder_path, filename)
    if not os.path.exists(filepath):
        logging.error(f"Weight file not found: {filepath}")
        return None, []

    try:
        df = pd.read_csv(filepath, encoding="utf-8")
        df.columns = df.columns.str.strip()  # Ensure no leading/trailing spaces

        # Identify ID column (assuming 'Fund Code')
        id_col = "Fund Code"
        if id_col not in df.columns:
            logging.error(f"Required column '{id_col}' not found in {filename}")
            return None, []

        # Identify date columns based on ISO format
        date_cols = [col for col in df.columns if _is_date_like(col)]
        if not date_cols:
            logging.warning(f"No date-like columns found in {filename}")
            return None, []

        # Sort date columns chronologically
        # Convert to datetime objects for reliable sorting
        datetime_objs = [pd.to_datetime(d) for d in date_cols]
        # Sort based on datetime objects
        datetime_objs.sort()
        # Convert back to display format (YYYY-MM-DD) after sorting
        date_headers_display = [dt.strftime("%Y-%m-%d") for dt in datetime_objs]
        # Get the original column names corresponding to the sorted display headers
        # We need this to access the correct columns in the DataFrame later
        # Create a map from display format back to original format
        display_to_original_map = {
            pd.to_datetime(d).strftime("%Y-%m-%d"): d for d in date_cols
        }
        original_date_cols_sorted = [
            display_to_original_map[d] for d in date_headers_display
        ]

        processed_data = {}
        # Set index for easier access
        df.set_index(id_col, inplace=True)

        for fund_code in df.index:
            processed_data[fund_code] = {}
            # Iterate using the sorted original column names and the sorted display headers
            for original_date_col, display_date_header in zip(
                original_date_cols_sorted, date_headers_display
            ):
                original_value_str = str(df.loc[fund_code, original_date_col])
                # --- Updated Logic for Decimal Input ---
                calculated_percentage = None
                try:
                    # Attempt to convert the raw value directly to float
                    decimal_value = float(original_value_str)
                    # Convert decimal to percentage
                    calculated_percentage = decimal_value * 100.0
                except (ValueError, TypeError):
                    # Handle cases where the value is not a valid number
                    logging.warning(
                        f"Could not convert value to float for {fund_code} on {display_date_header} in {filename}: {original_value_str}"
                    )
                    calculated_percentage = None  # Ensure it remains None
                # --- End Updated Logic ---

                is_100 = False
                formatted_value_str = (
                    "N/A"  # Default if conversion fails or value is NaN
                )

                if calculated_percentage is not None:
                    # Check if the calculated percentage is within the tolerance range
                    tolerance = 0.01  # e.g., allows 99.99 to 100.01
                    is_100 = abs(calculated_percentage - 100.0) <= tolerance
                    # Format the calculated percentage as a string with 2 decimal places
                    formatted_value_str = f"{calculated_percentage:.2f}%"

                # Store the formatted percentage string and the boolean check result
                processed_data[fund_code][display_date_header] = {
                    "value_percent_str": formatted_value_str,
                    "is_100": is_100,
                    # 'parsed_value': parsed_value_float # Keep for potential future use/debugging
                }

        return processed_data, date_headers_display

    except Exception as e:
        logging.error(f"Error processing weight file {filename}: {e}")
        traceback.print_exc()
        return None, []


@weight_bp.route("/check")
def weight_check():
    """Displays the weight check page."""
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # Detect file names in a case-insensitive manner to support different naming conventions
    def _locate_weight_file(base_dir: str, candidate_names: list[str]) -> str | None:
        """Return the first candidate that exists in *base_dir*, case-insensitive."""
        lower_map = {f.lower(): f for f in os.listdir(base_dir)}
        for cand in candidate_names:
            if cand.lower() in lower_map:
                return lower_map[cand.lower()]
        return None

    fund_filename = (
        _locate_weight_file(data_folder, ["w_Funds.csv", "w_fund.csv", "w_funds.csv"])
        or "w_Funds.csv"
    )
    bench_filename = (
        _locate_weight_file(data_folder, ["w_Bench.csv", "w_bench.csv"])
        or "w_Bench.csv"
    )

    # Pass the absolute data folder path to the helper function
    fund_data, fund_date_headers = load_and_process_weight_data(
        data_folder, fund_filename
    )
    bench_data, bench_date_headers = load_and_process_weight_data(
        data_folder, bench_filename
    )

    # Use the longer list of dates as the canonical header list, assuming they might differ slightly
    all_date_headers = sorted(list(set(fund_date_headers + bench_date_headers)))

    return render_template(
        "weight_check_page.html",
        fund_data=fund_data,
        bench_data=bench_data,
        date_headers=all_date_headers,  # Pass combined, sorted list
        fund_filename=fund_filename,
        bench_filename=bench_filename,
    )
