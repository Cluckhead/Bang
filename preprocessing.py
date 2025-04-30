# Purpose: Preprocessing utilities for CSV files in Simple Data Checker.
# This module provides functions for reading and sorting dates, replacing placeholder headers with dates, aggregating/grouping data, and ISIN suffixing for security-level analysis.
# Used for batch preprocessing of input files before analysis.

import os
import pandas as pd
import logging
from typing import List, Optional
import config
from data_utils import read_csv_robustly

logger = logging.getLogger(__name__)

def read_and_sort_dates(dates_file_path: str) -> Optional[List[str]]:
    """
    Reads dates from a CSV file, sorts them, and returns them as a list of strings (YYYY-MM-DD).
    Returns None if an error occurs.
    """
    if not dates_file_path or not os.path.exists(dates_file_path):
        logger.error(f"Dates file not found at {dates_file_path}")
        return None
    try:
        dates_df = pd.read_csv(dates_file_path, parse_dates=[0])
        if dates_df.iloc[:, 0].isnull().any():
            logger.warning(f"Some values in {dates_file_path} could not be parsed as dates.")
            dates_df = dates_df.dropna(subset=[dates_df.columns[0]])
            if dates_df.empty:
                logger.error(f"No valid dates found in {dates_file_path} after handling parsing issues.")
                return None
        sorted_dates = dates_df.iloc[:, 0].sort_values()
        date_strings = sorted_dates.dt.strftime("%Y-%m-%d").tolist()
        unique_date_strings = []
        seen_dates = set()
        for date_str in date_strings:
            if date_str not in seen_dates:
                unique_date_strings.append(date_str)
                seen_dates.add(date_str)
        return unique_date_strings
    except Exception as e:
        logger.error(f"Error reading dates from {dates_file_path}: {e}", exc_info=True)
        return None

def replace_headers_with_dates(
    df: pd.DataFrame,
    required_cols: List[str],
    candidate_start_index: int,
    candidate_cols: List[str],
    date_columns: Optional[List[str]],
    dates_file_path: str,
    logger: logging.Logger,
    input_path: str,
) -> pd.DataFrame:
    """
    Detects placeholder columns and replaces them with date columns if needed.
    Returns a DataFrame with updated headers.
    """
    current_cols = df.columns.tolist()
    # Pattern B: all candidate columns are the same
    is_patternB = candidate_cols and all(col == candidate_cols[0] for col in candidate_cols)
    if date_columns is None:
        logger.warning(f"Date information from {dates_file_path} is unavailable. Cannot check or replace headers in {input_path}. Processing with original headers: {current_cols}")
        return df
    if is_patternB:
        if len(date_columns) == len(candidate_cols):
            new_columns = current_cols[:candidate_start_index] + date_columns + current_cols[candidate_start_index+len(candidate_cols):]
            if len(new_columns) == len(current_cols):
                df.columns = new_columns
                logger.info(f"Replaced {len(candidate_cols)} repeated '{candidate_cols[0]}' columns with dates.")
            else:
                logger.error(f"Column count mismatch after constructing new columns. Keeping original headers.")
        else:
            logger.warning(f"Count mismatch: Found {len(candidate_cols)} repeated '{candidate_cols[0]}' columns, but expected {len(date_columns)} dates. Skipping date replacement.")
    elif candidate_cols == date_columns:
        logger.debug(f"Columns after required ones already match the expected dates. No replacement needed.")
    return df

def suffix_isin(isin: str, n: int) -> str:
    """Return a suffixed ISIN using the pattern from config."""
    return config.ISIN_SUFFIX_PATTERN.format(isin=isin, n=n)

