# This script serves as a pre-processing step for specific CSV files within the configured data directory.
# It targets files prefixed with 'pre_', reads them, and performs data aggregation and cleaning.
# The core logic involves grouping rows based on identical values across most columns, excluding 'Funds', 'Security Name', and potentially 'ISIN'.
# For rows sharing the same 'Security Name' but differing in other data points, the script attempts to find
# an 'ISIN' column and suffixes its value (e.g., -1, -2) to ensure uniqueness for downstream processing.
# The 'Funds' associated with identical data rows are aggregated into a single list-like string representation (e.g., '[FUND1,FUND2]').
# The processed data is then saved to a corresponding CSV file prefixed with 'sec_' (overwriting existing files)
# in the same data directory.
# It also processes weight files (`pre_w_*.csv`).
# The data directory is determined dynamically using `utils.get_data_folder_path`.

# process_data.py
# This script processes CSV files in the 'Data' directory that start with 'pre_'.
# It merges rows based on identical values in most columns (excluding 'Funds', 'Security Name', potentially 'ISIN').
# If multiple data versions exist for the same 'Security Name', it suffixes the 'ISIN' column value (-1, -2, etc.).
# The aggregated 'Funds' are stored as a list-like string in the output file, saved as 'sec_*.csv'.

import os
import pandas as pd
import logging

# Add datetime for date parsing and sorting
from datetime import datetime
import io

# Import the new weight processing function
from weight_processing import process_weight_file

# Import the path utility
from utils import get_data_folder_path

# Get the logger instance. Assumes logging is configured elsewhere (e.g., by Flask app or calling script).
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# Removed DATES_FILE_PATH constant - path is now determined dynamically in main()


def read_and_sort_dates(dates_file_path):
    """
    Reads dates from a CSV file, sorts them, and returns them as a list of strings.

    Args:
        dates_file_path (str): Absolute path to the CSV file containing dates.

    Returns:
        list[str] | None: A sorted list of date strings (YYYY-MM-DD) or None if an error occurs.
    """
    if not dates_file_path:
        logger.error("No dates_file_path provided to read_and_sort_dates.")
        return None
    if not os.path.exists(dates_file_path):
        logger.error(f"Dates file not found at {dates_file_path}")
        return None

    try:
        dates_df = pd.read_csv(
            dates_file_path, parse_dates=[0]
        )  # Assume date is the first column
        # Handle potential parsing errors if the column isn't purely dates
        if dates_df.iloc[:, 0].isnull().any():
            logger.warning(
                f"Warning: Some values in {dates_file_path} could not be parsed as dates."
            )
            # Attempt to drop NaT values and proceed
            dates_df = dates_df.dropna(subset=[dates_df.columns[0]])
            if dates_df.empty:
                logger.error(
                    f"Error: No valid dates found in {dates_file_path} after handling parsing issues."
                )
                return None

        # Sort dates chronologically
        sorted_dates = dates_df.iloc[:, 0].sort_values()
        # Format dates as 'YYYY-MM-DD' strings for column headers
        date_strings = sorted_dates.dt.strftime("%Y-%m-%d").tolist()
        logger.info(
            f"Successfully read and sorted {len(date_strings)} dates from {dates_file_path}."
        )

        # --- Deduplicate the date list while preserving order ---
        unique_date_strings = []
        seen_dates = set()
        duplicates_found = False
        for date_str in date_strings:
            if date_str not in seen_dates:
                unique_date_strings.append(date_str)
                seen_dates.add(date_str)
            else:
                duplicates_found = True

        if duplicates_found:
            logger.warning(
                f"Duplicate dates found in {dates_file_path}. Using unique sorted dates: {len(unique_date_strings)} unique dates."
            )
        # --- End Deduplication ---

        return unique_date_strings  # Return the deduplicated list
    except FileNotFoundError:
        # This case should ideally be caught by the initial os.path.exists check, but included for robustness
        logger.error(f"Error: Dates file not found at {dates_file_path}")
        return None
    except pd.errors.EmptyDataError:
        logger.error(f"Error: Dates file is empty - {dates_file_path}")
        return None
    except IndexError:
        logger.error(f"Error: Dates file {dates_file_path} seems to have no columns.")
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred reading dates from {dates_file_path}: {e}",
            exc_info=True,
        )
        return None


