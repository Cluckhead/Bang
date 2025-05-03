"""
Defines core functionality for the API views, including shared helper functions,
the Flask Blueprint, and feature switch configurations.
"""

import os
import pandas as pd
from flask import Blueprint, current_app, request, jsonify, render_template, Response
from typing import Dict, List, Optional, Tuple, Any, Union
import datetime
import config
import time
from data_validation import validate_data

# from tqs import tqs_query as tqs

# --- Feature Switch ---
# Set to True to attempt real API calls, validation, and saving.
# Set to False to only simulate the API call (print to console).
USE_REAL_TQS_API = False
# ----------------------

# Blueprint Configuration
api_bp = Blueprint(
    "api_bp",
    __name__,
    template_folder="../templates",
    static_folder="../static",
    url_prefix="/api",
)


def _simulate_and_print_tqs_call(QueryID, FundCodeList, StartDate, EndDate):
    """Simulates a TQS API call by printing the details and returning a simulated row count.

    This function is called when USE_REAL_TQS_API is False.
    It does NOT interact with any external API.

    Returns:
        int: A simulated number of rows for status reporting.
    """
    # Format the call signature exactly as requested: tqs(QueryID,[FundList],StartDate,EndDate)
    call_signature = f"tqs({QueryID}, {FundCodeList}, {StartDate}, {EndDate})"
    current_app.logger.info(
        f"--- SIMULATING TQS API CALL (USE_REAL_TQS_API = False) ---"
    )
    current_app.logger.info(call_signature)
    current_app.logger.info(f"--------------------------------------------------------")
    # Return a simulated row count for the summary table
    simulated_row_count = (
        len(FundCodeList) * 10 if FundCodeList else 0
    )  # Dummy calculation
    return simulated_row_count


def _fetch_real_tqs_data(QueryID, FundCodeList, StartDate, EndDate):
    """Fetches real data from the TQS API.

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
    """
    current_app.logger.info(f"Attempting real TQS API call for QueryID: {QueryID}")
    current_app.logger.info(
        f"--- EXECUTING REAL TQS API CALL (USE_REAL_TQS_API = True) --- "
    )
    current_app.logger.info(f"tqs({QueryID}, {FundCodeList}, {StartDate}, {EndDate})")
    current_app.logger.info(f"--------------------------------------------------------")

    dataframe = None
    try:
        # --- !!! Replace this comment and the line below with the actual API call !!! ---
        # Ensure the `tqs` function/library is imported (commented out at the top)
        # dataframe = tqs.get_data(QueryID, FundCodeList, StartDate, EndDate) # Example real call
        if dataframe is not None:
            current_app.logger.info(f"Data preview: {dataframe.head().to_string()}")
        else:
            current_app.logger.info("No data to display")

        pass  # Remove this pass when uncommenting the line above
        # --- End of section to replace ---

        # Check if the API returned valid data (e.g., a DataFrame)
        if dataframe is not None and isinstance(dataframe, pd.DataFrame):
            current_app.logger.info(
                f"Real TQS API call successful for QueryID: {QueryID}, Rows: {len(dataframe)}"
            )
            return dataframe
        elif dataframe is None:
            # Explicitly handle the case where the API call itself returned None (e.g., planned failure or empty result coded as None)
            current_app.logger.warning(
                f"Real TQS API call for QueryID: {QueryID} returned None."
            )
            return None
        else:
            # Handle cases where the API returned something unexpected (not a DataFrame)
            current_app.logger.warning(
                f"Real TQS API call for QueryID: {QueryID} returned an unexpected data type: {type(dataframe)}."
            )
            return None  # Treat unexpected types as failure

    except NameError as ne:
        # Specific handling if the tqs function isn't defined (import is commented out)
        current_app.logger.error(
            f"Real TQS API call failed for QueryID: {QueryID}. TQS function not imported/defined. Error: {ne}",
            exc_info=True,
        )
        current_app.logger.error(
            f"TQS function not available. Ensure 'from tqs import tqs_query as tqs' is uncommented and the library is installed."
        )
        return None
    except ConnectionError as ce:
        current_app.logger.error(
            f"Connection error during TQS API call for QueryID: {QueryID}: {ce}",
            exc_info=True,
        )
        return None
    except TimeoutError as te:
        current_app.logger.error(
            f"Timeout error during TQS API call for QueryID: {QueryID}: {te}",
            exc_info=True,
        )
        return None
    except PermissionError as pe:
        current_app.logger.error(
            f"Authentication/permission error during TQS API call for QueryID: {QueryID}: {pe}",
            exc_info=True,
        )
        return None
    except Exception as e:
        # Handle API call errors (timeout, connection issues, authentication, etc.)
        current_app.logger.error(
            f"Real TQS API call failed for QueryID: {QueryID}. Error: {e}",
            exc_info=True,
        )
        return None