def aggregate_data(
    df: pd.DataFrame, required_cols: List[str], logger: logging.Logger, input_path: str
) -> pd.DataFrame:
    """
    Group by Security Name, merge Funds, suffix ISIN for duplicates. Returns processed DataFrame.
    """
    current_cols = df.columns.tolist()
    id_cols = [col for col in current_cols if col not in required_cols]
    processed_rows = []
    df["Security Name"] = df["Security Name"].astype(str)
    df["Funds"] = df["Funds"].astype(str)
    grouped_by_sec = df.groupby("Security Name", sort=False, dropna=False)
    for sec_name, sec_group in grouped_by_sec:
        distinct_versions = []
        if id_cols:
            try:
                sub_grouped = sec_group.groupby(id_cols, dropna=False, sort=False)
                distinct_versions = [group for _, group in sub_grouped]
            except Exception as e:
                logger.error(f"Error during sub-grouping for Security Name '{sec_name}' in {input_path}: {e}", exc_info=True)
                continue
        else:
            distinct_versions = [sec_group]
        num_versions = len(distinct_versions)
        for i, current_version_df in enumerate(distinct_versions):
            if current_version_df.empty:
                continue
            unique_funds = current_version_df["Funds"].dropna().unique()
            funds_list = sorted([str(f) for f in unique_funds])
            new_row_series = current_version_df.iloc[0].copy()
            new_row_series["Funds"] = f"[{','.join(funds_list)}]"
            if num_versions > 1:
                isin_col_name = config.ISIN_COL
                if isin_col_name in new_row_series.index:
                    original_isin = new_row_series[isin_col_name]
                    new_isin = suffix_isin(original_isin, i+1)
                    new_row_series[isin_col_name] = new_isin
                    logger.debug(f"Suffixed ISIN for duplicate Security Name '{sec_name}'. Original: '{original_isin}', New: '{new_isin}'")
                else:
                    logger.warning(f"Found {num_versions} distinct data versions for Security Name '{sec_name}' but column '{isin_col_name}' not found. Cannot apply suffix to ISIN.")
            processed_rows.append(new_row_series.to_dict())
    if not processed_rows:
        logger.warning(f"No data rows processed for {input_path}. Output file will not be created.")
        return pd.DataFrame(columns=current_cols)
    output_df = pd.DataFrame(processed_rows)
    final_cols = [col for col in current_cols if col in output_df.columns]
    output_df = output_df[final_cols]
    output_df = output_df.fillna(0)
    return output_df 

def process_input_file(input_path: str, output_path: str, dates_path: str, config_dict: dict) -> None:
    """
    Processes an input CSV file and writes the processed output to output_path.
    Handles both pre_*.csv and pre_w_*.csv files, replacing headers with dates and aggregating as needed.
    Args:
        input_path (str): Path to the input CSV file.
        output_path (str): Path to write the processed CSV file.
        dates_path (str): Path to the dates CSV file.
        config_dict (dict): Configuration dictionary (not used yet, for future extensibility).
    """
    logger.info(f"Processing input file: {input_path} -> {output_path}")
    try:
        df = read_csv_robustly(input_path, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip")
        if df is None or df.empty:
            logger.warning(f"Input file {input_path} is empty or could not be read. Skipping.")
            return
        dates = read_and_sort_dates(dates_path)
        if dates is None:
            logger.warning(f"Could not read or process dates from {dates_path}. Skipping {input_path}.")
            return
        filename = os.path.basename(input_path)
        if filename.startswith("pre_w_"):
            # Weight file: identify metadata columns, replace headers with dates, save as w_*.csv
            # Heuristic: metadata columns are all columns before the first placeholder/date col
            # Assume candidate columns are all columns after required ones (first two: Funds, ISIN)
            required_cols = [config.FUNDS_COL, config.ISIN_COL]
            current_df_cols = df.columns.tolist()
            last_required_idx = -1
            for req_col in required_cols:
                try:
                    last_required_idx = max(last_required_idx, current_df_cols.index(req_col))
                except ValueError:
                    logger.error(f"Required column '{req_col}' not found in {input_path}. Skipping.")
                    return
            candidate_start_index = last_required_idx + 1
            candidate_cols = current_df_cols[candidate_start_index:]
            df = replace_headers_with_dates(
                df,
                required_cols,
                candidate_start_index,
                candidate_cols,
                dates,
                dates_path,
                logger,
                input_path,
            )
            df.to_csv(output_path, index=False, encoding="utf-8")
            logger.info(f"Successfully processed weight file: {output_path}")
        elif filename.startswith("pre_"):
            # General pre_ file: replace headers, aggregate, save as sec_*.csv
            required_cols = [config.FUNDS_COL, config.SEC_NAME_COL]
            current_df_cols = df.columns.tolist()
            last_required_idx = -1
            for req_col in required_cols:
                try:
                    last_required_idx = max(last_required_idx, current_df_cols.index(req_col))
                except ValueError:
                    logger.error(f"Required column '{req_col}' not found in {input_path}. Skipping.")
                    return
            candidate_start_index = last_required_idx + 1
            candidate_cols = current_df_cols[candidate_start_index:]
            df = replace_headers_with_dates(
                df,
                required_cols,
                candidate_start_index,
                candidate_cols,
                dates,
                dates_path,
                logger,
                input_path,
            )
            output_df = aggregate_data(df, required_cols, logger, input_path)
            if output_df.empty:
                logger.warning(f"No data rows processed for {input_path}. Output file will not be created.")
                return
            output_df.to_csv(output_path, index=False, encoding="utf-8")
            logger.info(f"Successfully processed file: {output_path}")
        else:
            logger.warning(f"File {input_path} does not match expected pre_ or pre_w_ pattern. Skipping.")
    except Exception as e:
        logger.error(f"Error processing input file {input_path}: {e}", exc_info=True) 