def replace_headers_with_dates(
    df: pd.DataFrame,
    required_cols: list,
    candidate_start_index: int,
    candidate_cols: list,
    date_columns: list,
    dates_file_path: str,
    logger: logging.Logger,
    input_path: str,
) -> pd.DataFrame:
    """
    Helper to detect placeholder columns and replace them with date columns if needed.
    Returns a DataFrame with updated headers.
    """
    current_cols = df.columns.tolist()
    # --- Enhanced Placeholder Detection ---
    # Detect sequences like 'Col', 'Col.1', ... (Pattern A) and 'Base', 'Base', ... (Pattern B)
    potential_placeholder_base_patternA = None
    detected_sequence_patternA = []
    start_index_patternA = -1
    potential_placeholder_base_patternB = None
    detected_sequence_patternB = []
    start_index_patternB = -1
    is_patternB_dominant = False
    if candidate_cols:
        first_candidate = candidate_cols[0]
        if all(col == first_candidate for col in candidate_cols):
            potential_placeholder_base_patternB = first_candidate
            detected_sequence_patternB = candidate_cols
            start_index_patternB = 0
            logger.debug(
                f"Detected Pattern B: Repeated column name '{potential_placeholder_base_patternB}' for all {len(detected_sequence_patternB)} candidate columns."
            )
            is_patternB_dominant = True
        else:
            for start_idx in range(len(candidate_cols)):
                current_potential_base = candidate_cols[start_idx]
                if "." not in current_potential_base:
                    temp_sequence = [current_potential_base]
                    for i in range(1, len(candidate_cols) - start_idx):
                        expected_col = f"{current_potential_base}.{i}"
                        actual_col_index = start_idx + i
                        if candidate_cols[actual_col_index] == expected_col:
                            temp_sequence.append(candidate_cols[actual_col_index])
                        else:
                            break
                    if len(temp_sequence) > 1:
                        potential_placeholder_base_patternA = current_potential_base
                        detected_sequence_patternA = temp_sequence
                        start_index_patternA = start_idx
                        break
    # --- Date Replacement Logic ---
    if date_columns is None:
        logger.warning(
            f"Date information from {dates_file_path} is unavailable. Cannot check or replace headers in {input_path}. Processing with original headers: {current_cols}"
        )
        return df
    elif is_patternB_dominant:
        placeholder_count_B = len(detected_sequence_patternB)
        original_placeholder_start_index_B = (
            candidate_start_index + start_index_patternB
        )
        if len(date_columns) == placeholder_count_B:
            cols_before = current_cols[:original_placeholder_start_index_B]
            cols_after = current_cols[
                original_placeholder_start_index_B + placeholder_count_B :
            ]
            new_columns = cols_before + date_columns + cols_after
            if len(new_columns) == len(current_cols):
                df.columns = new_columns
                logger.info(
                    f"Replaced {placeholder_count_B} repeated '{potential_placeholder_base_patternB}' columns with dates."
                )
            else:
                logger.error(
                    f"Internal error (Pattern B): Column count mismatch after constructing new columns. Keeping original headers."
                )
        else:
            logger.warning(
                f"Count mismatch for Pattern B: Found {placeholder_count_B} repeated '{potential_placeholder_base_patternB}' columns, but expected {len(date_columns)} dates. Skipping date replacement."
            )
    elif potential_placeholder_base_patternA:
        placeholder_count_A = len(detected_sequence_patternA)
        original_placeholder_start_index_A = (
            candidate_start_index + start_index_patternA
        )
        if len(date_columns) == placeholder_count_A:
            cols_before = current_cols[:original_placeholder_start_index_A]
            cols_after = current_cols[
                original_placeholder_start_index_A + placeholder_count_A :
            ]
            new_columns = cols_before + date_columns + cols_after
            if len(new_columns) == len(current_cols):
                df.columns = new_columns
                logger.info(
                    f"Replaced {placeholder_count_A} Pattern A columns ('{potential_placeholder_base_patternA}', '{potential_placeholder_base_patternA}.1', ...) with dates."
                )
            else:
                logger.error(
                    f"Internal error (Pattern A): Column count mismatch after constructing new columns. Keeping original headers."
                )
        else:
            logger.warning(
                f"Count mismatch for Pattern A: Found {placeholder_count_A} columns in sequence ('{potential_placeholder_base_patternA}', '{potential_placeholder_base_patternA}.1', ...), but expected {len(date_columns)} dates. Skipping date replacement."
            )
    elif candidate_cols == date_columns:
        logger.debug(
            f"Columns after required ones already match the expected dates. No replacement needed."
        )
    return df


