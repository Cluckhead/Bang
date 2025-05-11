# Purpose: Preprocessing utilities for CSV files in Simple Data Checker.
# This module provides functions for reading and sorting dates, replacing placeholder headers with dates, aggregating/grouping data, and ISIN suffixing for security-level analysis.
# Used for batch preprocessing of input files before analysis.

import os
import pandas as pd
import logging
from typing import List, Optional
import config
from data_utils import read_csv_robustly
import re

# --- Filename prefix constants (5.1.2) ---
PRE_PREFIX: str = "pre_"  # Files that require full preprocessing
SEC_PREFIX: str = "sec_"  # Output files for security-level data
WEIGHT_PREFIX: str = "w_"  # Output files for weight data
PRE_WEIGHT_PREFIX: str = "pre_w_"  # Input weight files that need preprocessing
# --- End constants ---

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
            logger.warning(
                f"Some values in {dates_file_path} could not be parsed as dates."
            )
            dates_df = dates_df.dropna(subset=[dates_df.columns[0]])
            if dates_df.empty:
                logger.error(
                    f"No valid dates found in {dates_file_path} after handling parsing issues."
                )
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
    date_columns: List[str],
    metadata_cols: List[str] = None,
    *,
    log: logging.Logger = logger,
) -> pd.DataFrame:
    """Replace repeating data-column headers (e.g., Field, Field.1, Field.2, ...) with actual *date* strings.

    This version detects the repeating columns by regex (e.g., Field, Field.1, Field.2, ...),
    finds the common prefix, and only replaces those columns with dates. All other columns
    (metadata/static) are left unchanged.

    Parameters
    ----------
    df
        The dataframe to operate on. The dataframe **is modified in place** and
        also returned for convenience.
    date_columns
        A *sorted* list of date strings (``YYYY-MM-DD``) originating from
        ``Dates.csv``.
    metadata_cols
        (Unused in this version, kept for compatibility.)
    log
        Optional logger to use – defaults to module-level logger.

    Returns
    -------
    pd.DataFrame
        The dataframe with its columns potentially renamed.
    """
    all_cols: List[str] = list(df.columns)
    if not date_columns:
        log.warning("No date_columns supplied – skipping header replacement.")
        return df

    # --- Find repeating columns matching the pattern <prefix>, <prefix>.1, <prefix>.2, ... ---
    # Build a regex to match columns like 'Field.1', 'Field.2', ...
    pattern = re.compile(r"^(.*)\.(\d+)$")
    prefix_counts = {}
    prefix_to_cols = {}
    for col in all_cols:
        m = pattern.match(col)
        if m:
            prefix = m.group(1)
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            prefix_to_cols.setdefault(prefix, []).append(col)
    # Also check for columns that are just the prefix (e.g., 'Field')
    for col in all_cols:
        for prefix in prefix_counts:
            if col == prefix:
                prefix_counts[prefix] += 1
                prefix_to_cols[prefix].insert(0, col)  # Ensure prefix is first
    if not prefix_counts:
        log.warning("No repeating columns found matching <prefix> or <prefix>.<number> pattern. Skipping header replacement.")
        return df
    # Use the most common prefix (in case of multiple)
    main_prefix = max(prefix_counts, key=prefix_counts.get)
    # Get all columns to replace, in order: prefix, prefix.1, prefix.2, ...
    cols_to_replace = prefix_to_cols[main_prefix]
    if len(cols_to_replace) != len(date_columns):
        log.warning(
            f"Count mismatch: {len(cols_to_replace)} columns to replace, {len(date_columns)} date columns. Will replace up to the minimum."
        )
    replace_count = min(len(cols_to_replace), len(date_columns))
    # Map old column names to new date names
    col_rename_map = {old: date_columns[i] for i, old in enumerate(cols_to_replace[:replace_count])}
    # Apply renaming
    df = df.rename(columns=col_rename_map)
    log.info(f"Replaced {replace_count} column headers with dates using prefix '{main_prefix}'.")
    return df


def suffix_isin(isin: str, n: int) -> str:
    """
    Suffix an ISIN for duplicate security handling using the pattern from config.

    When multiple securities have the same name but different attributes,
    this function appends a suffix to the ISIN to make it unique.

    Args:
        isin (str): The original ISIN to suffix
        n (int): The suffix number (typically the index in a group of duplicates)

    Returns:
        str: The suffixed ISIN following the pattern in config.ISIN_SUFFIX_PATTERN
    """
    return config.ISIN_SUFFIX_PATTERN.format(isin=isin, n=n)