# --- Helper function to find key columns ---
def _find_key_columns(df, filename):
    """Attempts to find the date and fund/identifier columns."""
    date_col = None
    fund_col = None

    # Date column candidates (add more if needed)
    date_candidates = [
        "Date",
        "date",
        "AsOfDate",
        "ASOFDATE",
        "Effective Date",
        "Trade Date",
        "Position Date",
    ]
    # Fund/ID column candidates
    fund_candidates = [
        "Code",
        "Fund Code",
        "Fundcode",
        "security id",
        "SecurityID",
        "Security Name",
    ]  # Broadened list

    found_cols = df.columns.str.strip().str.lower()

    for candidate in date_candidates:
        if candidate.lower() in found_cols:
            # Find the original casing
            original_cols = [
                col for col in df.columns if col.strip().lower() == candidate.lower()
            ]
            if original_cols:
                date_col = original_cols[0]
                current_app.logger.info(f"[{filename}] Found date column: '{date_col}'")
                break

    for candidate in fund_candidates:
        if candidate.lower() in found_cols:
            # Find the original casing
            original_cols = [
                col for col in df.columns if col.strip().lower() == candidate.lower()
            ]
            if original_cols:
                fund_col = original_cols[0]
                current_app.logger.info(
                    f"[{filename}] Found fund/ID column: '{fund_col}'"
                )
                break

    if not date_col:
        current_app.logger.warning(
            f"[{filename}] Could not reliably identify a date column from candidates: {date_candidates}"
        )
    if not fund_col:
        current_app.logger.warning(
            f"[{filename}] Could not reliably identify a fund/ID column from candidates: {fund_candidates}"
        )

    return date_col, fund_col


