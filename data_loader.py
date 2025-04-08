# This file is responsible for loading and preprocessing data from CSV files.
# It includes functions to dynamically identify essential columns (Date, Code, Benchmark)
# based on patterns, handle potential naming variations, parse dates, standardize column names,
# set appropriate data types, and prepare the data in a pandas DataFrame format
# suitable for further analysis and processing within the application.
# data_loader.py
# This file is responsible for loading and preprocessing data from time-series CSV files (typically prefixed with `ts_`).
# It includes functions to dynamically identify essential columns (Date, Code, Benchmark)
# based on patterns, handle potential naming variations, parse dates (handling 'YYYY-MM-DD' and 'DD/MM/YYYY'),
# standardize column names, set appropriate data types, and prepare the data in a pandas DataFrame format
# suitable for further analysis within the application. It includes robust error handling and logging.

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

def _find_column(pattern: str, columns: List[str], filename: str, col_type: str) -> str:
    """Helper function to find a single column matching a pattern (case-insensitive)."""
    matches = [col for col in columns if re.search(pattern, col, re.IGNORECASE)]
    if len(matches) == 1:
        logger.info(f"Found {col_type} column in '{filename}': '{matches[0]}'")
        return matches[0]
    elif len(matches) > 1:
        # Log error before raising
        logger.error(f"Multiple possible {col_type} columns found in '{filename}' matching pattern '{pattern}': {matches}. Please ensure unique column names.")
        raise ValueError(f"Multiple possible {col_type} columns found in '{filename}' matching pattern '{pattern}': {matches}. Please ensure unique column names.")
    else:
         # Log error before raising
        logger.error(f"No {col_type} column found in '{filename}' matching pattern '{pattern}'. Found columns: {columns}")
        raise ValueError(f"No {col_type} column found in '{filename}' matching pattern '{pattern}'. Found columns: {columns}")