def aggregate_data(
    df: pd.DataFrame, required_cols: list, logger: logging.Logger, input_path: str
) -> pd.DataFrame:
    """
    Helper to aggregate/group data as per project rules (group by Security Name, merge Funds, suffix ISIN).
    Returns a processed DataFrame ready for output.
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
                logger.error(
                    f"Error during sub-grouping for Security Name '{sec_name}' in {input_path}: {e}. Skipping this security.",
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
                isin_col_name = "ISIN"
                if isin_col_name in new_row_series.index:
                    original_isin = new_row_series[isin_col_name]
                    new_isin = f"{str(original_isin)}-{i+1}"
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


# Refactored process_csv_file


def process_csv_file(input_path, output_path, date_columns, dates_file_path):
    """
    Processes a CSV file, handling errors robustly.
    """
    try:
        df = pd.read_csv(
            input_path, on_bad_lines="skip", encoding="utf-8", encoding_errors="replace"
        )
        logger.info(f"Processing file: {input_path}")
        if df.empty:
            logger.warning(
                f"Input file {input_path} is empty or contains only invalid lines. Skipping processing."
            )
            return
        original_cols = df.columns.tolist()
        fund_col_name = None
        if "Funds" in original_cols:
            fund_col_name = "Funds"
        elif "Fund" in original_cols:
            fund_col_name = "Fund"
            logger.info(
                f"Found 'Fund' column in {input_path}. Will rename to 'Funds' for processing."
            )
            df.rename(columns={"Fund": "Funds"}, inplace=True)
        else:
            logger.error(
                f"Skipping {input_path}: Missing required fund column (neither 'Funds' nor 'Fund' found). Found columns: {original_cols}"
            )
            return
        required_cols = ["Funds", "Security Name"]
        if "Security Name" not in original_cols:
            logger.error(
                f"Skipping {input_path}: Missing required column 'Security Name'. Found columns: {original_cols}"
            )
            return
        current_df_cols = df.columns.tolist()
        last_required_idx = -1
        for req_col in required_cols:
            try:
                last_required_idx = max(
                    last_required_idx, current_df_cols.index(req_col)
                )
            except ValueError:
                logger.error(
                    f"Required column '{req_col}' unexpectedly not found after initial check/rename in {input_path}. Skipping."
                )
                return
        candidate_start_index = last_required_idx + 1
        candidate_cols = current_df_cols[candidate_start_index:]
        # Step 1: Header replacement
        df = replace_headers_with_dates(
            df,
            required_cols,
            candidate_start_index,
            candidate_cols,
            date_columns,
            dates_file_path,
            logger,
            input_path,
        )
        # Step 2: Data aggregation
        output_df = aggregate_data(df, required_cols, logger, input_path)
        if output_df.empty:
            logger.warning(
                f"No data rows processed for {input_path}. Output file will not be created."
            )
            return
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Output DataFrame info before save for {output_path} (after NaN fill):"
            )
            buf = io.StringIO()
            output_df.info(verbose=True, buf=buf)
            logger.debug(buf.getvalue())
        output_df.to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"Successfully created: {output_path} with {len(output_df)} rows.")
    except FileNotFoundError:
        logger.error(f"Error: Input file not found - {input_path}")
    except pd.errors.EmptyDataError:
        logger.warning(
            f"Input file is empty or contains only header - {input_path}. Skipping."
        )
    except pd.errors.ParserError as pe:
        logger.error(
            f"Error parsing CSV file {input_path}: {pe}. Check file format and integrity.",
            exc_info=True,
        )
    except PermissionError:
        logger.error(f"Permission denied when writing to {output_path}", exc_info=True)
    except OSError as e:
        logger.error(f"OS error when writing to {output_path}: {e}", exc_info=True)
    except Exception as e:
        logger.error(
            f"An unexpected error occurred processing {input_path}: {e}", exc_info=True
        )


def main():
    """Main execution function to find and process 'pre_' files and the weight file."""
    logger.info("--- Starting pre-processing script --- ")

    # Determine the root path for this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Use the utility to get the configured absolute data folder path
    # Pass the script's directory as the base for resolving relative paths if necessary
    input_dir = get_data_folder_path(app_root_path=script_dir)
    logger.info(f"Using data directory: {input_dir}")

    if not os.path.isdir(input_dir):
        logger.error(
            f"Data directory not found or is not a directory: {input_dir}. Cannot proceed."
        )
        return

    # Construct absolute path for dates.csv
    dates_file_path = os.path.join(input_dir, "dates.csv")

    # Read and prepare date columns
    date_columns = read_and_sort_dates(dates_file_path)
    if date_columns is None:
        logger.warning(
            "Could not read or process dates.csv. Files requiring date replacement might be skipped or processed incorrectly."
        )
        # Continue processing other files that might not need date replacement, but log the warning.

    # Find files starting with 'pre_' in the determined data directory
    processed_count = 0
    skipped_count = 0
    for filename in os.listdir(input_dir):
        # Skip non-CSV files and the specific weight files which are handled separately
        if not filename.endswith(".csv") or filename.startswith("pre_w_"):
            if filename.startswith("pre_w_"):
                logger.debug(
                    f"Skipping {filename} in main loop, will be handled by weight processor."
                )
            continue  # Skip this file in the main loop

        if filename.startswith("pre_") and filename.endswith(".csv"):
            input_path = os.path.join(input_dir, filename)
            # Create the output filename by replacing 'pre_' with '' (e.g., sec_duration.csv)
            output_filename = filename.replace("pre_", "", 1)
            output_path = os.path.join(input_dir, output_filename)

            logger.info(
                f"Found file to process: {input_path} -> {output_path} (will overwrite)"
            )
            try:
                # Pass dates_file_path to the function
                process_csv_file(input_path, output_path, date_columns, dates_file_path)
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing file {input_path}: {e}", exc_info=True)
                skipped_count += 1

    logger.info(
        f"Finished processing general 'pre_' files. Processed: {processed_count}, Skipped due to errors: {skipped_count}"
    )

    # --- Process the specific weight files using weight_processing ---
    weight_files_to_process = {
        "pre_w_fund.csv": "w_Funds.csv",
        "pre_w_bench.csv": "w_Bench.csv",
        "pre_w_secs.csv": "w_secs.csv",
    }

    for input_fname, output_fname in weight_files_to_process.items():
        weight_input_path = os.path.join(input_dir, input_fname)
        weight_output_path = os.path.join(input_dir, output_fname)

        if os.path.exists(weight_input_path):
            logger.info(
                f"Processing weight file: {weight_input_path} -> {weight_output_path}"
            )
            try:
                # Pass the absolute input, output paths, and the absolute dates_path
                process_weight_file(
                    weight_input_path, weight_output_path, dates_file_path
                )
            except Exception as e:
                logger.error(
                    f"Error processing weight file {weight_input_path}: {e}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"Weight input file not found: {weight_input_path}. Skipping processing for {output_fname}."
            )

    logger.info("--- Pre-processing script finished --- ")


if __name__ == "__main__":
    main()