def aggregate_data(
    df: pd.DataFrame, required_cols: List[str], logger: logging.Logger, input_path: str
) -> pd.DataFrame:
    """
    Group by Security Name, merge Funds, suffix ISIN for duplicates. Returns processed DataFrame.
    """
    current_cols = df.columns.tolist()

    # Ensure required columns exist; create if missing to avoid KeyError
    for req_col in required_cols:
        if req_col not in df.columns:
            logger.warning(
                f"Required column '{req_col}' missing in {input_path}. Creating empty column to proceed."
            )
            df[req_col] = ""

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
                logger.error(
                    f"Error during sub-grouping for Security Name '{sec_name}' in {input_path}: {e}",
                    exc_info=True,
                )
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
                    new_isin = suffix_isin(original_isin, i + 1)
                    new_row_series[isin_col_name] = new_isin
                    logger.debug(
                        f"Suffixed ISIN for duplicate Security Name '{sec_name}'. Original: '{original_isin}', New: '{new_isin}'"
                    )
                else:
                    logger.warning(
                        f"Found {num_versions} distinct data versions for Security Name '{sec_name}' but column '{isin_col_name}' not found. Cannot apply suffix to ISIN."
                    )
            processed_rows.append(new_row_series.to_dict())
    if not processed_rows:
        logger.warning(
            f"No data rows processed for {input_path}. Output file will not be created."
        )
        return pd.DataFrame(columns=current_cols)
    output_df = pd.DataFrame(processed_rows)
    final_cols = [col for col in current_cols if col in output_df.columns]
    output_df = output_df[final_cols]
    output_df = output_df.fillna(0)
    return output_df


def process_input_file(
    input_path: str, output_path: str, dates_path: str, config_dict: dict
) -> None:
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
        df = read_csv_robustly(
            input_path, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip"
        )
        if df is None or df.empty:
            logger.warning(
                f"Input file {input_path} is empty or could not be read. Skipping."
            )
            return
        dates = read_and_sort_dates(dates_path)
        if dates is None:
            logger.warning(
                f"Could not read or process dates from {dates_path}. Skipping {input_path}."
            )
            return
        filename = os.path.basename(input_path)
        if filename.startswith("pre_w_"):
            # Weight file: identify metadata columns dynamically (detect_metadata_columns handles w_secs vs others)
            df = replace_headers_with_dates(
                df,
                dates,
                df.columns[: detect_metadata_columns(df)].tolist(),
            )
            df.to_csv(output_path, index=False, encoding="utf-8")
            logger.info(f"Successfully processed weight file: {output_path}")
        elif filename.startswith("pre_"):
            # General pre_ file: replace headers, aggregate, save as sec_*.csv
            required_cols = [config.FUNDS_COL, config.SEC_NAME_COL]
            metadata_candidates = [col for col in df.columns if col in config.METADATA_COLS]
            if metadata_candidates:
                last_meta_idx = max(df.columns.get_loc(col) for col in metadata_candidates)
                metadata_cols = df.columns[:last_meta_idx + 1]
            else:
                # fallback to old logic if no metadata columns found
                last_required_idx = -1
                for req_col in required_cols:
                    try:
                        last_required_idx = max(
                            last_required_idx, df.columns.get_loc(req_col)
                        )
                    except KeyError:
                        logger.error(
                            f"Required column '{req_col}' not found in {input_path}. Skipping."
                        )
                        return
                metadata_cols = df.columns[:last_required_idx + 1]
            df = replace_headers_with_dates(df, dates, metadata_cols)
            output_df = aggregate_data(df, required_cols, logger, input_path)
            if output_df.empty:
                logger.warning(
                    f"No data rows processed for {input_path}. Output file will not be created."
                )
                return
            output_df.to_csv(output_path, index=False, encoding="utf-8")
            logger.info(f"Successfully processed file: {output_path}")
        else:
            logger.warning(
                f"File {input_path} does not match expected pre_ or pre_w_ pattern. Skipping."
            )
    except Exception as e:
        logger.error(f"Error processing input file {input_path}: {e}", exc_info=True)


def detect_metadata_columns(df: pd.DataFrame, min_numeric_cols: int = 3) -> int:
    """Detect the number of metadata columns in a DataFrame.

    This utility mirrors the original implementation that lived in
    ``weight_processing.py`` but is now centralised here so it can be re-used
    by any preprocessing logic.

    The function first checks whether *all* of the standard metadata column
    names defined in ``config.METADATA_COLS`` are present. If so, the count of
    those columns is returned immediately.  Otherwise, it falls back to a
    heuristic that scans the first few non-metadata columns looking for a
    minimum number of numeric columns (``min_numeric_cols``).

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame whose columns should be inspected.
    min_numeric_cols : int, default 3
        The minimum consecutive numeric columns that signal the start of the
        actual numeric data section.

    Returns
    -------
    int
        The index *after* the last metadata column (i.e. suitable for slicing
        ``df.iloc[:, :meta_end_idx]`` to obtain the metadata columns).
    """
    # Fast-path: use predefined list if all present
    if hasattr(config, "METADATA_COLS") and all(
        col in df.columns for col in config.METADATA_COLS
    ):
        return len(config.METADATA_COLS)

    # Heuristic detection fallback
    for i in range(1, len(df.columns)):
        numeric_count = 0
        # Look ahead up to ``min_numeric_cols`` columns
        for j in range(i, min(i + min_numeric_cols, len(df.columns))):
            sample = df.iloc[:, j].dropna().head(10)
            if sample.apply(
                lambda x: pd.api.types.is_number(x)
                or pd.api.types.is_float(x)
                or pd.api.types.is_integer(x)
            ).all():
                numeric_count += 1
        if numeric_count == min_numeric_cols:
            return i  # Metadata columns occupy positions < i

    # Fallback: assume only the first column is metadata
    return 1
