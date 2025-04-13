# This file is responsible for loading and preprocessing data from CSV files.
# It includes functions to dynamically identify essential columns (Date, Code, Benchmark)
# based on patterns, handle potential naming variations, parse dates, standardize column names,
# set appropriate data types, and prepare the data in a pandas DataFrame format
# suitable for further analysis and processing within the application.
# It also supports loading a secondary file (e.g., prefixed with 'sp_') for comparison.
# data_loader.py
# This file is responsible for loading and preprocessing data from time-series CSV files (typically prefixed with `ts_`).
# It includes functions to dynamically identify essential columns (Date, Code, Benchmark)
# based on patterns, handle potential naming variations, parse dates (handling 'YYYY-MM-DD' and 'DD/MM/YYYY'),
# standardize column names, set appropriate data types, and prepare the data in a pandas DataFrame format
# suitable for further analysis within the application. It includes robust error handling and logging.
# It now also supports loading and processing a secondary comparison file (e.g., sp_*.csv).

import pandas as pd
import os
import logging
from typing import List, Tuple, Optional
import re # Import regex for pattern matching
from flask import current_app # Import current_app to access config

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

# --- Removed logging setup block --- 
# Logging is now handled centrally by the Flask app factory in app.py


# Define constants
# Removed DATA_FOLDER constant - path is now dynamically determined

# Standard internal column names after renaming
STD_DATE_COL = 'Date'
STD_CODE_COL = 'Code'
STD_BENCHMARK_COL = 'Benchmark'

def _find_column(pattern: str, columns: List[str], filename_for_logging: str, col_type: str) -> str:
    """Helper function to find a single column matching a pattern (case-insensitive)."""
    matches = [col for col in columns if re.search(pattern, col, re.IGNORECASE)]
    if len(matches) == 1:
        logger.info(f"Found {col_type} column in '{filename_for_logging}': '{matches[0]}'")
        return matches[0]
    elif len(matches) > 1:
        # Log error before raising
        logger.error(f"Multiple possible {col_type} columns found in '{filename_for_logging}' matching pattern '{pattern}': {matches}. Please ensure unique column names.")
        raise ValueError(f"Multiple possible {col_type} columns found in '{filename_for_logging}' matching pattern '{pattern}': {matches}. Please ensure unique column names.")
    else:
         # Log error before raising
        logger.error(f"No {col_type} column found in '{filename_for_logging}' matching pattern '{pattern}'. Found columns: {columns}")
        raise ValueError(f"No {col_type} column found in '{filename_for_logging}' matching pattern '{pattern}'. Found columns: {columns}")

def _create_empty_dataframe(original_fund_val_col_names: List[str], benchmark_col_present: bool) -> pd.DataFrame:
    """Creates an empty DataFrame with the expected structure."""
    final_benchmark_col_name = STD_BENCHMARK_COL if benchmark_col_present else None
    expected_cols = [STD_DATE_COL, STD_CODE_COL] + original_fund_val_col_names
    if final_benchmark_col_name:
        expected_cols.append(final_benchmark_col_name)
    # Create an empty df with the right index and columns
    empty_index = pd.MultiIndex(levels=[[], []], codes=[[], []], names=[STD_DATE_COL, STD_CODE_COL])
    value_cols = [col for col in expected_cols if col not in [STD_DATE_COL, STD_CODE_COL]]
    return pd.DataFrame(index=empty_index, columns=value_cols)

