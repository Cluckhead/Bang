# This script serves as a pre-processing step for specific CSV files within the 'Data' directory.
# It targets files prefixed with 'pre_', reads them, and performs data aggregation and cleaning.
# The core logic involves grouping rows based on identical values across most columns, excluding 'Funds' and 'Security Name'.
# For rows sharing the same 'Security Name' but differing in other data points, the 'Security Name' is suffixed
# (e.g., _1, _2) to ensure uniqueness. The 'Funds' associated with identical data rows are aggregated
# into a single list-like string representation (e.g., '[FUND1,FUND2]').
# The processed data is then saved to a new CSV file prefixed with 'new_'.

# process_data.py
# This script processes CSV files in the 'Data' directory that start with 'pre_'.
# It merges rows based on identical values in all columns except 'Funds'.
# Duplicated 'Security Name' entries with differing data are suffixed (_1, _2, etc.).
# The aggregated 'Funds' are stored as a list in the output file.

import os
import pandas as pd
import logging
# Add datetime for date parsing and sorting
from datetime import datetime

# --- Logging Setup ---
# Use the same log file as other data processing scripts
LOG_FILENAME = 'data_processing_errors.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Get the logger for the current module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        # Create log file path relative to this file's location (assuming it's in the project root)
        log_filepath = os.path.join(os.path.dirname(__file__), LOG_FILENAME) # If script is in root
        # If script is in a sub-directory, adjust path:
        # log_filepath = os.path.join(os.path.dirname(__file__), '..', LOG_FILENAME)
        fh = logging.FileHandler(log_filepath, mode='a')
        fh.setLevel(logging.WARNING)
        fh_formatter = logging.Formatter(LOG_FORMAT)
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)
    except Exception as e:
        # Log to stderr if file logging setup fails
        import sys
        print(f"Error setting up file logging for process_data: {e}", file=sys.stderr)
# --- End Logging Setup ---

# Define a constant for the dates file path
DATES_FILE_PATH = os.path.join('Data', 'dates.csv') # Define path to dates file

def read_and_sort_dates(dates_file):
    """
    Reads dates from a CSV file, sorts them, and returns them as a list of strings.

    Args:
        dates_file (str): Path to the CSV file containing dates (expected single column).

    Returns:
        list[str] | None: A sorted list of date strings (YYYY-MM-DD) or None if an error occurs.
    """
    try:
        dates_df = pd.read_csv(dates_file, parse_dates=[0]) # Assume date is the first column
        # Handle potential parsing errors if the column isn't purely dates
        if dates_df.iloc[:, 0].isnull().any():
             logger.warning(f"Warning: Some values in {dates_file} could not be parsed as dates.")
             # Attempt to drop NaT values and proceed
             dates_df = dates_df.dropna(subset=[dates_df.columns[0]])
             if dates_df.empty:
                 logger.error(f"Error: No valid dates found in {dates_file} after handling parsing issues.")
                 return None

        # Sort dates chronologically
        sorted_dates = dates_df.iloc[:, 0].sort_values()
        # Format dates as 'YYYY-MM-DD' strings for column headers
        date_strings = sorted_dates.dt.strftime('%Y-%m-%d').tolist()
        logger.info(f"Successfully read and sorted {len(date_strings)} dates from {dates_file}.")

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
            logger.warning(f"Duplicate dates found in {dates_file}. Using unique sorted dates: {len(unique_date_strings)} unique dates.")
        # --- End Deduplication ---

        return unique_date_strings # Return the deduplicated list
    except FileNotFoundError:
        logger.error(f"Error: Dates file not found at {dates_file}")
        return None
    except pd.errors.EmptyDataError:
        logger.error(f"Error: Dates file is empty - {dates_file}")
        return None
    except IndexError:
        logger.error(f"Error: Dates file {dates_file} seems to have no columns.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred reading dates from {dates_file}: {e}", exc_info=True)
        return None


