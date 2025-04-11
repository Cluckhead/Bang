# weight_processing.py
# This script provides functionality to process weight files (w_Funds.csv, w_Bench.csv).
# It replaces placeholder column headers (like 'Port Weight' or 'Bench Weight') with actual dates
# read from an external dates file, if the counts match. The file is then overwritten with the updated headers.

import pandas as pd
import logging
import os
import io

# Use the same log file as other data processing scripts
LOG_FILENAME = 'data_processing_errors.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Get the logger for the current module
logger = logging.getLogger(__name__)
# Explicitly configure logger if not already configured by importer (like process_data)
if not logger.handlers:
    logger.setLevel(logging.DEBUG) # Set level to DEBUG to allow debug messages

    # Console Handler (INFO and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO) # Log INFO and higher to console
    ch_formatter = logging.Formatter(LOG_FORMAT)
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    # File Handler (WARNING and above)
    try:
        # Ensure log file path is correct relative to this script's location
        log_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_FILENAME)
        fh = logging.FileHandler(log_filepath, mode='a')
        fh.setLevel(logging.WARNING) # Log WARNING and higher to file
        fh_formatter = logging.Formatter(LOG_FORMAT)
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)
    except Exception as e:
        # Fallback to console logging if file handler fails
        logger.error(f"Failed to set up file logging for weight_processing: {e}", exc_info=True)


def process_weight_file(input_path, date_columns):
    """
    Reads a weight CSV file (e.g., w_Funds.csv), replaces placeholder weight columns
    with dates if counts match, and overwrites the original file.

    Args:
        input_path (str): Path to the input weight CSV file.
        date_columns (list[str]): Sorted list of date strings ('YYYY-MM-DD') for headers.
    """
    if not os.path.exists(input_path):
        logger.error(f"Weight file not found: {input_path}. Skipping.")
        return
    if not date_columns:
        logger.warning(f"No date columns provided for {input_path}. Cannot replace headers. Skipping.")
        return

    try:
        # Read the input CSV - add robustness
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        logger.info(f"Processing weight file: {input_path}")

        # Log DataFrame info at DEBUG level
        buf = io.StringIO()
        df.info(verbose=True, buf=buf)
        logger.debug(f"DataFrame info after read for {input_path}:\n{buf.getvalue()}")

        if df.empty:
            logger.warning(f"Weight file {input_path} is empty or contains only invalid lines. Skipping processing.")
            return

        original_cols = df.columns.tolist()

        # Identify the key identifier column (e.g., 'Fund Code')
        # Assuming it's the first column for simplicity, but could be made more robust
        if not original_cols:
             logger.error(f"Weight file {input_path} seems to have no columns. Skipping.")
             return
        id_col = original_cols[0]
        logger.debug(f"Identified ID column: '{id_col}'")

        # Identify the weight columns (all columns after the first one)
        weight_cols = original_cols[1:]
        if not weight_cols:
            logger.warning(f"Weight file {input_path} has an ID column ('{id_col}') but no subsequent weight columns. Skipping header replacement.")
            return

        # --- Detect Header Pattern --- Detect Base, Base.1, Base.2 pattern ---
        base_col_name = None
        detected_sequence = []
        if weight_cols:
            first_weight_col = weight_cols[0]
            # Check if it looks like a base name (no '.' suffix added by pandas)
            if '.' not in first_weight_col:
                base_col_name = first_weight_col
                detected_sequence.append(base_col_name)
                # Check subsequent columns for the pattern Base.1, Base.2 etc.
                for i in range(1, len(weight_cols)):
                    expected_col = f"{base_col_name}.{i}"
                    if weight_cols[i] == expected_col:
                        detected_sequence.append(expected_col)
                    else:
                        # Pattern broken, might be a mix or just short sequence
                        logger.debug(f"Pattern '{base_col_name}.{i}' broken at index {i+1} in {input_path}. Found '{weight_cols[i]}'")
                        break
            else:
                # First weight column already has a suffix, maybe Base.1? This logic doesn't handle that start case.
                logger.warning(f"First weight column '{first_weight_col}' in {input_path} already contains '.'. Cannot determine base name for pattern check.")

        if not base_col_name or len(detected_sequence) < 2: # Need at least Base and Base.1
            logger.warning(f"Could not detect a clear 'Base, Base.1, ...' pattern in weight columns for {input_path}. First few: {weight_cols[:5]}. Skipping header replacement.")
            return
        # --- End Pattern Detection ---

        logger.info(f"Detected pattern starting with '{base_col_name}'. Sequence length: {len(detected_sequence)} in {input_path}.")

        # Compare counts
        num_pattern_cols = len(detected_sequence)
        num_date_cols = len(date_columns)

        # Check if the *entire* set of weight columns matches the detected pattern length
        if num_pattern_cols != len(weight_cols):
             logger.warning(f"Detected pattern sequence length ({num_pattern_cols}) does not match total number of weight columns ({len(weight_cols)}) in {input_path}. Headers might be mixed. Skipping replacement.")
             return

        # Now compare the matched pattern length with date count
        if num_pattern_cols == num_date_cols:
            logger.info(f"Count match ({num_date_cols} dates). Replacing headers in {input_path}.")
            new_columns = [id_col] + date_columns
            df.columns = new_columns

            # Overwrite the original file with the new headers
            try:
                df.to_csv(input_path, index=False, encoding='utf-8')
                logger.info(f"Successfully updated headers and overwritten: {input_path}")
            except Exception as write_e:
                logger.error(f"Error writing updated headers back to {input_path}: {write_e}", exc_info=True)
                # Consider reverting df.columns here if needed, though the in-memory change is already done.
        else:
            logger.warning(f"Count mismatch in {input_path}: Found pattern sequence of length {num_pattern_cols} (based on '{base_col_name}'), but have {num_date_cols} dates. Headers will NOT be replaced.")

    except FileNotFoundError:
        # This case is handled by the initial check, but included for completeness
        logger.error(f"Error: Input weight file not found - {input_path}")
    except pd.errors.EmptyDataError:
         logger.warning(f"Weight file is empty or contains only header - {input_path}. Skipping.")
    except pd.errors.ParserError as pe:
        logger.error(f"Error parsing CSV weight file {input_path}: {pe}. Check file format and integrity.", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred processing weight file {input_path}: {e}", exc_info=True)

# Example of how to potentially call this (e.g., from process_data.py or for testing)
# if __name__ == "__main__":
#    # This part would typically run inside process_data.py's main function
#    DATES_FILE_PATH = os.path.join('Data', 'dates.csv')
#    from process_data import read_and_sort_dates # Assuming process_data.py is accessible
#    dates = read_and_sort_dates(DATES_FILE_PATH)
#    if dates:
#        process_weight_file(os.path.join('Data', 'w_Funds.csv'), dates)
#        process_weight_file(os.path.join('Data', 'w_Bench.csv'), dates)
#    else:
#        print("Could not read dates, skipping weight file processing.") 