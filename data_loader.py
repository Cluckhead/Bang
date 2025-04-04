# data_loader.py
# This file contains functions for loading and preparing the data from CSV files.

import pandas as pd
import os
import logging
from typing import List, Tuple, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define constants
DATA_FOLDER = 'Data'
DEFAULT_DATE_COL = 'Date' # Example default, adjust if needed
DEFAULT_CODE_COL = 'Code' # Example default, adjust if needed
DEFAULT_BENCHMARK_COL = 'Benchmark' # Example default, adjust if needed

def load_and_process_data(
    filename: str,
    date_col: str = DEFAULT_DATE_COL,
    code_col: str = DEFAULT_CODE_COL,
    benchmark_col: str = DEFAULT_BENCHMARK_COL,
    other_fund_cols: Optional[List[str]] = None,
    data_folder: str = DATA_FOLDER
) -> Tuple[pd.DataFrame, List[str], str]:
    """Loads a CSV file, identifies key columns based on provided names,
    parses dates, sets index, and ensures numeric types for value columns.

    Args:
        filename (str): The name of the CSV file within the data folder.
        date_col (str): The exact name of the date column. Defaults to DEFAULT_DATE_COL.
        code_col (str): The exact name of the fund code identifier column. Defaults to DEFAULT_CODE_COL.
        benchmark_col (str): The exact name of the benchmark value column. Defaults to DEFAULT_BENCHMARK_COL.
        other_fund_cols (Optional[List[str]]): A list of exact names for other fund value columns.
                                                If None, all columns except date, code, and benchmark
                                                are assumed to be fund columns. Defaults to None.
        data_folder (str): The path to the folder containing the data files. Defaults to DATA_FOLDER.

    Returns:
        Tuple[pd.DataFrame, List[str], str]:
               Processed DataFrame indexed by date and fund code,
               list of identified fund column names,
               the benchmark column name.

    Raises:
        ValueError: If the file doesn't contain the required columns or if no value columns are found.
        FileNotFoundError: If the specified file does not exist.
    """
    filepath = os.path.join(data_folder, filename)
    if not os.path.exists(filepath):
        logging.error(f"File not found: {filepath}")
        raise FileNotFoundError(f"File not found: {filepath}")

    try:
        # Read only the header first to get column names accurately
        header_df = pd.read_csv(filepath, nrows=0)
        original_cols = [col.strip() for col in header_df.columns.tolist()] # Strip whitespace immediately

        # --- Validate required columns exist ---
        required_cols = {date_col, code_col, benchmark_col}
        if not required_cols.issubset(original_cols):
            missing = required_cols - set(original_cols)
            raise ValueError(f"File '{filename}' is missing required columns: {missing}. Found: {original_cols}")

        # --- Identify fund value columns ---
        if other_fund_cols:
            # Use explicitly provided list
            fund_val_col_names = [col for col in other_fund_cols if col in original_cols]
            if not fund_val_col_names:
                 logging.warning(f"Provided 'other_fund_cols' not found in '{filename}'.")
            # Ensure provided fund columns don't overlap with key identifier/benchmark columns
            reserved_cols = {date_col, code_col, benchmark_col}
            overlap = set(fund_val_col_names).intersection(reserved_cols)
            if overlap:
                 logging.warning(f"Columns {overlap} listed in 'other_fund_cols' are reserved and will be ignored as fund columns.")
                 fund_val_col_names = [col for col in fund_val_col_names if col not in overlap]
        else:
            # Assume all other columns are fund columns
            excluded_cols = {date_col, code_col, benchmark_col}
            fund_val_col_names = [col for col in original_cols if col not in excluded_cols]
            if not fund_val_col_names:
                 logging.warning(f"No additional fund columns automatically identified in '{filename}' besides date, code, and benchmark.")


        # --- Read the full CSV ---
        # Specify date parsing for the identified date column
        df = pd.read_csv(filepath, parse_dates=[date_col], dayfirst=True)
        df.columns = df.columns.str.strip() # Ensure columns are stripped again after full read

        # --- Set Index ---
        df.set_index([date_col, code_col], inplace=True)

        # --- Convert value columns to numeric ---
        value_cols_to_convert = [col for col in fund_val_col_names + [benchmark_col] if col in df.columns]
        if not value_cols_to_convert:
            # This should be rare given earlier checks, but safeguard anyway
            raise ValueError(f"No valid fund or benchmark value columns found to convert in {filename}. Identified: {fund_val_col_names}, Benchmark: {benchmark_col}")

        # Use apply with pd.to_numeric for robust conversion
        df[value_cols_to_convert] = df[value_cols_to_convert].apply(pd.to_numeric, errors='coerce')
        if df[value_cols_to_convert].isnull().all().all():
            logging.warning(f"All values in value columns {value_cols_to_convert} became NaN after conversion in file {filename}. Check data types.")


        logging.info(f"Successfully loaded and processed '{filename}'. Identified Funds: {fund_val_col_names}, Benchmark: {benchmark_col}")
        return df, fund_val_col_names, benchmark_col

    except Exception as e:
        logging.error(f"Error processing file {filename}: {e}", exc_info=True)
        # Re-raise the exception after logging
        raise 