def _process_single_file(
    filepath: str,
    filename_for_logging: str
) -> Optional[Tuple[pd.DataFrame, List[str], Optional[str]]]:
    """Internal helper to load and process a single CSV file.

    Handles finding columns, parsing dates, renaming, indexing, and type conversion.
    Returns None if the file is not found or critical processing steps fail.

    Returns:
        Optional[Tuple[pd.DataFrame, List[str], Optional[str]]]:
               Processed DataFrame, list of original fund value column names,
               and the standardized benchmark column name if present, otherwise None.
               Returns None if processing fails critically.
    """
    if not os.path.exists(filepath):
        logger.warning(f"File not found, skipping: {filepath}")
        return None # Return None if file doesn't exist

    try:
        # Read only the header first
        header_df = pd.read_csv(filepath, nrows=0, encoding='utf-8', encoding_errors='replace', on_bad_lines='skip')
        original_cols = [col.strip() for col in header_df.columns.tolist()]
        logger.info(f"Processing file: '{filename_for_logging}'. Original columns: {original_cols}")

        # Dynamically find required columns
        date_pattern = r'\b(Position\s*)?Date\b'
        actual_date_col = _find_column(date_pattern, original_cols, filename_for_logging, 'Date')
        code_pattern = r'\b(Fund\s*)?Code\b' # Allow 'Fund Code' or 'Code'
        actual_code_col = _find_column(code_pattern, original_cols, filename_for_logging, 'Code')

        benchmark_col_present = False
        actual_benchmark_col = None
        try:
            benchmark_pattern = r'\b(Benchmark|Bench)\b' # Allow 'Benchmark' or 'Bench'
            actual_benchmark_col = _find_column(benchmark_pattern, original_cols, filename_for_logging, 'Benchmark')
            benchmark_col_present = True
        except ValueError:
            logger.info(f"No Benchmark column found in '{filename_for_logging}' matching pattern. Proceeding without benchmark.")

        # Identify original fund value columns
        excluded_cols_for_funds = {actual_date_col, actual_code_col}
        if benchmark_col_present and actual_benchmark_col:
            excluded_cols_for_funds.add(actual_benchmark_col)
        original_fund_val_col_names = [col for col in original_cols if col not in excluded_cols_for_funds]

        if not original_fund_val_col_names and not benchmark_col_present:
             logger.error(f"No fund value columns and no benchmark column identified in '{filename_for_logging}'. Cannot process.")
             return None # Cannot proceed

        # Read the full CSV
        df = pd.read_csv(filepath, encoding='utf-8', encoding_errors='replace', on_bad_lines='skip', dtype={actual_date_col: str})
        df.columns = df.columns.str.strip()

        # Rename columns
        rename_map = {
            actual_date_col: STD_DATE_COL,
            actual_code_col: STD_CODE_COL
        }
        if benchmark_col_present and actual_benchmark_col:
            rename_map[actual_benchmark_col] = STD_BENCHMARK_COL
        df.rename(columns=rename_map, inplace=True)
        logger.info(f"Renamed columns in '{filename_for_logging}': {list(rename_map.keys())} -> {list(rename_map.values())}")

        # Robust Date Parsing
        date_series = df[STD_DATE_COL]
        parsed_dates = pd.to_datetime(date_series, errors='coerce', dayfirst=None, yearfirst=None) # Let pandas infer

        # Check if all parsing failed
        if parsed_dates.isnull().all() and len(date_series) > 0:
             # Try again with dayfirst=True if initial inference failed
            logger.warning(f"Initial date parsing failed for {filename_for_logging}. Trying with dayfirst=True.")
            parsed_dates = pd.to_datetime(date_series, errors='coerce', dayfirst=True)
            if parsed_dates.isnull().all() and len(date_series) > 0:
                logger.error(f"Could not parse any dates in column '{STD_DATE_COL}' (original: '{actual_date_col}') in file {filename_for_logging} even with dayfirst=True.")
                return None # Cannot proceed without valid dates

        nat_count = parsed_dates.isnull().sum()
        total_count = len(parsed_dates)
        success_count = total_count - nat_count
        logger.info(f"Parsed {success_count}/{total_count} dates in {filename_for_logging}. ({nat_count} resulted in NaT).")
        if nat_count > 0:
             logger.warning(f"{nat_count} date values in '{STD_DATE_COL}' from {filename_for_logging} became NaT.")

        df[STD_DATE_COL] = parsed_dates
        original_row_count = len(df)
        df.dropna(subset=[STD_DATE_COL], inplace=True)
        rows_dropped = original_row_count - len(df)
        if rows_dropped > 0:
            logger.warning(f"Dropped {rows_dropped} rows from {filename_for_logging} due to failed date parsing.")

        # Set Index
        if df.empty:
            logger.warning(f"DataFrame became empty after dropping rows with unparseable dates in {filename_for_logging}.")
            # Return empty structure but indicate success in file processing up to this point
            empty_df = _create_empty_dataframe(original_fund_val_col_names, benchmark_col_present)
            final_bm_col = STD_BENCHMARK_COL if benchmark_col_present else None
            return empty_df, original_fund_val_col_names, final_bm_col

        df.set_index([STD_DATE_COL, STD_CODE_COL], inplace=True)

        # Convert value columns to numeric
        value_cols_to_convert = original_fund_val_col_names[:]
        if benchmark_col_present:
            value_cols_to_convert.append(STD_BENCHMARK_COL)

        valid_cols_for_conversion = [col for col in value_cols_to_convert if col in df.columns]
        if not valid_cols_for_conversion:
             logger.error(f"No valid fund or benchmark value columns found to convert in {filename_for_logging} after processing.")
             # Return partially processed DF but log error
             final_bm_col = STD_BENCHMARK_COL if benchmark_col_present else None
             return df, original_fund_val_col_names, final_bm_col # Return what we have

        df[valid_cols_for_conversion] = df[valid_cols_for_conversion].apply(pd.to_numeric, errors='coerce')
        nan_check_cols = [col for col in valid_cols_for_conversion if col in df.columns]
        if nan_check_cols and df[nan_check_cols].isnull().all().all():
            logger.warning(f"All values in value columns {nan_check_cols} became NaN after conversion in file {filename_for_logging}. Check data types.")


        final_benchmark_col_name = STD_BENCHMARK_COL if benchmark_col_present else None
        logger.info(f"Successfully processed file: '{filename_for_logging}'. Index: {df.index.names}. Columns: {df.columns.tolist()}")
        return df, original_fund_val_col_names, final_benchmark_col_name

    except FileNotFoundError:
        logger.error(f"File not found during processing: {filepath}")
        return None # Handled above, but belt-and-suspenders
    except ValueError as e:
        logger.error(f"Value error processing {filename_for_logging}: {e}")
        return None # Return None on critical errors like missing columns
    except Exception as e:
        logger.exception(f"Unexpected error processing {filename_for_logging}: {e}") # Log full traceback
        return None # Return None on unexpected errors

