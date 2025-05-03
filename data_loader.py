# This file is responsible for loading and preprocessing data from CSV files.
# It includes functions to dynamically identify essential columns (Date, Code, Benchmark, 'SS Project - In Scope')
# based on patterns, handle potential naming variations, parse dates, standardize column names,
# set appropriate data types, and prepare the data in a pandas DataFrame format
# suitable for further analysis and processing within the application.
# It also supports loading a secondary file (e.g., prefixed with 'sp_') for comparison,
# and filtering data based on the 'SS Project - In Scope' column.
#
# Refactored: _process_single_file is now split into smaller helpers for clarity and maintainability.

# Purpose: Loads and preprocesses time-series and security-level data from CSV files for the Simple Data Checker application.
# Handles dynamic column identification, robust date parsing, numeric conversion, and optional filtering/aggregation for downstream analysis.
# Uses data_utils for robust I/O, parsing, and transformation. Logging is handled centrally by the Flask app.

import pandas as pd
import os
import logging
from typing import List, Tuple, Optional, Dict, Any
import re  # Import regex for pattern matching
from flask import current_app  # Import current_app to access config
import config
from data_utils import (
    read_csv_robustly,
    parse_dates_robustly,
    identify_columns,
    convert_to_numeric_robustly,
)
from utils import load_yaml_config

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

# --- Removed logging setup block ---
# Logging is now handled centrally by the Flask app factory in app.py


# Define constants
# Removed DATA_FOLDER constant - path is now dynamically determined

# Standard internal column names after renaming
STD_DATE_COL = "Date"
STD_CODE_COL = "Code"
STD_BENCHMARK_COL = "Benchmark"
STD_SCOPE_COL = "SS Project - In Scope"  # Standardized name for the scope column

# Load date patterns from YAML once at module level
_date_patterns_yaml = load_yaml_config(
    os.path.join(os.path.dirname(__file__), "config", "date_patterns.yaml")
)
DATE_COLUMN_PATTERNS = _date_patterns_yaml.get("date_patterns", [])


# --- NEW HELPER FUNCTION ---
def load_simple_csv(filepath: str, filename_for_logging: str) -> Optional[pd.DataFrame]:
    """Loads a CSV file into a DataFrame with basic error handling.

    Args:
        filepath (str): The full path to the CSV file.
        filename_for_logging (str): The filename used for logging messages.

    Returns:
        Optional[pd.DataFrame]: DataFrame if loaded successfully, else None.
    """
    if not os.path.exists(filepath):
        logger.warning(f"File not found, skipping: {filepath}")
        return None
    df = read_csv_robustly(
        filepath, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip"
    )
    if df is None:
        logger.error(
            f"Error reading simple CSV '{filename_for_logging}': see previous log for details."
        )
        return None
    if df.empty:
        logger.warning(f"File is empty: {filepath}")
        return pd.DataFrame()  # Return empty DataFrame for consistency
    df.columns = df.columns.str.strip()  # Clean column names
    logger.info(
        f"Successfully loaded simple CSV: '{filename_for_logging}' ({len(df)} rows)"
    )
    return df


# --- END NEW HELPER FUNCTION ---


def _find_column(
    pattern: str, columns: List[str], filename_for_logging: str, col_type: str
) -> str:
    """Helper function to find a single column matching a pattern (case-insensitive)."""
    matches = [col for col in columns if re.search(pattern, col, re.IGNORECASE)]
    if len(matches) == 1:
        logger.info(
            f"Found {col_type} column in '{filename_for_logging}': '{matches[0]}'"
        )
        return matches[0]
    elif len(matches) > 1:
        # Log error before raising
        logger.error(
            f"Multiple possible {col_type} columns found in '{filename_for_logging}' matching pattern '{pattern}': {matches}. Please ensure unique column names."
        )
        raise ValueError(
            f"Multiple possible {col_type} columns found in '{filename_for_logging}' matching pattern '{pattern}': {matches}. Please ensure unique column names."
        )
    else:
        # Log error before raising
        logger.error(
            f"No {col_type} column found in '{filename_for_logging}' matching pattern '{pattern}'. Found columns: {columns}"
        )
        raise ValueError(
            f"No {col_type} column found in '{filename_for_logging}' matching pattern '{pattern}'. Found columns: {columns}"
        )


