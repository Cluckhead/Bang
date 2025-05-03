# Purpose: This script serves as a pre-processing step for specific CSV files within the configured data directory, handling grouping, aggregation, and header normalization for downstream security-level analysis.
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
import config

# Add datetime for date parsing and sorting
from datetime import datetime
import io

# Import the new weight processing function
from weight_processing import process_weight_file

# Import the path utility
from utils import get_data_folder_path

# Bring in shared preprocessing helpers
from preprocessing import (
    read_and_sort_dates,
    aggregate_data,
    replace_headers_with_dates,
)  # unified helper

# Get the logger instance. Assumes logging is configured elsewhere (e.g., by Flask app or calling script).
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# Removed DATES_FILE_PATH constant - path is now determined dynamically in main()


def suffix_isin(isin: str, n: int) -> str:
    """Return a suffixed ISIN using the pattern from config."""
    return config.ISIN_SUFFIX_PATTERN.format(isin=isin, n=n)


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
        if config.FUNDS_COL in original_cols:
            fund_col_name = config.FUNDS_COL
        elif config.FUND_CODE_COL in original_cols:
            fund_col_name = config.FUND_CODE_COL
            logger.info(
                f"Found '{config.FUND_CODE_COL}' column in {input_path}. Will rename to '{config.FUNDS_COL}' for processing."
            )
            df.rename(columns={config.FUND_CODE_COL: config.FUNDS_COL}, inplace=True)
        else:
            logger.error(
                f"Skipping {input_path}: Missing required fund column (neither '{config.FUNDS_COL}' nor '{config.FUND_CODE_COL}' found). Found columns: {original_cols}"
            )
            return
        required_cols = [config.FUNDS_COL, config.SEC_NAME_COL]
        if config.SEC_NAME_COL not in original_cols:
            logger.error(
                f"Skipping {input_path}: Missing required column '{config.SEC_NAME_COL}'. Found columns: {original_cols}"
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
        metadata_cols = current_df_cols[:candidate_start_index]
        # Step 1: Header replacement (new helper)
        df = replace_headers_with_dates(df, date_columns, metadata_cols)
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
        logger.error(f"Error: Input file not found - {input_path}", exc_info=True)
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
            f"An unexpected error occurred processing {input_path}: {e}",
            exc_info=True,
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