# Modify process_csv_file signature to accept date_columns
def process_csv_file(input_path, output_path, date_columns):
    """
    Reads a 'pre_' CSV file, potentially replaces placeholder columns with dates,
    processes it according to the rules, and writes the result to a 'new_' CSV file.

    Args:
        input_path (str): Path to the input CSV file (e.g., 'Data/pre_sec_duration.csv').
        output_path (str): Path to the output CSV file (e.g., 'Data/new_sec_duration.csv').
        date_columns (list[str] | None): Sorted list of date strings for headers, or None if dates couldn't be read.
    """
    # If date_columns is None (due to error reading dates.csv), log and skip processing files needing date replacement.
    # We'll handle the actual replacement logic further down.
    if date_columns is None:
         logger.warning(f"Skipping {input_path} because date information is unavailable (check logs for errors reading dates.csv).")
         # A file might still be processable if its columns are *already* correct dates,
         # but the current logic requires date_columns for the check/replacement.
         # To proceed without dates.csv, the logic would need significant changes.
         return # Skip processing this file if dates aren't loaded.


    try:
        # Read the input CSV - add robustness
        # Skip bad lines, handle encoding errors
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        logger.info(f"Processing file: {input_path}")

        if df.empty:
            logger.warning(f"Input file {input_path} is empty or contains only invalid lines. Skipping processing.")
            return

        # --- Column Header Replacement Logic ---
        original_cols = df.columns.tolist()
        required_cols = ['Funds', 'Security Name'] # Core columns that should always exist
        # Ensure required columns are actually in the dataframe before proceeding
        if not all(col in original_cols for col in required_cols):
             missing = [col for col in required_cols if col not in original_cols]
             logger.error(f"Skipping {input_path}: Missing required columns: {missing}. Found columns: {original_cols}")
             return

        # Find the index after the last required column to start searching for placeholders
        # This assumes required columns appear early and together, adjust if needed.
        last_required_idx = -1
        for req_col in required_cols:
            try:
                last_required_idx = max(last_required_idx, original_cols.index(req_col))
            except ValueError: # Should not happen due to check above, but safeguard
                 logger.error(f"Required column '{req_col}' unexpectedly not found after initial check in {input_path}. Skipping.")
                 return

        candidate_start_index = last_required_idx + 1
        candidate_cols = original_cols[candidate_start_index:]

        # Decide on the final columns to use for processing
        current_cols = original_cols # Default to original columns

        # --- Enhanced Placeholder Detection ---
        # Detect sequences like 'Col', 'Col.1', 'Col.2', ...
        potential_placeholder_base = None
        placeholder_start_index_in_candidates = -1
        detected_sequence = []

        if not candidate_cols:
            logger.warning(f"File {input_path} has no columns after required columns '{required_cols}'. Cannot check for date placeholders.")
        else:
            # Iterate through candidate columns to find the *start* of the sequence
            found_sequence = False
            for start_idx in range(len(candidate_cols)):
                # Potential base is the column at start_idx
                current_potential_base = candidate_cols[start_idx]

                # Check if it's a potential base name (no '.' suffix)
                if '.' not in current_potential_base:
                    logger.debug(f"Checking potential base '{current_potential_base}' at index {start_idx} in candidate columns.")
                    # Found a potential start, now check for the sequence
                    potential_placeholder_base = current_potential_base
                    placeholder_start_index_in_candidates = start_idx
                    detected_sequence = [potential_placeholder_base] # Start sequence with the base

                    # Check subsequent columns for the pattern 'base.1', 'base.2', etc.
                    for i in range(1, len(candidate_cols) - start_idx):
                        expected_col = f"{potential_placeholder_base}.{i}"
                        actual_col_index = start_idx + i
                        if candidate_cols[actual_col_index] == expected_col:
                            detected_sequence.append(candidate_cols[actual_col_index])
                        else:
                            # Sequence broken
                            logger.debug(f"Sequence broken at index {actual_col_index}. Expected '{expected_col}', found '{candidate_cols[actual_col_index]}'.")
                            break # Stop checking for this base

                    # Check if a sequence of at least length 2 (Base, Base.1) was found
                    if len(detected_sequence) > 1:
                        logger.info(f"Found sequence starting with '{potential_placeholder_base}' at candidate index {placeholder_start_index_in_candidates}.")
                        found_sequence = True
                        break # Exit the outer loop, we found our sequence
                    else:
                        # Only the base was found, or sequence broke immediately. Reset and continue searching.
                        logger.debug(f"Only base '{potential_placeholder_base}' found or sequence too short. Continuing search.")
                        potential_placeholder_base = None
                        placeholder_start_index_in_candidates = -1
                        detected_sequence = []
                        # Continue the outer loop to check the next column as a potential base
                else:
                     logger.debug(f"Column '{current_potential_base}' at index {start_idx} has '.' suffix, skipping as potential base.")

            if not found_sequence:
                 logger.info(f"No placeholder sequence like 'Base', 'Base.1', ... found anywhere in candidate columns of {input_path}.")
                 potential_placeholder_base = None # Ensure it's None if no sequence found
                 detected_sequence = []


        # --- Date Replacement Logic using Detected Sequence ---
        if date_columns is None:
            logger.warning(f"Date information from {DATES_FILE_PATH} is unavailable. Cannot check or replace headers in {input_path}. Processing with original headers: {original_cols}")
        elif potential_placeholder_base is not None and detected_sequence:
            # A sequence like 'Base', 'Base.1', ... was detected
            placeholder_count = len(detected_sequence)
            original_placeholder_start_index = candidate_start_index + placeholder_start_index_in_candidates
            logger.info(f"Detected placeholder sequence based on '{potential_placeholder_base}' with {placeholder_count} columns, starting at index {original_placeholder_start_index} in original columns.")

            # Compare count with loaded dates
            if len(date_columns) == placeholder_count:
                logger.info(f"Replacing {placeholder_count} placeholder columns starting with '{potential_placeholder_base}' with dates.")
                # Construct new columns: Keep columns before sequence + dates + columns after sequence
                cols_before = original_cols[:original_placeholder_start_index]
                # Important: Calculate cols_after based on the *original* position and *count* of placeholders
                cols_after = original_cols[original_placeholder_start_index + placeholder_count:]
                new_columns = cols_before + date_columns + cols_after

                if len(new_columns) != len(original_cols):
                    logger.error(f"Internal error: Column count mismatch after constructing new columns ({len(new_columns)} vs {len(original_cols)}). Columns before: {cols_before}, Dates: {date_columns}, Columns after: {cols_after}. Reverting to original headers.")
                    current_cols = original_cols # Revert to original
                else:
                    df.columns = new_columns
                    current_cols = new_columns # Use the new columns for further processing
                    logger.info(f"Columns after replacement: {current_cols}")
            else:
                # Counts mismatch - log warning and proceed with original headers
                logger.warning(f"Placeholder count mismatch in {input_path}: Found sequence based on '{potential_placeholder_base}' with {placeholder_count} columns, but expected {len(date_columns)} dates based on {DATES_FILE_PATH}. Skipping date replacement. Processing with original headers.")
                # current_cols remains original_cols

        else:
            # No 'Base', 'Base.1', ... sequence found. Check if the candidate columns *already* match the date_columns.
            logger.info(f"No placeholder sequence like 'Base', 'Base.1', ... detected in {input_path}. Checking if existing columns match dates.")
            if candidate_cols == date_columns:
                 logger.info(f"Columns in {input_path} (after required ones) already match the expected dates. No replacement needed.")
                 # current_cols is already original_cols, which are correct.
            else:
                 # Log the mismatch if they don't match dates either
                 logger.warning(f"Columns in {input_path} do not match expected dates and no 'Base', 'Base.1', ... sequence found. Processing with original headers: {original_cols}")
                 # current_cols remains original_cols

        # --- End Column Header Replacement Logic ---


        # Identify columns to check for identity (all except Funds and Security Name) using the CURRENT columns
        # These might be the original placeholders or the replaced dates.
        # Crucially, this now correctly includes any original static columns that were *not* replaced.
        id_cols = [col for col in current_cols if col not in required_cols]

        processed_rows = []

        # Convert 'Security Name' and 'Funds' to string first to handle potential non-string types causing issues later
        df['Security Name'] = df['Security Name'].astype(str)
        df['Funds'] = df['Funds'].astype(str)

        # Group by the primary identifier 'Security Name'
        # Convert 'Security Name' to string first to handle potential non-string types causing groupby issues
        df['Security Name'] = df['Security Name'].astype(str)
        # Ensure 'Funds' is also string for consistent processing later
        df['Funds'] = df['Funds'].astype(str)

        # Use the potentially renamed DataFrame for grouping
        grouped_by_sec = df.groupby('Security Name', sort=False, dropna=False)

        for sec_name, sec_group in grouped_by_sec:
            # Within each security group, further group by all other identifying columns (which might now be dates)
            # This separates rows where the same Security Name has different associated data
            distinct_versions = []
            if id_cols: # Only subgroup if there are other identifying columns
                try:
                    # dropna=False treats NaNs in id_cols as equal for grouping
                    sub_grouped = sec_group.groupby(id_cols, dropna=False, sort=False)
                    distinct_versions = [group for _, group in sub_grouped]
                except KeyError as e:
                    logger.error(f"KeyError during sub-grouping for Security Name '{sec_name}' in {input_path}. Column: {e}. Grouping columns: {id_cols}. Skipping this security.", exc_info=True)
                    continue # Skip this security name if subgrouping fails
                except Exception as e:
                     logger.error(f"Unexpected error during sub-grouping for Security Name '{sec_name}' in {input_path}: {e}. Grouping columns: {id_cols}. Skipping this security.", exc_info=True)
                     continue
            else:
                # If only Security Name and Funds exist (after potential date column issues), treat the whole sec_group as one version
                 distinct_versions = [sec_group]

            num_versions = len(distinct_versions)

            # Iterate through each distinct version found for the current Security Name
            for i, current_version_df in enumerate(distinct_versions):
                if current_version_df.empty:
                    continue # Should not happen, but safeguard
                    
                # Aggregate the unique 'Funds' for this specific version
                # Handle potential NaN values in Funds column before aggregation
                unique_funds = current_version_df['Funds'].dropna().unique()
                # Convert funds to string before joining
                funds_list = sorted([str(f) for f in unique_funds])

                # Take the first row of this version as the template for the output row
                # Use .iloc[0] safely as we checked current_version_df is not empty
                new_row_series = current_version_df.iloc[0].copy()

                # Assign the aggregated funds as a string formatted like a list: "[FUND1,FUND2,...]"
                new_row_series['Funds'] = f"[{','.join(funds_list)}]"

                # If there was more than one distinct version for this Security Name, suffix the name
                if num_versions > 1:
                    # Ensure sec_name is a string before formatting
                    new_row_series['Security Name'] = f"{str(sec_name)}_{i+1}"
                # Else: keep the original Security Name (already stringified and set in new_row_series)

                # Append the processed row (as a dictionary) to our results list
                processed_rows.append(new_row_series.to_dict())

        if not processed_rows:
            logger.warning(f"No data rows processed for {input_path}. Output file will not be created.")
            # Changed behavior: Do not create an empty output file if no rows are processed.
            return
            # Create an empty DataFrame with original columns if no rows processed
            # output_df = pd.DataFrame(columns=original_cols)
        else:
             # Create the final DataFrame from the list of processed rows
            output_df = pd.DataFrame(processed_rows)
             # Ensure the column order reflects the potentially updated columns (current_cols)
             # Filter current_cols to only those present in output_df to avoid KeyErrors if a column was unexpectedly dropped
            final_cols = [col for col in current_cols if col in output_df.columns]
            output_df = output_df[final_cols]


        # Write the processed data to the new CSV file
        # The Funds column now contains comma-separated strings, which pandas will quote if necessary.
        output_df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully created: {output_path} with {len(output_df)} rows.")

    except FileNotFoundError:
        logger.error(f"Error: Input file not found - {input_path}")
    except pd.errors.EmptyDataError:
         logger.warning(f"Input file is empty or contains only header - {input_path}. Skipping.")
    except pd.errors.ParserError as pe:
        logger.error(f"Error parsing CSV file {input_path}: {pe}. Check file format and integrity.", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred processing {input_path}: {e}", exc_info=True)


def main():
    """
    Main function to find and process all 'pre_*.csv' files in the 'Data' directory.
    """
    # --- Read Dates ---
    # Define the path to the dates file
    dates_file_path = DATES_FILE_PATH # Use the constant defined at the top
    # Attempt to read and sort dates
    date_columns = read_and_sort_dates(dates_file_path)
    # If dates couldn't be read, date_columns will be None.
    # process_csv_file will handle this by skipping files.
    # Log message indicating status of date loading is handled within read_and_sort_dates.
    # --- End Read Dates ---

    input_dir = 'Data'
    input_prefix = 'pre_'
    # output_prefix = 'new_' #disabled
    output_prefix = ''

    if not os.path.isdir(input_dir):
        logger.error(f"Input directory '{input_dir}' not found.")
        return

    logger.info(f"Starting pre-processing scan in directory: '{input_dir}'")
    processed_count = 0
    skipped_count = 0
    # Iterate through all files in the specified directory
    for filename in os.listdir(input_dir):
        # Check if the file matches the pattern 'pre_*.csv'
        if filename.startswith(input_prefix) and filename.endswith('.csv'):
            input_file_path = os.path.join(input_dir, filename)
            # Construct the output filename by replacing 'pre_' with 'new_'
            output_filename = filename.replace(input_prefix, output_prefix, 1)
            output_file_path = os.path.join(input_dir, output_filename)

            # Process the individual CSV file
            try:
                # Pass the loaded date_columns to the processing function
                process_csv_file(input_file_path, output_file_path, date_columns)
                # Simple check if output exists might not be enough if process_csv_file skips creation
                # We rely on logs from process_csv_file to indicate success/failure/skip
                processed_count +=1 # Increment even if skipped internally, as we attempted it.
            except Exception as e:
                 # Catch any unexpected errors bubbling up from process_csv_file
                 logger.error(f"Unhandled exception processing {input_file_path} in main loop: {e}", exc_info=True)
                 skipped_count += 1
        else:
            # Optionally log files that don't match the pattern if needed for debugging
            # logger.debug(f"Skipping file '{filename}' as it does not match pattern 'pre_*.csv'")
            pass
            
    logger.info(f"Pre-processing scan finished. Attempted processing {processed_count} files. Encountered errors in {skipped_count} files during main loop (check logs for details).")

if __name__ == "__main__":
    # Ensure the script runs the main function when executed directly
    main() 