# Simplified return type: focus on the dataframes and metadata needed downstream
LoadResult = Tuple[
    Optional[pd.DataFrame],      # Primary DataFrame
    Optional[List[str]],         # Primary original value columns
    Optional[str],               # Primary benchmark column name (standardized)
    Optional[pd.DataFrame],      # Secondary DataFrame
    Optional[List[str]],         # Secondary original value columns
    Optional[str]                # Secondary benchmark column name (standardized)
]

def load_and_process_data(
    primary_filename: str,
    secondary_filename: Optional[str] = None,
    data_folder_path: Optional[str] = None # Renamed and made optional
) -> LoadResult:
    """Loads and processes a primary CSV file and optionally a secondary CSV file.

    Retrieves the data folder path from Flask's current_app.config['DATA_FOLDER']
    if data_folder_path is not provided. Assumes execution within a Flask request context
    when data_folder_path is None.

    Uses the internal _process_single_file helper for processing each file.

    Args:
        primary_filename (str): The name of the primary CSV file.
        secondary_filename (Optional[str]): The name of the secondary CSV file. Defaults to None.
        data_folder_path (Optional[str]): Explicit path to the folder containing the data files.
                                           If None, path is retrieved from current_app.config.

    Returns:
        LoadResult: A tuple containing the processed DataFrames and metadata for
                    primary and (optionally) secondary files. Elements corresponding
                    to a file will be None if the file doesn't exist or processing fails,
                    or if the data folder path cannot be determined.
    """
    data_folder: Optional[str] = None

    if data_folder_path is None:
        try:
            # Retrieve the absolute path configured during app initialization
            data_folder = current_app.config['DATA_FOLDER']
            logger.info(f"Using data folder from current_app.config: {data_folder}")
            if not data_folder:
                 logger.error("DATA_FOLDER in current_app.config is not set or empty.")
                 return None, None, None, None, None, None
        except RuntimeError:
            logger.error("Cannot access current_app.config. load_and_process_data must be called within a Flask request context or be provided with an explicit data_folder_path.")
            # Return None for all parts of the tuple if path cannot be determined
            return None, None, None, None, None, None
        except KeyError:
            logger.error("'DATA_FOLDER' key not found in current_app.config. Ensure it is set during app initialization.")
            return None, None, None, None, None, None
    else:
        # Use the explicitly provided path
        data_folder = data_folder_path
        logger.info(f"Using explicitly provided data_folder_path: {data_folder}")

    # Ensure data_folder is not None before proceeding (should be handled above, but belt-and-suspenders)
    if data_folder is None:
         logger.critical("Data folder path could not be determined. Aborting load.")
         return None, None, None, None, None, None

    # --- Process Primary File --- 
    primary_filepath = os.path.join(data_folder, primary_filename)
    logger.info(f"--- Starting data load for primary: {primary_filename} from {primary_filepath} ---")
    primary_result = _process_single_file(primary_filepath, primary_filename)

    df1, cols1, bench1 = (None, None, None)
    if primary_result:
        df1, cols1, bench1 = primary_result
        logger.info(f"Primary file '{primary_filename}' processed. Shape: {df1.shape if df1 is not None else 'N/A'}. Benchmark: {bench1}")
    else:
        logger.warning(f"Processing failed for primary file: {primary_filename}")

    # --- Process Secondary File (if provided) --- 
    df2, cols2, bench2 = (None, None, None)
    if secondary_filename:
        secondary_filepath = os.path.join(data_folder, secondary_filename)
        logger.info(f"--- Starting data load for secondary: {secondary_filename} from {secondary_filepath} ---")
        secondary_result = _process_single_file(secondary_filepath, secondary_filename)
        if secondary_result:
            df2, cols2, bench2 = secondary_result
            logger.info(f"Secondary file '{secondary_filename}' processed. Shape: {df2.shape if df2 is not None else 'N/A'}. Benchmark: {bench2}")
        else:
            logger.warning(f"Processing failed for secondary file: {secondary_filename}")

    return df1, cols1, bench1, df2, cols2, bench2