def load_and_process_data(
    filename: str,
    # Remove default args for specific names as they are now dynamically found
    # date_col: str = DEFAULT_DATE_COL,
    # code_col: str = DEFAULT_CODE_COL,
    # benchmark_col: str = DEFAULT_BENCHMARK_COL,
    # other_fund_cols: Optional[List[str]] = None, # Keep for potential future explicit override, but primary logic is dynamic
    data_folder: str = DATA_FOLDER
) -> Tuple[pd.DataFrame, List[str], Optional[str]]: # Changed return type hint for benchmark_col
    """Loads a CSV file, dynamically identifies date, code, and benchmark columns,
    renames them to standard names ('Date', 'Code', 'Benchmark'), parses dates (trying YYYY-MM-DD then DD/MM/YYYY),
    sets index, identifies original fund column names, and ensures numeric types for value columns.

    Args:
        filename (str): The name of the CSV file within the data folder.
        data_folder (str): The path to the folder containing the data files. Defaults to DATA_FOLDER.

    Returns:
        Tuple[pd.DataFrame, List[str], Optional[str]]:
               Processed DataFrame indexed by the standardized 'Date' and 'Code' columns,
               list of original fund column names found in the file,
               the standardized benchmark column name ('Benchmark') if present, otherwise None.

    Raises:
        ValueError: If required columns (Date, Code) cannot be uniquely identified,
                    if date parsing fails completely, or if no value columns are found (and no benchmark).
        FileNotFoundError: If the specified file does not exist.
    """
    filepath = os.path.join(data_folder, filename)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise FileNotFoundError(f"File not found: {filepath}")

    try:
        # Read only the header first to get column names accurately
        header_df = pd.read_csv(filepath, nrows=0, encoding='utf-8', encoding_errors='replace', on_bad_lines='skip')
        original_cols = [col.strip() for col in header_df.columns.tolist()] # Strip whitespace immediately
        logger.info(f"Original columns found in '{filename}': {original_cols}")

        # --- Dynamically find required columns using patterns ---
        # Use word boundaries (\b) to avoid partial matches like 'Benchmarking'
        actual_date_col = _find_column(r'\bDate\b', original_cols, filename, 'Date')
        actual_code_col = _find_column(r'\bCode\b', original_cols, filename, 'Code')
        # Allow benchmark column to be optional - look for it, but don't fail if not found.
        try:
            actual_benchmark_col = _find_column(r'\bBenchmark\b', original_cols, filename, 'Benchmark')
            benchmark_col_present = True
        except ValueError:
            logger.warning(f"No Benchmark column found in '{filename}' matching pattern '\\bBenchmark\\b'. Proceeding without benchmark.")
            actual_benchmark_col = None # Indicate benchmark is not present
            benchmark_col_present = False

        # --- Identify original fund value columns ---
        # Fund columns are everything EXCEPT the identified date and code columns.
        # Benchmark is also excluded IF it was found.
        excluded_cols_for_funds = {actual_date_col, actual_code_col}
        if benchmark_col_present and actual_benchmark_col: # Check actual_benchmark_col is not None
            excluded_cols_for_funds.add(actual_benchmark_col)

        # Identify columns that are not date, code, or benchmark (if present)
        original_fund_val_col_names = [col for col in original_cols if col not in excluded_cols_for_funds]

        if not original_fund_val_col_names and not benchmark_col_present:
             logger.error(f"No fund value columns and no benchmark column identified in '{filename}'. Cannot process.")
             raise ValueError(f"No fund value columns and no benchmark column identified in '{filename}'. Cannot process.")
        elif not original_fund_val_col_names:
             logger.warning(f"No specific fund value columns identified in '{filename}' besides the benchmark column.")
        else:
            logger.info(f"Identified Fund columns in '{filename}': {original_fund_val_col_names}")


        # --- Read the full CSV ---
        # Read WITHOUT parsing dates initially, handle it manually later for flexibility
        df = pd.read_csv(filepath, encoding='utf-8', encoding_errors='replace', on_bad_lines='skip', dtype={actual_date_col: str}) # Read date col as string
        df.columns = df.columns.str.strip() # Ensure columns are stripped again after full read

        # --- Rename columns to standard names BEFORE date parsing ---
        rename_map = {
            actual_date_col: STD_DATE_COL,
            actual_code_col: STD_CODE_COL
        }
        if benchmark_col_present and actual_benchmark_col:
            rename_map[actual_benchmark_col] = STD_BENCHMARK_COL

        df.rename(columns=rename_map, inplace=True)
        logger.info(f"Renamed columns in '{filename}' to standard names: {list(rename_map.keys())} -> {list(rename_map.values())}")


        # --- Robust Date Parsing ---
        date_series = df[STD_DATE_COL]
        parsed_dates = pd.to_datetime(date_series, format='%Y-%m-%d', errors='coerce')
        # Check if the first format failed for all entries (common if format is wrong)
        if parsed_dates.isnull().all():
            logger.info(f"Date format '%Y-%m-%d' failed for all entries in {filename}. Trying '%d/%m/%Y'.")
            parsed_dates = pd.to_datetime(date_series, format='%d/%m/%Y', errors='coerce')
            # Check if the second format also failed
            if parsed_dates.isnull().all():
                logger.error(f"Could not parse dates in column '{STD_DATE_COL}' (original: '{actual_date_col}') using either YYYY-MM-DD or DD/MM/YYYY format in file {filename}.")
                raise ValueError(f"Date parsing failed for file {filename}.")
            else:
                logger.info(f"Successfully parsed dates using format '%d/%m/%Y' for {filename}.")
        else:
             logger.info(f"Successfully parsed dates using format '%Y-%m-%d' for {filename}.")

        # Assign the successfully parsed dates back to the DataFrame
        df[STD_DATE_COL] = parsed_dates
        # Drop rows where date parsing failed completely (became NaT)
        original_row_count = len(df)
        df.dropna(subset=[STD_DATE_COL], inplace=True)
        rows_dropped = original_row_count - len(df)
        if rows_dropped > 0:
            logger.warning(f"Dropped {rows_dropped} rows from {filename} due to failed date parsing.")

        # --- Set Index using standard names ---
        if df.empty:
            logger.warning(f"DataFrame became empty after dropping rows with unparseable dates in {filename}.")
            # Return an empty DataFrame matching the expected structure but log the issue
            final_benchmark_col_name = STD_BENCHMARK_COL if benchmark_col_present else None
            # Need to define columns if df is empty, based on expected output structure
            expected_cols = [STD_DATE_COL, STD_CODE_COL] + original_fund_val_col_names
            if final_benchmark_col_name:
                expected_cols.append(final_benchmark_col_name)
            # Create an empty df with the right index and columns
            empty_index = pd.MultiIndex(levels=[[], []], codes=[[], []], names=[STD_DATE_COL, STD_CODE_COL])
            return pd.DataFrame(index=empty_index, columns=[col for col in expected_cols if col not in [STD_DATE_COL, STD_CODE_COL]]), original_fund_val_col_names, final_benchmark_col_name
        else:
            df.set_index([STD_DATE_COL, STD_CODE_COL], inplace=True)


        # --- Convert value columns to numeric ---
        # Use original fund names and the standard benchmark name (if present)
        value_cols_to_convert = original_fund_val_col_names[:] # Make a copy
        if benchmark_col_present:
             # Use the RENAMED benchmark column name for conversion
            value_cols_to_convert.append(STD_BENCHMARK_COL)

        if not value_cols_to_convert:
            # This case implies only date/code columns were found, which should be caught earlier, but safeguard.
            logger.error(f"No valid fund or benchmark value columns found to convert in {filename} after processing.")
            raise ValueError(f"No valid fund or benchmark value columns found to convert in {filename} after processing.")

        # Ensure the columns actually exist in the DataFrame after renaming before converting
        valid_cols_for_conversion = [col for col in value_cols_to_convert if col in df.columns]
        if not valid_cols_for_conversion:
             logger.error(f"None of the identified value columns ({value_cols_to_convert}) exist in the DataFrame after renaming. Columns: {df.columns.tolist()}")
             raise ValueError(f"None of the identified value columns ({value_cols_to_convert}) exist in the DataFrame after renaming. Columns: {df.columns.tolist()}")

        # Use apply with pd.to_numeric for robust conversion (errors='coerce' is crucial)
        df[valid_cols_for_conversion] = df[valid_cols_for_conversion].apply(pd.to_numeric, errors='coerce')

        # Check for NaNs after conversion
        nan_check_cols = [col for col in valid_cols_for_conversion if col in df.columns] # Re-check existence just in case
        if nan_check_cols and df[nan_check_cols].isnull().all().all():
            logger.warning(f"All values in value columns {nan_check_cols} became NaN after conversion in file {filename}. Check data types.")

        # Return the DataFrame, the ORIGINAL fund column names, and the STANDARD benchmark name
        # Return STD_BENCHMARK_COL if benchmark was present, else None
        final_benchmark_col_name = STD_BENCHMARK_COL if benchmark_col_present else None
        logger.info(f"Successfully loaded and processed '{filename}'. Identified Original Funds: {original_fund_val_col_names}, Standard Benchmark Name Used: {final_benchmark_col_name}")
        return df, original_fund_val_col_names, final_benchmark_col_name

    except Exception as e:
        # Log the error with traceback information to file and console
        logger.error(f"Error processing file {filepath}: {e}", exc_info=True)
        # Re-raise the exception to be handled by the calling code (e.g., in app.py or script runner)
        # The calling code should decide whether to skip the file or halt execution.
        raise 