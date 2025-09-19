  # Purpose: Preprocessing utilities for CSV files in Simple Data Checker.
# This module provides functions for reading and sorting dates, replacing placeholder headers with dates, aggregating/grouping data, and ISIN suffixing for security-level analysis.
# Used for batch preprocessing of input files before analysis.

import os
import pandas as pd
import logging
from typing import List, Optional
from core import config
from core.data_utils import read_csv_robustly
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
        dates_df = pd.read_csv(dates_file_path, parse_dates=[0], dayfirst=True)
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
        
        # Ensure the date column is properly converted to datetime before using .dt accessor
        date_column = dates_df.iloc[:, 0]
        if not pd.api.types.is_datetime64_any_dtype(date_column):
            logger.warning(f"Date column in {dates_file_path} is not datetime type. Attempting conversion.")
            try:
                date_column = pd.to_datetime(date_column, errors='coerce')
                # Remove any NaT values that couldn't be converted
                date_column = date_column.dropna()
                if date_column.empty:
                    logger.error(f"No valid dates after datetime conversion in {dates_file_path}")
                    return None
            except Exception as convert_err:
                logger.error(f"Failed to convert dates to datetime in {dates_file_path}: {convert_err}")
                return None
        
        sorted_dates = date_column.sort_values()
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
    log.debug(f"Replaced {replace_count} column headers with dates using prefix '{main_prefix}'.")
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
                    #logger.debug(
                    #    f"Suffixed ISIN for duplicate Security Name '{sec_name}'. Original: '{original_isin}', New: '{new_isin}'"
                    #)
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
    filename = os.path.basename(input_path)
    logger.debug(f"Processing input file: {filename} -> {os.path.basename(output_path)}")
    try:
        df = read_csv_robustly(
            input_path, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip"
        )
        if df is None or df.empty:
            logger.warning(
                f"Input file {input_path} is empty or could not be read. Skipping."
            )
            return

        # ------------------------------------------------------------------
        # NEW: Handle *long* format input (ISIN, Funds, Date, Value) directly
        #      without header replacement.  The presence of both a "Date" and
        #      a "Value" column uniquely identifies the new API pivot format.
        # ------------------------------------------------------------------

        # Check for various column name patterns for long-format data
        date_col = None
        value_col = None
        
        # Look for date column variations
        for col in df.columns:
            if col.lower() in ['date', 'position date', 'position_date']:
                date_col = col
                break
                
        # Look for value column variations  
        for col in df.columns:
            if col.lower() in ['value', 'accrued interest', 'accrued_interest']:
                value_col = col
                break

        if date_col is not None and value_col is not None:
            logger.debug(f"Detected long-format security data – applying pivot logic. Date column: '{date_col}', Value column: '{value_col}'")

            # Standardize column names for processing
            if date_col != "Date":
                df = df.rename(columns={date_col: "Date"})
            if value_col != "Value":
                df = df.rename(columns={value_col: "Value"})

            # 1) Parse and normalise the Date column (handle ISO format like 2025-06-02T00:00:00)
            try:
                # First attempt ISO parsing
                iso_parsed = pd.to_datetime(df["Date"], errors="coerce")
                if iso_parsed.isna().all():
                    # ISO failed for every row – try dayfirst
                    logger.info("ISO date parse failed for all rows – retrying with dayfirst=True")
                    dayfirst_parsed = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
                    parsed = dayfirst_parsed
                    detected_fmt = "dayfirst"
                else:
                    # Use ISO parsed, but still try dayfirst for rows that failed individually
                    dayfirst_parsed = pd.to_datetime(df.loc[iso_parsed.isna(), "Date"], dayfirst=True, errors="coerce")
                    parsed = iso_parsed
                    parsed.loc[iso_parsed.isna()] = dayfirst_parsed
                    detected_fmt = "mixed (ISO + fallback dayfirst)"
                failed_rows = parsed.isna().sum()
                df["Date"] = parsed
                if failed_rows:
                    logger.warning(f"{failed_rows} rows in {input_path} had unparseable dates and were dropped during long-format preprocessing.")
                df = df.dropna(subset=["Date"])
                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                logger.debug(f"Long-format date parsing complete (detected {detected_fmt}). Sample: {df['Date'].head(5).tolist()}")
            except Exception as exc:
                logger.error(f"Failed to parse Date column in {input_path}: {exc}")
                return

            # 2) Merge in reference metadata (Security Name, Type, Callable, Currency)
            reference_path = os.path.join(os.path.dirname(dates_path), "reference.csv")
            if not os.path.exists(reference_path):
                logger.warning(
                    "Reference metadata file not found at %s – continuing without enrichment.",
                    reference_path,
                )
                ref_df = None
            else:
                try:
                    ref_df = pd.read_csv(reference_path)
                except Exception as exc:
                    logger.error(
                        "Could not read reference file %s: %s – proceeding without enrichment.",
                        reference_path,
                        exc,
                    )
                    ref_df = None

            if ref_df is not None:
                # Select and rename relevant columns if present.
                rename_map = {}
                if "Security Sub Type" in ref_df.columns:
                    rename_map["Security Sub Type"] = "Type"
                if "Call Indicator" in ref_df.columns:
                    rename_map["Call Indicator"] = "Callable"
                # Handle legacy and new currency column headers
                if "CCY" in ref_df.columns:
                    rename_map["CCY"] = "Currency"  # legacy header
                if "Position Currency" in ref_df.columns:
                    rename_map["Position Currency"] = "Currency"  # new header
                ref_df = ref_df.rename(columns=rename_map)

                # Keep only columns we actually need
                wanted_cols = [
                    config.ISIN_COL,
                    config.SEC_NAME_COL,
                    "Type",
                    "Callable",
                    "Currency",
                ]
                ref_df = ref_df[[c for c in wanted_cols if c in ref_df.columns]].copy()

                # Normalise callable values to single letters (Y/N) if necessary
                if "Callable" in ref_df.columns:
                    ref_df["Callable"] = ref_df["Callable"].astype(str).str.upper().map(
                        {"TRUE": "Y", "FALSE": "N"}
                    ).fillna(ref_df["Callable"])

                df = df.merge(ref_df, how="left", on=config.ISIN_COL)

            # Special handling for accrued interest files which don't need metadata columns
            filename = os.path.basename(input_path).lower()
            if "accrued" in filename:
                # Accrued interest files only need ISIN as the pivot index
                pivot_index = [config.ISIN_COL]
                logger.debug("Detected accrued interest file - using simplified pivot index")
            else:
                # Ensure mandatory metadata columns exist even if missing from ref
                for col in [config.SEC_NAME_COL, "Type", "Callable", "Currency"]:
                    if col not in df.columns:
                        df[col] = ""

                # 3) Pivot – rows -> dates across columns
                pivot_index = [
                    config.ISIN_COL,
                    config.SEC_NAME_COL,
                    config.FUNDS_COL,
                    "Type",
                    "Callable",
                    "Currency",
                ]

            try:
                wide_df = (
                    df.pivot_table(
                        index=pivot_index,
                        columns="Date",
                        values="Value",
                        aggfunc="first",
                    )
                    .reset_index()
                )
            except Exception as exc:
                logger.error(f"Failed to pivot long-format data in {input_path}: {exc}")
                return

            # Flatten the MultiIndex columns that pivot_table produced
            wide_df.columns = [str(col) for col in wide_df.columns]

            # 4) Order the date columns chronologically *without* introducing
            #    any additional dates. We do *not* rely on Dates.csv for the
            #    new long-format files – only the dates that actually appear
            #    in the incoming data are retained.
            date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
            date_cols = sorted(
                [c for c in wide_df.columns if date_pattern.fullmatch(c)],
                key=lambda d: d,
            )
            wide_df = wide_df[pivot_index + date_cols]

            # Special-case: Weight files (pre_w_*) should NOT be aggregated across
            # securities because each row corresponds to a specific Fund/ISIN
            # combination with its own weight.  Simply write the pivoted output.
            filename = os.path.basename(input_path)
            filename_lower = filename.lower()
            if filename_lower.startswith("pre_w_"):
                wide_df.to_csv(output_path, index=False, encoding="utf-8")
                logger.debug("Successfully processed long-format weight file: %s", output_path)
                return  # Finished – skip the generic aggregation logic

            # Special-case: Accrued interest files don't need aggregation
            if "accrued" in filename_lower:
                wide_df.to_csv(output_path, index=False, encoding="utf-8")
                logger.debug("Successfully processed long-format accrued interest file: %s", output_path)
                return  # Finished – skip the generic aggregation logic

            # 5) For non-weight files, run aggregation logic to merge duplicate securities
            required_cols = [config.FUNDS_COL, config.SEC_NAME_COL]
            output_df = aggregate_data(wide_df, required_cols, logger, input_path)

            if output_df.empty:
                logger.warning(
                    f"No data rows processed for {input_path}. Output file will not be created."
                )
                return

            output_df.to_csv(output_path, index=False, encoding="utf-8")
            logger.debug("Successfully processed long-format file: %s", output_path)
            return  # Done – do *not* fall through to legacy logic

        # NEW BRANCH: Handle Key Rate Duration (KRD) files ---------------------
        # These files arrive in the following wide format already:
        #   ISIN, Date, 1M - KRD, 3M - KRD, 6M - KRD, 1Y - KRD, 2Y - KRD, 3Y - KRD, 4Y - KRD, 5Y - KRD, 7Y - KRD, 10Y - KRD, 20Y - KRD, 30Y - KRD, 50Y - KRD
        # We need to strip the " - KRD" suffix from the tenor columns and normalise the Date column.
        # The pre_* marker is simply stripped to create the output filename (handled by *run_preprocessing.py*).

        filename = os.path.basename(input_path)
        filename_lower = filename.lower()
        if filename_lower.startswith("pre_krd"):
            logger.debug("Detected KRD-format file – applying date normalisation and header cleanup.")

            if "Date" not in df.columns:
                logger.error("KRD file %s does not contain a 'Date' column. Skipping.", input_path)
                return

            # Robust date parsing: detect delimiter style to choose correct parsing
            try:
                sample_date_raw = df["Date"].dropna().iloc[0]
                if isinstance(sample_date_raw, str) and "/" in sample_date_raw:
                    # Likely in DD/MM/YYYY or MM/DD/YYYY – prefer dayfirst to correctly parse European format
                    parsed_dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
                    detected_format = 'slash-delimited with dayfirst=True'
                else:
                    # ISO-style or already YYYY-MM-DD
                    parsed_dates = pd.to_datetime(df["Date"], errors="coerce")
                    detected_format = 'ISO / dash-delimited'
                if parsed_dates.isna().all():
                    # Fallback to the other parsing method if everything failed
                    parsed_dates = pd.to_datetime(df["Date"], errors="coerce", dayfirst=not ("/" in str(sample_date_raw)))
                    detected_format += ' (fallback)'
                df["Date"] = parsed_dates.dt.strftime("%Y-%m-%d")
                failed_count = parsed_dates.isna().sum()
                if failed_count:
                    logger.warning(
                        f"{failed_count} rows in {input_path} had unparseable dates and were dropped during KRD preprocessing."
                    )
                df = df.dropna(subset=["Date"])
                logger.debug(
                    f"KRD date parsing: detected format: {detected_format}. "
                    f"Sample parsed dates: {df['Date'].head(5).tolist()}"
                )
            except Exception as exc:
                logger.error("Failed to parse Date column in %s: %s", input_path, exc)
                return

            # Robust KRD column renaming: handle 'KRD - 1M', '1M - KRD', etc.
            expected_tenors = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "20Y", "30Y", "50Y"]
            column_rename_map = {}
            for col in df.columns:
                # Match any column containing a tenor and 'KRD' (prefix or suffix)
                m = re.match(r"(?:KRD\s*-\s*)?(\d+[MY])(?:\s*-\s*KRD)?", col)
                if m and m.group(1) in expected_tenors:
                    column_rename_map[col] = m.group(1)
            logger.debug(f"KRD column rename map: {column_rename_map}")
            if column_rename_map:
                df = df.rename(columns=column_rename_map)
                logger.debug("Stripped KRD prefix/suffix from %d tenor columns", len(column_rename_map))
            # Ensure columns are in the expected order: ISIN, Date, then tenors in order
            base_cols = ["ISIN", "Date"]
            available_tenors = [t for t in expected_tenors if t in df.columns]
            final_column_order = base_cols + available_tenors
            logger.debug(f"Final KRD columns: {final_column_order}")
            df = df[final_column_order]
            df.to_csv(output_path, index=False, encoding="utf-8")
            logger.debug("Successfully processed KRD file: %s", output_path)
            return  # Finished – do not fall through to the generic logic

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
            logger.debug(f"Successfully processed weight file: {output_path}")
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
            # Normalize any date columns with time component (YYYY-MM-DDTHH:MM:SS -> YYYY-MM-DD)
            rename_map_timecols = {}
            date_with_time_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})T")
            for col in df.columns:
                m = date_with_time_pattern.match(col)
                if m:
                    rename_map_timecols[col] = m.group(1)
            if rename_map_timecols:
                df = df.rename(columns=rename_map_timecols)
                logger.debug(
                    "Stripped time component from %d date columns (e.g., %s -> %s)",
                    len(rename_map_timecols),
                    list(rename_map_timecols.keys())[0],
                    list(rename_map_timecols.values())[0],
                )
            df = replace_headers_with_dates(df, dates, metadata_cols)
            output_df = aggregate_data(df, required_cols, logger, input_path)
            if output_df.empty:
                logger.warning(
                    f"No data rows processed for {input_path}. Output file will not be created."
                )
                return
            output_df.to_csv(output_path, index=False, encoding="utf-8")
            logger.debug(f"Successfully processed file: {output_path}")
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