def _create_empty_dataframe(
    original_fund_val_col_names: List[str], benchmark_col_present: bool
) -> pd.DataFrame:
    """Creates an empty DataFrame with the expected structure."""
    final_benchmark_col_name = STD_BENCHMARK_COL if benchmark_col_present else None
    expected_cols = [STD_DATE_COL, STD_CODE_COL] + original_fund_val_col_names
    if final_benchmark_col_name:
        expected_cols.append(final_benchmark_col_name)
    # Create an empty df with the right index and columns
    empty_index = pd.MultiIndex(
        levels=[[], []], codes=[[], []], names=[STD_DATE_COL, STD_CODE_COL]
    )
    value_cols = [
        col for col in expected_cols if col not in [STD_DATE_COL, STD_CODE_COL]
    ]
    return pd.DataFrame(index=empty_index, columns=value_cols)


def _find_columns_for_file(
    original_cols: List[str], filename_for_logging: str
) -> Tuple[str, str, bool, Optional[str], List[str], Optional[str]]:
    """
    Identifies the actual date, code, (optionally) benchmark columns, fund value columns, and scope column.
    Returns:
        actual_date_col, actual_code_col, benchmark_col_present, actual_benchmark_col, original_fund_val_col_names, actual_scope_col
    """
    # Use patterns from config for date, code, benchmark, and scope columns
    patterns = {
        "date": DATE_COLUMN_PATTERNS,
        "code": config.CODE_COLUMN_PATTERNS,
        "benchmark": config.BENCHMARK_COLUMN_PATTERNS,
        "scope": config.SCOPE_COLUMN_PATTERNS,
    }
    required = ["date", "code"]
    found = identify_columns(original_cols, patterns, required)
    actual_date_col = found["date"]
    actual_code_col = found["code"]
    actual_benchmark_col = found.get("benchmark")
    actual_scope_col = found.get("scope")
    benchmark_col_present = actual_benchmark_col is not None
    # Exclude date, code, benchmark, and scope columns when identifying value columns
    excluded_cols_for_funds = {actual_date_col, actual_code_col}
    if benchmark_col_present and actual_benchmark_col:
        excluded_cols_for_funds.add(actual_benchmark_col)
    if actual_scope_col:
        excluded_cols_for_funds.add(actual_scope_col)
    original_fund_val_col_names = [
        col for col in original_cols if col not in excluded_cols_for_funds
    ]
    if not original_fund_val_col_names and not benchmark_col_present:
        logger.warning(
            f"No fund value columns identified in '{filename_for_logging}' after excluding standard columns."
        )
    return (
        actual_date_col,
        actual_code_col,
        benchmark_col_present,
        actual_benchmark_col,
        original_fund_val_col_names,
        actual_scope_col,
    )


def _parse_date_column(
    df: pd.DataFrame, date_col: str, filename_for_logging: str
) -> pd.Series:
    """
    Parses the date column robustly using data_utils.parse_dates_robustly.
    Returns the parsed date series.
    """
    date_series = df[date_col]
    parsed_dates = parse_dates_robustly(date_series)
    nat_count = parsed_dates.isnull().sum()
    total_count = len(parsed_dates)
    success_count = total_count - nat_count
    logger.info(
        f"Parsed {success_count}/{total_count} dates in {filename_for_logging}. ({nat_count} resulted in NaT)."
    )
    if nat_count > 0:
        logger.warning(
            f"{nat_count} date values in '{date_col}' from {filename_for_logging} became NaT."
        )
    return parsed_dates


def _convert_value_columns(df: pd.DataFrame, value_cols: list) -> list:
    """
    Converts specified columns in the DataFrame to numeric using convert_to_numeric_robustly.
    Returns the list of columns that were successfully converted.
    """
    converted_cols = []
    for col in value_cols:
        if col in df.columns:
            df[col] = convert_to_numeric_robustly(df[col])
            converted_cols.append(col)
    return converted_cols