# --- Standalone Execution / Testing --- 
# Note: If run directly, this block cannot use current_app.config.
# It needs to determine the data folder path independently, potentially using get_data_folder_path from utils.

# Example (requires config.py and utils.py to be importable):
# if __name__ == '__main__':
#     try:
#         from utils import get_data_folder_path
#         # Determine the root path assuming data_loader.py is one level down from the project root
#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         project_root = os.path.dirname(script_dir)
#         # Use the utility function to get the configured path
#         standalone_data_path = get_data_folder_path(app_root_path=project_root)
#         print(f"[Standalone] Determined data path: {standalone_data_path}")
#
#         # Example usage:
#         primary_file = 'ts_NAV_Report_Short.csv' # Replace with your actual test file
#         # secondary_file = 'sp_NAV_Report_Short.csv' # Optional secondary file
#         df1, cols1, bench1, df2, cols2, bench2 = load_and_process_data(
#             primary_filename=primary_file,
#             # secondary_filename=secondary_file,
#             data_folder_path=standalone_data_path # Pass the determined path explicitly
#         )
#
#         if df1 is not None:
#             print(f"\n--- Primary Data ({primary_file}) ---")
#             print(df1.head())
#             print(f"Original Value Columns: {cols1}")
#             print(f"Benchmark Column: {bench1}")
#         else:
#             print(f"\nFailed to load primary data ({primary_file}). Check logs.")
#
#         # if secondary_file and df2 is not None:
#         #     print(f"\n--- Secondary Data ({secondary_file}) ---")
#         #     print(df2.head())
#         #     print(f"Original Value Columns: {cols2}")
#         #     print(f"Benchmark Column: {bench2}")
#         # elif secondary_file:
#         #      print(f"\nFailed to load secondary data ({secondary_file}). Check logs.")
#
#     except ImportError:
#         print("Error: Could not import utils.get_data_folder_path. Ensure utils.py and config.py exist and are accessible.")
#     except Exception as e:
#         print(f"An error occurred during standalone execution: {e}") 