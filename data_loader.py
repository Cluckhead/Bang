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

# --- Logging Setup ---
LOG_FILENAME = 'data_processing_errors.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Get the logger for the current module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Set minimum level for the logger

# Prevent adding handlers multiple times
if not logger.handlers:
    # Console Handler (INFO and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter(LOG_FORMAT)
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    # File Handler (WARNING and above)
    try:
        # Attempt to create log file in the parent directory (project root)
        log_filepath = os.path.join(os.path.dirname(__file__), '..', LOG_FILENAME)
        fh = logging.FileHandler(log_filepath, mode='a') # Append mode
        fh.setLevel(logging.WARNING)
        fh_formatter = logging.Formatter(LOG_FORMAT)
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)
    except Exception as e:
        logger.error(f"Failed to configure file logging to {log_filepath}: {e}")
# --- End Logging Setup ---


# Define constants
DATA_FOLDER = 'Data'
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
    data_folder: str = DATA_FOLDER
) -> LoadResult:
    """Loads and processes a primary CSV file and optionally a secondary CSV file.

    Uses the internal _process_single_file helper for processing each file.

    Args:
        primary_filename (str): The name of the primary CSV file.
        secondary_filename (Optional[str]): The name of the secondary CSV file. Defaults to None.
        data_folder (str): The path to the folder containing the data files. Defaults to DATA_FOLDER.

    Returns:
        LoadResult: A tuple containing the processed DataFrames and metadata for
                    primary and (optionally) secondary files. Elements corresponding
                    to a file will be None if the file doesn't exist or processing fails.
    """
    primary_filepath = os.path.join(data_folder, primary_filename)
    logger.info(f"--- Starting data load for primary: {primary_filename} ---")
    primary_result = _process_single_file(primary_filepath, primary_filename)

    primary_df = None
    primary_original_val_cols = None
    primary_benchmark_col = None
    if primary_result:
        primary_df, primary_original_val_cols, primary_benchmark_col = primary_result
        logger.info(f"Primary file '{primary_filename}' loaded. Shape: {primary_df.shape if primary_df is not None else 'None'}")
    else:
        logger.error(f"Failed to process primary file: {primary_filename}")
        # Still return structure, but with Nones for primary
        primary_df = _create_empty_dataframe([], False) # Provide minimal empty DF
        primary_original_val_cols = []
        primary_benchmark_col = None


    secondary_df = None
    secondary_original_val_cols = None
    secondary_benchmark_col = None

    if secondary_filename:
        secondary_filepath = os.path.join(data_folder, secondary_filename)
        logger.info(f"--- Checking for secondary file: {secondary_filename} ---")
        if os.path.exists(secondary_filepath):
            logger.info(f"Secondary file found. Processing: {secondary_filename}")
            secondary_result = _process_single_file(secondary_filepath, secondary_filename)
            if secondary_result:
                secondary_df, secondary_original_val_cols, secondary_benchmark_col = secondary_result
                logger.info(f"Secondary file '{secondary_filename}' loaded. Shape: {secondary_df.shape if secondary_df is not None else 'None'}")
            else:
                 logger.warning(f"Failed to process secondary file: {secondary_filename}. Proceeding without it.")
                 # Keep secondary parts as None if processing fails
        else:
            logger.info(f"Secondary file not found: {secondary_filename}. Proceeding with primary only.")
    else:
        logger.info("No secondary filename provided.")

    return (
        primary_df, primary_original_val_cols, primary_benchmark_col,
        secondary_df, secondary_original_val_cols, secondary_benchmark_col
    )

# Example Usage (optional, for testing)
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
#     logger.info("Running data_loader directly for testing...")
#
#     # Test case 1: Primary file only (exists)
#     print("\n--- Test Case 1: Primary Only (ts_Duration.csv) ---")
#     try:
#         pri_df, pri_ovc, pri_bc, sec_df, sec_ovc, sec_bc = load_and_process_data('ts_Duration.csv')
#         if pri_df is not None:
#             print(f"Primary loaded successfully. Shape: {pri_df.shape}")
#             print(f"Primary Orig Val Cols: {pri_ovc}")
#             print(f"Primary Bench Col: {pri_bc}")
#             print(pri_df.head())
#         else:
#             print("Primary loading failed.")
#         print(f"Secondary DF is None: {sec_df is None}")
#
#     except Exception as e:
#         print(f"Error in Test Case 1: {e}")
#
#     # Test case 2: Primary and Secondary (both exist)
#     print("\n--- Test Case 2: Primary (ts_Duration.csv) and Secondary (sp_ts_Duration.csv) ---")
#     # Ensure you have a 'sp_ts_Duration.csv' file in 'Data/' for this test
#     secondary_test_file = 'sp_ts_Duration.csv'
#     if not os.path.exists(os.path.join(DATA_FOLDER, secondary_test_file)):
#         print(f"WARNING: Secondary test file '{secondary_test_file}' not found. Skipping Test Case 2.")
#     else:
#         try:
#             pri_df, pri_ovc, pri_bc, sec_df, sec_ovc, sec_bc = load_and_process_data('ts_Duration.csv', secondary_filename=secondary_test_file)
#             if pri_df is not None:
#                 print(f"Primary loaded successfully. Shape: {pri_df.shape}")
#                 print(f"Primary Orig Val Cols: {pri_ovc}")
#                 print(f"Primary Bench Col: {pri_bc}")
#             else:
#                 print("Primary loading failed.")
#
#             if sec_df is not None:
#                 print(f"Secondary loaded successfully. Shape: {sec_df.shape}")
#                 print(f"Secondary Orig Val Cols: {sec_ovc}")
#                 print(f"Secondary Bench Col: {sec_bc}")
#                 print(sec_df.head())
#             else:
#                 print("Secondary loading failed or file not found.")
#
#         except Exception as e:
#             print(f"Error in Test Case 2: {e}")
#
#     # Test case 3: Primary exists, Secondary does not
#     print("\n--- Test Case 3: Primary (ts_Duration.csv) and Secondary (non_existent.csv) ---")
#     try:
#         pri_df, pri_ovc, pri_bc, sec_df, sec_ovc, sec_bc = load_and_process_data('ts_Duration.csv', secondary_filename='non_existent.csv')
#         if pri_df is not None:
#             print(f"Primary loaded successfully. Shape: {pri_df.shape}")
#         else:
#             print("Primary loading failed.")
#         print(f"Secondary DF is None: {sec_df is None}")
#         print(f"Secondary Orig Val Cols is None: {sec_ovc is None}")
#         print(f"Secondary Bench Col is None: {sec_bc is None}")
#
#     except Exception as e:
#         print(f"Error in Test Case 3: {e}")
#
#     # Test case 4: Primary does not exist
#     print("\n--- Test Case 4: Primary (bad_file.csv) ---")
#     try:
#         pri_df, pri_ovc, pri_bc, sec_df, sec_ovc, sec_bc = load_and_process_data('bad_file.csv')
#         print(f"Primary DF is not None: {pri_df is not None}") # Should be True, but df will be empty
#         print(f"Primary DF shape: {pri_df.shape if pri_df is not None else 'None'}")
#         print(f"Primary Orig Val Cols: {pri_ovc}")
#         print(f"Primary Bench Col: {pri_bc}")
#         print(f"Secondary DF is None: {sec_df is None}")
#
#     except Exception as e:
#         print(f"Error in Test Case 4: {e}") 