# --- Helper Function to Get File Statuses ---
def get_data_file_statuses(data_folder):
    """
    Scans the data folder based on QueryMap.csv and returns status for each file.
    """
    statuses = []
    query_map_path = os.path.join(data_folder, "QueryMap.csv")

    if not os.path.exists(query_map_path):
        current_app.logger.warning(
            f"QueryMap.csv not found at {query_map_path} for status check."
        )
        return statuses  # Return empty list if map is missing

    try:
        query_map_df = pd.read_csv(query_map_path)
        if "FileName" not in query_map_df.columns:
            current_app.logger.warning(
                f"QueryMap.csv at {query_map_path} is missing 'FileName' column."
            )
            return statuses

        date_column_candidates = [
            "Date",
            "date",
            "AsOfDate",
            "ASOFDATE",
            "Effective Date",
            "Trade Date",
            "Position Date",
        ]  # Add more candidates if needed

        for index, row in query_map_df.iterrows():
            filename = row["FileName"]
            file_path = os.path.join(data_folder, filename)
            status_info = {
                "filename": filename,
                "exists": False,
                "last_modified": "N/A",
                "latest_data_date": "N/A",
                "funds_included": "N/A",  # Initialize new key
            }

            if os.path.exists(file_path):
                status_info["exists"] = True
                try:
                    # Get file modification time
                    mod_timestamp = os.path.getmtime(file_path)
                    status_info["last_modified"] = datetime.datetime.fromtimestamp(
                        mod_timestamp
                    ).strftime("%Y-%m-%d %H:%M:%S")

                    # Try to read the CSV and find the latest date
                    try:
                        df = pd.read_csv(
                            file_path, low_memory=False
                        )  # low_memory=False can help with mixed types
                        df_head = df.head()
                        # Determine the actual date column name
                        date_col = None
                        # --- Update Date Column Candidates ---
                        date_column_candidates = [
                            "Date",
                            "date",
                            "AsOfDate",
                            "ASOFDATE",
                            "Effective Date",
                            "Trade Date",
                            "Position Date",
                        ]
                        found_cols = df_head.columns.str.strip()
                        current_app.logger.info(
                            f"[{filename}] Checking for date columns: {date_column_candidates} in columns {found_cols.tolist()}"
                        )
                        for candidate in date_column_candidates:
                            # Case-insensitive check
                            matching_cols = [
                                col
                                for col in found_cols
                                if col.lower() == candidate.lower()
                            ]
                            if matching_cols:
                                date_col = matching_cols[0]  # Use the actual name found
                                current_app.logger.info(
                                    f"[{filename}] Found date column: '{date_col}'"
                                )
                                break  # Found the first match

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
                                        raise ValueError(
                                            f"Date column '{date_col}' found in header but not in full DataFrame columns: {df.columns.tolist()}"
                                        )
                                    date_col = corrected_date_col  # Use the name from the full df

                                date_series = df[
                                    date_col
                                ]  # Use the full series from the complete DataFrame
                                # --------------------------------------------------

                                current_app.logger.info(
                                    f"[{filename}] Attempting to parse full date column '{date_col}' (length: {len(date_series)}). Top 5 values: {date_series.head().to_list()}"
                                )

                                # Try standard YYYY-MM-DD first
                                parsed_dates = pd.to_datetime(
                                    date_series, format="%Y-%m-%d", errors="coerce"
                                )

                                # If all are NaT, try DD/MM/YYYY
                                if parsed_dates.isnull().all():
                                    current_app.logger.info(
                                        f"[{filename}] Format YYYY-MM-DD failed, trying DD/MM/YYYY..."
                                    )
                                    parsed_dates = pd.to_datetime(
                                        date_series, format="%d/%m/%Y", errors="coerce"
                                    )

                                # If still all NaT, try inferring (less reliable but fallback)
                                if parsed_dates.isnull().all():
                                    current_app.logger.warning(
                                        f"[{filename}] Both specific formats failed, trying to infer date format..."
                                    )
                                    parsed_dates = pd.to_datetime(
                                        date_series,
                                        errors="coerce",
                                        infer_datetime_format=True,
                                    )

                                # Check if any dates were successfully parsed
                                if not parsed_dates.isnull().all():
                                    latest_date = parsed_dates.max()
                                    if pd.notna(latest_date):
                                        status_info["latest_data_date"] = (
                                            latest_date.strftime("%Y-%m-%d")
                                        )
                                        current_app.logger.info(
                                            f"[{filename}] Successfully found latest date: {status_info['latest_data_date']}"
                                        )
                                    else:
                                        status_info["latest_data_date"] = (
                                            "No Valid Dates Found"
                                        )
                                        current_app.logger.warning(
                                            f"[{filename}] Parsed dates but found no valid max date (all NaT?)."
                                        )
                                else:
                                    status_info["latest_data_date"] = (
                                        "Date Parsing Failed"
                                    )
                                    current_app.logger.warning(
                                        f"[{filename}] All parsing attempts failed for date column '{date_col}'."
                                    )

                            except Exception as date_err:
                                current_app.logger.error(
                                    f"Error parsing date column '{date_col}' in {file_path}: {date_err}",
                                    exc_info=True,
                                )
                                status_info["latest_data_date"] = (
                                    f"Error Parsing Date ({date_col})"
                                )
                        else:
                            status_info["latest_data_date"] = (
                                "No Date Column Found/Parsed"
                            )
                            current_app.logger.warning(
                                f"[{filename}] Could not find a suitable date column."
                            )

                        # --- Add Fund Code Extraction ---
                        code_col = None
                        # FIX: Search for 'code' OR 'fund code' (case-insensitive)
                        code_candidates = ["code", "fund code"]
                        found_code_col_name = None
                        for candidate in code_candidates:
                            matches = [
                                c for c in df.columns if c.strip().lower() == candidate
                            ]
                            if matches:
                                found_code_col_name = matches[
                                    0
                                ]  # Use the actual column name found
                                break  # Stop searching once found

                        if found_code_col_name:
                            code_col = (
                                found_code_col_name  # Assign the found name to code_col
                            )
                            current_app.logger.info(
                                f"[{filename}] Found Code column: '{code_col}'"
                            )
                            if not df.empty and code_col in df:
                                try:
                                    unique_funds = sorted(
                                        [
                                            str(f)
                                            for f in df[code_col].unique()
                                            if pd.notna(f)
                                        ]
                                    )
                                    if unique_funds:
                                        if len(unique_funds) <= 5:
                                            status_info["funds_included"] = ", ".join(
                                                unique_funds
                                            )
                                        else:
                                            status_info["funds_included"] = (
                                                ", ".join(unique_funds[:5])
                                                + f" ... ({len(unique_funds)} total)"
                                            )
                                        current_app.logger.info(
                                            f"[{filename}] Found funds: {status_info['funds_included']}"
                                        )
                                    else:
                                        status_info["funds_included"] = "No Codes Found"
                                except Exception as fund_err:
                                    current_app.logger.error(
                                        f"[{filename}] Error extracting funds from column '{code_col}': {fund_err}"
                                    )
                                    status_info["funds_included"] = (
                                        "Error Extracting Funds"
                                    )
                            else:
                                status_info["funds_included"] = (
                                    "Code Column Empty?"  # Should be covered by EmptyDataError usually
                                )
                        else:
                            status_info["funds_included"] = "Code Column Missing"
                            current_app.logger.warning(
                                f"[{filename}] Code column ('Code' or 'Fund Code') not found."
                            )
                        # --- End Fund Code Extraction ---

                    except pd.errors.EmptyDataError:
                        status_info["latest_data_date"] = "File is Empty"
                        status_info["funds_included"] = (
                            "File is Empty"  # Also set for funds
                        )
                        current_app.logger.warning(f"CSV file is empty: {file_path}")
                    except Exception as read_err:
                        status_info["latest_data_date"] = "Read Error"
                        current_app.logger.error(
                            f"Error reading CSV {file_path} for status check: {read_err}",
                            exc_info=True,
                        )

                except Exception as file_err:
                    current_app.logger.error(
                        f"Error accessing file properties for {file_path}: {file_err}",
                        exc_info=True,
                    )
                    status_info["last_modified"] = "Error Accessing File"

            statuses.append(status_info)

    except Exception as e:
        current_app.logger.error(
            f"Failed to process QueryMap.csv for file statuses: {e}", exc_info=True
        )
        # Optionally return a status indicating the map couldn't be processed
        return [
            {
                "filename": "QueryMap Error",
                "exists": False,
                "last_modified": str(e),
                "latest_data_date": "",
                "funds_included": "",
            }
        ]

    return statuses


# --- End Helper Function ---