def _aggregate_by_date_code(
    df: pd.DataFrame,
    date_col: str,
    code_col: str,
    filename_for_logging: str,
    numeric_hint_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Aggregate duplicate (date, code) rows.

    Numeric columns are averaged; non-numeric columns keep the first value.
    If no numeric dtypes are detected, *numeric_hint_cols* are coerced to
    numeric (best-effort) before aggregation.
    """
    before = len(df)

    group_cols = [date_col, code_col]

    # Identify numeric columns – coerce hints if necessary
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols and numeric_hint_cols:
        for col in numeric_hint_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # Build aggregation dictionary
    agg_dict: Dict[str, str] = {col: "mean" for col in numeric_cols}
    for col in df.columns:
        if col not in group_cols and col not in numeric_cols:
            agg_dict[col] = "first"

    df_agg = df.groupby(group_cols, as_index=False).agg(agg_dict)
    after = len(df_agg)
    if before != after:
        logger.info(
            f"Aggregated {before} rows to {after} unique (Date, Code) pairs in '{filename_for_logging}'."
        )
    return df_agg


def _filter_by_scope(
    df: pd.DataFrame,
    scope_col: str,
    filename_for_logging: str,
) -> pd.DataFrame:
    """Return only rows where *scope_col* equals 'TRUE' (case-insensitive)."""
    original_count = len(df)
    if scope_col not in df.columns:
        logger.warning(
            f"Scope column '{scope_col}' not found in '{filename_for_logging}'. Skipping scope filter."
        )
        return df

    df_filtered = df.copy()
    df_filtered[scope_col] = (
        df_filtered[scope_col].astype(str).str.upper().fillna("FALSE")
    )
    df_filtered = df_filtered[df_filtered[scope_col] == "TRUE"]
    logger.info(
        f"Filtered '{filename_for_logging}' based on '{scope_col}'. Kept {len(df_filtered)}/{original_count} rows where value is 'TRUE'."
    )
    return df_filtered


def _process_single_file(
    filepath: str,
    filename_for_logging: str,
    filter_sp_valid: bool = False,  # Add parameter with default False
) -> Optional[Tuple[pd.DataFrame, List[str], Optional[str]]]:
    """
    Internal helper to load and process a single CSV file.

    The function orchestrates several distinct logical steps to transform raw CSV
    input into a clean, analysis-ready DataFrame.  The high-level workflow is:

    1. **Read header only** – obtain original column names without loading full data.
    2. **Identify key columns** – locate date, code, benchmark, scope, and value
       columns via `_find_columns_for_file` (uses regex patterns from config).
    3. **Read full data** – load only the required columns using
       `data_utils.read_csv_robustly`, applying preliminary dtype hints.
    4. **(Optional) Aggregate rows** – when *not* filtering on *S&P Valid* scope,
       aggregate duplicate (Date, Code) pairs to a single row (mean of numeric
       columns, first of non-numeric).
    5. **(Optional) Filter by scope** – when `filter_sp_valid` is *True*, keep
       only rows where the scope column equals "TRUE" (case-insensitive).
    6. **Rename standard columns** – map the identified columns to the internal
       standard names (`Date`, `Code`, `Benchmark`).
    7. **Drop helper columns** – remove the now-unused scope column (if any).
    8. **Parse dates** – convert the `Date` column using
       `data_utils.parse_dates_robustly`, then drop rows where parsing failed.
    9. **Set multi-index** – set `(Date, Code)` as a MultiIndex for efficient
       downstream operations.
    10. **Convert value columns to numeric** – apply
        `data_utils.convert_to_numeric_robustly` and drop rows with NaNs.

    If at any stage a critical error is encountered, the function logs the issue
    and returns `None`, ensuring the caller can handle partial failures
    gracefully.

    Returns:
        Optional[Tuple[pd.DataFrame, List[str], Optional[str]]]:
            • Processed DataFrame (or an empty one with correct structure)
            • List of original fund value column names
            • Standardised benchmark column name (if present) or `None`.
    """
    if not os.path.exists(filepath):
        logger.warning(f"File not found, skipping: {filepath}")
        return None
    try:
        # --- Step 1: Read header (discover original columns) -------------------
        header_df = read_csv_robustly(
            filepath,
            nrows=0,
            encoding="utf-8",
            encoding_errors="replace",
            on_bad_lines="skip",
        )
        if header_df is None:
            logger.warning(f"Header could not be read for {filepath}")
            return None
        original_cols = [col.strip() for col in header_df.columns.tolist()]
        logger.info(
            f"Processing file: '{filename_for_logging}'. Original columns: {original_cols}"
        )

        # --- Step 2: Identify key columns (date, code, benchmark, scope, values) ---
        (
            actual_date_col,
            actual_code_col,
            benchmark_col_present,
            actual_benchmark_col,
            original_fund_val_col_names,
            actual_scope_col,
        ) = _find_columns_for_file(original_cols, filename_for_logging)

        # --- Step 3: Read full data using robust CSV reader --------------------
        # Determine columns to read, potentially including the scope column
        cols_to_read = {actual_date_col, actual_code_col}
        if benchmark_col_present and actual_benchmark_col:
            cols_to_read.add(actual_benchmark_col)
        if actual_scope_col:
            cols_to_read.add(actual_scope_col)
        cols_to_read.update(original_fund_val_col_names)

        # Define dtypes, read scope col as string initially
        dtype_map = {actual_date_col: str}
        if actual_scope_col:
            dtype_map[actual_scope_col] = str  # Read scope as string

        # Use robust CSV reader for data
        df = read_csv_robustly(
            filepath,
            usecols=list(cols_to_read),
            encoding="utf-8",
            encoding_errors="replace",
            on_bad_lines="skip",
            dtype=dtype_map,
        )
        if df is None:
            logger.warning(f"Data could not be read for {filepath}")
            return None

        # --- Step 4: (Optional) Aggregate duplicate rows when scope filtering OFF ---
        if not filter_sp_valid:
            numeric_hints: List[str] = list(original_fund_val_col_names)
            if benchmark_col_present and actual_benchmark_col in df.columns:
                numeric_hints.append(actual_benchmark_col)
            df = _aggregate_by_date_code(
                df,
                actual_date_col,
                actual_code_col,
                filename_for_logging,
                numeric_hint_cols=numeric_hints,
            )

        df.columns = df.columns.str.strip()  # Clean column names

        # --- Step 5: (Optional) Filter rows based on S&P Valid scope column -----
        if filter_sp_valid and actual_scope_col:
            df = _filter_by_scope(df, actual_scope_col, filename_for_logging)
            if df.empty:
                logger.warning(
                    f"DataFrame became empty after filtering on '{actual_scope_col}' for {filename_for_logging}"
                )
                empty_df = _create_empty_dataframe(
                    original_fund_val_col_names, benchmark_col_present
                )
                final_bm_col = STD_BENCHMARK_COL if benchmark_col_present else None
                return empty_df, original_fund_val_col_names, final_bm_col

        # --- Step 6: Rename standard columns -----------------------------------
        rename_map = {actual_date_col: STD_DATE_COL, actual_code_col: STD_CODE_COL}
        if (
            benchmark_col_present
            and actual_benchmark_col
            and actual_benchmark_col in df.columns
        ):
            rename_map[actual_benchmark_col] = STD_BENCHMARK_COL
        # Do NOT rename the scope column here if it existed, we only needed it for filtering

        # Perform rename
        df.rename(columns=rename_map, inplace=True)
        logger.info(f"Renamed standard columns in '{filename_for_logging}'.")

        # --- Step 7: Drop helper columns (scope) --------------------------------
        # Now that filtering is done, drop the original scope column if it exists and we don't need it further
        if actual_scope_col and actual_scope_col in df.columns:
            df.drop(columns=[actual_scope_col], inplace=True)
            logger.debug(
                f"Dropped original scope column '{actual_scope_col}' after filtering."
            )

        # --- Step 8: Parse dates & drop unparseable rows -----------------------
        df[STD_DATE_COL] = _parse_date_column(df, STD_DATE_COL, filename_for_logging)

        original_row_count = len(df)
        df.dropna(
            subset=[STD_DATE_COL], inplace=True
        )  # Drop rows where date parsing failed
        rows_dropped = original_row_count - len(df)
        if rows_dropped > 0:
            logger.warning(
                f"Dropped {rows_dropped} rows from {filename_for_logging} due to failed date parsing (after potential filtering)."
            )

        if df.empty:
            logger.warning(
                f"DataFrame became empty after dropping rows with unparseable dates in {filename_for_logging} (after potential filtering)."
            )
            empty_df = _create_empty_dataframe(
                original_fund_val_col_names, benchmark_col_present
            )
            final_bm_col = STD_BENCHMARK_COL if benchmark_col_present else None
            return empty_df, original_fund_val_col_names, final_bm_col

        df.set_index([STD_DATE_COL, STD_CODE_COL], inplace=True)

        # --- Step 9: Convert value columns to numeric & drop NaNs --------------
        _convert_value_columns(df, original_fund_val_col_names)

        # After conversion, log if any rows are dropped due to NaNs in value columns
        for col in original_fund_val_col_names:
            before = len(df)
            df.dropna(subset=[col], inplace=True)
            dropped = before - len(df)
            if dropped > 0:
                logger.warning(
                    f"Dropped {dropped} rows from {filename_for_logging} due to NaN values in column '{col}' after type conversion."
                )

        final_benchmark_col_name = (
            STD_BENCHMARK_COL
            if benchmark_col_present and STD_BENCHMARK_COL in df.columns
            else None
        )

        logger.info(
            f"Successfully processed file: '{filename_for_logging}'. Index: {df.index.names}. Columns: {df.columns.tolist()}"
        )
        return df, original_fund_val_col_names, final_benchmark_col_name

    except FileNotFoundError:
        logger.error(f"File not found during processing: {filepath}", exc_info=True)
        return None
    except pd.errors.EmptyDataError:
        logger.warning(f"File is empty: {filepath}")
        return None
    except pd.errors.ParserError as e:
        logger.error(f"Parser error in file {filepath}: {e}", exc_info=True)
        return None
    except PermissionError:
        logger.error(f"Permission denied when accessing {filepath}", exc_info=True)
        return None
    except OSError as e:
        logger.error(f"OS error when accessing {filepath}: {e}", exc_info=True)
        return None
    except ValueError as e:  # Catch ValueErrors from _find_columns or other steps
        logger.error(f"Value error processing {filename_for_logging}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error processing {filename_for_logging}: {e}")
        return None


# Simplified return type: focus on the dataframes and metadata needed downstream
LoadResult = Tuple[
    Optional[pd.DataFrame],  # Primary DataFrame
    Optional[List[str]],  # Primary original value columns
    Optional[str],  # Primary benchmark column name (standardized)
    Optional[pd.DataFrame],  # Secondary DataFrame
    Optional[List[str]],  # Secondary original value columns
    Optional[str],  # Secondary benchmark column name (standardized)
]


def load_and_process_data(
    primary_filename: str,
    secondary_filename: Optional[str] = None,
    data_folder_path: Optional[str] = None,  # Renamed and made optional
    filter_sp_valid: bool = False,  # Add parameter here
) -> Tuple[
    Optional[pd.DataFrame],
    Optional[List[str]],
    Optional[str],
    Optional[pd.DataFrame],
    Optional[List[str]],
    Optional[str],
]:
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
        filter_sp_valid (bool): If True, filters both primary and secondary dataframes
                                to include only rows where 'SS Project - In Scope' is TRUE.
                                Defaults to False (no filtering).

    Returns:
        LoadResult: A tuple containing the processed DataFrames and metadata for
                    primary and (optionally) secondary files. Elements corresponding
                    to a file will be None if the file doesn't exist or processing fails,
                    or if the file is empty after filtering.
    """
    if data_folder_path is None:
        try:
            data_folder_path = current_app.config["DATA_FOLDER"]
            logger.debug(
                f"Retrieved DATA_FOLDER from Flask app config: {data_folder_path}"
            )
        except RuntimeError:
            logger.error(
                "Attempted to load data outside of Flask application context and no data_folder_path provided."
            )
            return (
                None,
                None,
                None,
                None,
                None,
                None,
            )  # Return tuple of Nones matching LoadResult

    primary_filepath = os.path.join(data_folder_path, primary_filename)
    logger.info(
        f"Attempting to load primary file: {primary_filepath}, filter_sp_valid={filter_sp_valid}"
    )
    primary_result = _process_single_file(
        primary_filepath, primary_filename, filter_sp_valid
    )  # Pass filter flag

    df_primary, primary_val_cols, primary_bm_col = (
        (None, None, None) if primary_result is None else primary_result
    )

    df_secondary, secondary_val_cols, secondary_bm_col = None, None, None
    if secondary_filename:
        secondary_filepath = os.path.join(data_folder_path, secondary_filename)
        logger.info(
            f"Attempting to load secondary file: {secondary_filepath}, filter_sp_valid={filter_sp_valid}"
        )
        secondary_result = _process_single_file(
            secondary_filepath, secondary_filename, filter_sp_valid
        )  # Pass filter flag
        if secondary_result is not None:
            df_secondary, secondary_val_cols, secondary_bm_col = secondary_result

    # Log summary of what was loaded (or not loaded)
    primary_status = (
        "loaded successfully"
        if df_primary is not None and not df_primary.empty
        else (
            "empty or processing failed"
            if df_primary is None
            else "loaded but empty (possibly due to filtering)"
        )
    )
    secondary_status = "not requested"
    if secondary_filename:
        secondary_status = (
            "loaded successfully"
            if df_secondary is not None and not df_secondary.empty
            else (
                "empty or processing failed"
                if df_secondary is None
                else "loaded but empty (possibly due to filtering)"
            )
        )

    logger.info(
        f"Load complete. Primary file ({primary_filename}): {primary_status}. Secondary file ({secondary_filename or 'N/A'}): {secondary_status}."
    )

    return (
        df_primary,
        primary_val_cols,
        primary_bm_col,
        df_secondary,
        secondary_val_cols,
        secondary_bm_col,
    )


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
