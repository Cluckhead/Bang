# This script serves as a pre-processing step for specific CSV files within the configured data directory.
# It targets files prefixed with 'pre_', reads them, and performs data aggregation and cleaning.
# The core logic involves grouping rows based on identical values across most columns, excluding 'Funds' and 'Security Name'.
# For rows sharing the same 'Security Name' but differing in other data points, the 'Security Name' is suffixed
# (e.g., _1, _2) to ensure uniqueness. The 'Funds' associated with identical data rows are aggregated
# into a single list-like string representation (e.g., '[FUND1,FUND2]').
# The processed data is then saved to a corresponding CSV file prefixed with 'sec_' (overwriting existing files)
# in the same data directory.
# It also processes a weight file (`w_Funds.csv`).
# The data directory is determined dynamically using `utils.get_data_folder_path`.

# process_data.py
# This script processes CSV files in the 'Data' directory that start with 'pre_'.
# It merges rows based on identical values in all columns except 'Funds'.
# Duplicated 'Security Name' entries with differing data are suffixed (_1, _2, etc.).
# The aggregated 'Funds' are stored as a list in the output file, saved as 'sec_*.csv'.

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

# --- Removed logging setup block --- 
# Logging is now handled centrally by the Flask app factory in app.py or by the script runner.

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
        dates_df = pd.read_csv(dates_file_path, parse_dates=[0]) # Assume date is the first column
        # Handle potential parsing errors if the column isn't purely dates
        if dates_df.iloc[:, 0].isnull().any():
             logger.warning(f"Warning: Some values in {dates_file_path} could not be parsed as dates.")
             # Attempt to drop NaT values and proceed
             dates_df = dates_df.dropna(subset=[dates_df.columns[0]])
             if dates_df.empty:
                 logger.error(f"Error: No valid dates found in {dates_file_path} after handling parsing issues.")
                 return None

        # Sort dates chronologically
        sorted_dates = dates_df.iloc[:, 0].sort_values()
        # Format dates as 'YYYY-MM-DD' strings for column headers
        date_strings = sorted_dates.dt.strftime('%Y-%m-%d').tolist()
        logger.info(f"Successfully read and sorted {len(date_strings)} dates from {dates_file_path}.")

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
            logger.warning(f"Duplicate dates found in {dates_file_path}. Using unique sorted dates: {len(unique_date_strings)} unique dates.")
        # --- End Deduplication ---

        return unique_date_strings # Return the deduplicated list
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
        logger.error(f"An unexpected error occurred reading dates from {dates_file_path}: {e}", exc_info=True)
        return None


# Modify process_csv_file signature to accept date_columns
def process_csv_file(input_path, output_path, date_columns):
    """
    Reads a 'pre_' CSV file, potentially replaces placeholder columns with dates,
    processes it according to the rules, and writes the result to a 'sec_' CSV file,
    overwriting if it exists.

    Args:
        input_path (str): Path to the input CSV file (e.g., 'Data/pre_sec_duration.csv').
        output_path (str): Path to the output CSV file (e.g., 'Data/sec_duration.csv').
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

        # Log DataFrame info right after reading (DEBUG level)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"DataFrame info after read for {input_path}:")
            buf = io.StringIO()
            df.info(verbose=True, buf=buf)
            logger.debug(buf.getvalue())

        if df.empty:
            logger.warning(f"Input file {input_path} is empty or contains only invalid lines. Skipping processing.")
            return

        # --- Column Header Replacement & Validation Logic ---
        original_cols = df.columns.tolist()

        # Define core columns, allowing for 'Fund' or 'Funds'
        fund_col_name = None
        if 'Funds' in original_cols:
            fund_col_name = 'Funds'
        elif 'Fund' in original_cols:
            fund_col_name = 'Fund'
            logger.info(f"Found 'Fund' column in {input_path}. Will rename to 'Funds' for processing.")
            # Rename the column IN PLACE for subsequent operations
            df.rename(columns={'Fund': 'Funds'}, inplace=True)
        else:
            logger.error(f"Skipping {input_path}: Missing required fund column (neither 'Funds' nor 'Fund' found). Found columns: {original_cols}")
            return

        # Now define required cols using the standardized 'Funds' name
        required_cols = ['Funds', 'Security Name']

        # Check for 'Security Name' (already checked for fund column)
        if 'Security Name' not in original_cols:
            logger.error(f"Skipping {input_path}: Missing required column 'Security Name'. Found columns: {original_cols}")
            return

        logger.debug(f"Required columns {required_cols} confirmed present (or renamed) in {input_path}.")

        # Find the index after the last required column to start searching for placeholders
        # Use the potentially renamed df.columns
        current_df_cols = df.columns.tolist()
        last_required_idx = -1
        for req_col in required_cols:
            try:
                last_required_idx = max(last_required_idx, current_df_cols.index(req_col))
            except ValueError: # Should not happen due to checks above, but safeguard
                 logger.error(f"Required column '{req_col}' unexpectedly not found after initial check/rename in {input_path}. Skipping.")
                 return

        candidate_start_index = last_required_idx + 1
        # Use current_df_cols which includes the renamed column if applicable
        candidate_cols = current_df_cols[candidate_start_index:]

        # Decide on the final columns to use for processing
        current_cols = current_df_cols # Default to current (potentially renamed) columns

        # --- Enhanced Placeholder Detection ---
        # Detect sequences like 'Col', 'Col.1', 'Col.2', ... (Pandas default)
        # AND sequences like 'Base', 'Base', 'Base', ... (Target for date replacement)
        potential_placeholder_base_patternA = None # For Base, Base.1, ...
        detected_sequence_patternA = []
        start_index_patternA = -1

        potential_placeholder_base_patternB = None # For Base, Base, Base, ...
        detected_sequence_patternB = []
        start_index_patternB = -1

        is_patternB_dominant = False # Flag if Pattern B is found and should trigger date replacement

        if not candidate_cols:
            logger.warning(f"File {input_path} has no columns after required columns {required_cols}. Cannot check for date placeholders.")
        else:
            # Check for Pattern B first: 'Base', 'Base', 'Base', ...
            first_candidate = candidate_cols[0]
            # Check if ALL candidate columns are identical to the first one
            if all(col == first_candidate for col in candidate_cols):
                potential_placeholder_base_patternB = first_candidate
                detected_sequence_patternB = candidate_cols
                start_index_patternB = 0 # Starts at the beginning of candidates
                logger.debug(f"Detected Pattern B: Repeated column name '{potential_placeholder_base_patternB}' for all {len(detected_sequence_patternB)} candidate columns.")
                # If we find Pattern B covering *all* candidates, we prioritize it for date replacement check
                is_patternB_dominant = True
            else:
                 logger.info(f"Candidate columns are not all identical (Pattern B check failed). First candidate: '{first_candidate}'. Candidates: {candidate_cols[:5]}...")
                 # If Pattern B check fails, proceed to check for Pattern A ('Base', 'Base.1', ...)
                 # Iterate through candidate columns to find the *start* of the sequence 'Base', 'Base.1', ...
                 found_sequence_A = False
                 for start_idx in range(len(candidate_cols)):
                     current_potential_base = candidate_cols[start_idx]
                     # Check if it's a potential base name (no '.' suffix)
                     if '.' not in current_potential_base:
                         logger.debug(f"Checking for Pattern A starting with '{current_potential_base}' at index {start_idx} in candidate columns.")
                         temp_sequence = [current_potential_base]
                         # Check subsequent columns for the pattern 'base.1', 'base.2', etc.
                         for i in range(1, len(candidate_cols) - start_idx):
                             expected_col = f"{current_potential_base}.{i}"
                             actual_col_index = start_idx + i
                             if candidate_cols[actual_col_index] == expected_col:
                                 temp_sequence.append(candidate_cols[actual_col_index])
                             else:
                                 logger.debug(f"Pattern A sequence broken at index {actual_col_index}. Expected '{expected_col}', found '{candidate_cols[actual_col_index]}'.")
                                 break # Stop checking for this base

                         if len(temp_sequence) > 1: # Found Base, Base.1 at minimum
                             potential_placeholder_base_patternA = current_potential_base
                             detected_sequence_patternA = temp_sequence
                             start_index_patternA = start_idx
                             logger.debug(f"Found Pattern A sequence starting with '{potential_placeholder_base_patternA}' at candidate index {start_index_patternA} with length {len(detected_sequence_patternA)}.")
                             found_sequence_A = True
                             break # Exit the outer loop for Pattern A search
                         else:
                             logger.debug(f"Only base '{current_potential_base}' found or Pattern A sequence too short. Continuing search.")
                             # Continue loop to check next candidate as potential base
                     else:
                         logger.debug(f"Column '{current_potential_base}' at index {start_idx} has '.' suffix, skipping as potential Pattern A base.")

                 if not found_sequence_A:
                     logger.info(f"No Pattern A sequence ('Base', 'Base.1', ...) found in candidate columns of {input_path}.")


        # --- Date Replacement Logic using Detected Patterns ---
        if date_columns is None:
            logger.warning(f"Date information from {dates_file_path} is unavailable. Cannot check or replace headers in {input_path}. Processing with original headers: {original_cols}")
        # --- Prioritize Pattern B for Date Replacement ---
        elif is_patternB_dominant:
             placeholder_count_B = len(detected_sequence_patternB)
             original_placeholder_start_index_B = candidate_start_index + start_index_patternB # Should be last_required_idx + 1
             logger.info(f"Processing based on detected Pattern B ('{potential_placeholder_base_patternB}' repeated {placeholder_count_B} times), starting at original index {original_placeholder_start_index_B}.")

             if len(date_columns) == placeholder_count_B:
                 logger.info(f"Replacing {placeholder_count_B} repeated '{potential_placeholder_base_patternB}' columns with dates.")
                 # Use current_cols here to respect potential prior rename ('Fund' -> 'Funds')
                 cols_before = current_cols[:original_placeholder_start_index_B]
                 cols_after = current_cols[original_placeholder_start_index_B + placeholder_count_B:]
                 new_columns = cols_before + date_columns + cols_after
 
                 if len(new_columns) != len(current_cols): # Compare against current_cols length
                     logger.error(f"Internal error (Pattern B): Column count mismatch after constructing new columns ({len(new_columns)} vs {len(current_cols)}). Reverting to original headers.")
                     # Revert logic might need refinement, but for now, keep current_cols as is.
                     # current_cols = original_cols # Reverting might lose the 'Fund'->'Funds' rename
                 else:
                     df.columns = new_columns
                     current_cols = new_columns
                     logger.info(f"Columns after Pattern B date replacement: {current_cols}")
             else:
                 logger.warning(f"Count mismatch for Pattern B in {input_path}: Found {placeholder_count_B} repeated '{potential_placeholder_base_patternB}' columns, but expected {len(date_columns)} dates. Skipping date replacement. Processing with original headers.")
                 # current_cols remains potentially renamed cols

        # --- Handle Pattern A or No Pattern ---
        # No Pattern B found, or it didn't match date count. Check Pattern A or if columns already match dates.
        else:
             if potential_placeholder_base_patternA:
                 # Pattern A ('Base', 'Base.1', ...) was found.
                 placeholder_count_A = len(detected_sequence_patternA)
                 original_placeholder_start_index_A = candidate_start_index + start_index_patternA
                 logger.debug(f"Detected Pattern A sequence based on '{potential_placeholder_base_patternA}' (length {placeholder_count_A}) starting at original index {original_placeholder_start_index_A}.")
 
                 # --- Attempt Date Replacement for Pattern A if lengths match ---
                 if len(date_columns) == placeholder_count_A:
                     logger.info(f"Replacing {placeholder_count_A} Pattern A columns ('{potential_placeholder_base_patternA}', '{potential_placeholder_base_patternA}.1', ...) with dates.")
                     # Use current_cols here to respect potential prior rename ('Fund' -> 'Funds')
                     cols_before = current_cols[:original_placeholder_start_index_A]
                     cols_after = current_cols[original_placeholder_start_index_A + placeholder_count_A:]
                     new_columns = cols_before + date_columns + cols_after
 
                     if len(new_columns) != len(current_cols): # Compare against current_cols length
                         logger.error(f"Internal error (Pattern A): Column count mismatch after constructing new columns ({len(new_columns)} vs {len(current_cols)}). Reverting to original headers.")
                         # Keep current_cols as is to avoid losing potential rename
                         # current_cols = original_cols
                     else:
                         df.columns = new_columns
                         current_cols = new_columns
                         logger.info(f"Columns after Pattern A date replacement using {len(date_columns)} dates for {input_path}.")
                 else:
                     # Lengths don't match, log warning and proceed with original (Pattern A) headers
                     logger.warning(f"Count mismatch for Pattern A in {input_path}: Found {placeholder_count_A} columns in sequence ('{potential_placeholder_base_patternA}', '{potential_placeholder_base_patternA}.1', ...), but expected {len(date_columns)} dates. Skipping date replacement. Processing with original headers.")
                     # current_cols remains potentially renamed cols
                 # --- End Date Replacement Logic for Pattern A ---

             elif candidate_cols == date_columns:
                 # No patterns found, but candidates already match dates
                 logger.debug(f"Columns in {input_path} (after required ones) already match the expected dates. No replacement needed.")

        # --- End Column Header Replacement Logic ---


        # Identify columns to check for identity (all except Funds and Security Name) using the CURRENT columns
        # These might be the original placeholders or the replaced dates.
        # Crucially, this now correctly includes any original static columns that were *not* replaced.
        id_cols = [col for col in current_cols if col not in required_cols]

        processed_rows = []

        # Convert 'Security Name' and 'Funds' to string first to handle potential non-string types causing issues later
        # Use 'Funds' as it has been standardized by rename operation if necessary
        df['Security Name'] = df['Security Name'].astype(str)
        df['Funds'] = df['Funds'].astype(str)

        # Group by the primary identifier 'Security Name'
        # Convert 'Security Name' to string first to handle potential non-string types causing groupby issues
        # df['Security Name'] = df['Security Name'].astype(str) # Already done above
        # Ensure 'Funds' is also string for consistent processing later
        # df['Funds'] = df['Funds'].astype(str) # Already done above

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

        # Fill NaN values with 0 before saving
        output_df = output_df.fillna(0)

        # Log DataFrame info just before saving (DEBUG level)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Output DataFrame info before save for {output_path} (after NaN fill):")
            buf = io.StringIO()
            output_df.info(verbose=True, buf=buf)
            logger.debug(buf.getvalue())

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
    """Main execution function to find and process 'pre_' files and the weight file."""
    logger.info("--- Starting pre-processing script --- ")

    # Determine the root path for this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Use the utility to get the configured absolute data folder path
    # Pass the script's directory as the base for resolving relative paths if necessary
    input_dir = get_data_folder_path(app_root_path=script_dir)
    logger.info(f"Using data directory: {input_dir}")

    if not os.path.isdir(input_dir):
        logger.error(f"Data directory not found or is not a directory: {input_dir}. Cannot proceed.")
        return

    # Construct absolute path for dates.csv
    dates_file_path = os.path.join(input_dir, 'dates.csv')

    # Read and prepare date columns
    date_columns = read_and_sort_dates(dates_file_path)
    if date_columns is None:
        logger.warning("Could not read or process dates.csv. Files requiring date replacement might be skipped or processed incorrectly.")
        # Continue processing other files that might not need date replacement, but log the warning.

    # Find files starting with 'pre_' in the determined data directory
    processed_count = 0
    skipped_count = 0
    for filename in os.listdir(input_dir):
        # Skip non-CSV files and the specific weight files which are handled separately
        if not filename.endswith('.csv') or filename.startswith('pre_w_'):
            if filename.startswith('pre_w_'):
                logger.debug(f"Skipping {filename} in main loop, will be handled by weight processor.")
            continue # Skip this file in the main loop

        if filename.startswith('pre_') and filename.endswith('.csv'):
            input_path = os.path.join(input_dir, filename)
            # Create the output filename by replacing 'pre_' with '' (e.g., sec_duration.csv)
            output_filename = filename.replace('pre_', '', 1)
            output_path = os.path.join(input_dir, output_filename)
            
            logger.info(f"Found file to process: {input_path} -> {output_path} (will overwrite)")
            try:
                process_csv_file(input_path, output_path, date_columns)
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing file {input_path}: {e}", exc_info=True)
                skipped_count += 1
        
    logger.info(f"Finished processing general 'pre_' files. Processed: {processed_count}, Skipped due to errors: {skipped_count}")

    # --- Process the specific weight files using weight_processing --- 
    weight_files_to_process = {
        'pre_w_fund.csv': 'w_Funds.csv',
        'pre_w_bench.csv': 'w_Bench.csv',
        'pre_w_secs.csv': 'w_secs.csv'
    }

    for input_fname, output_fname in weight_files_to_process.items():
        weight_input_path = os.path.join(input_dir, input_fname)
        weight_output_path = os.path.join(input_dir, output_fname)

        if os.path.exists(weight_input_path):
            logger.info(f"Processing weight file: {weight_input_path} -> {weight_output_path}")
            try:
                # Pass the absolute input, output paths, and the absolute dates_path
                process_weight_file(weight_input_path, weight_output_path, dates_file_path)
            except Exception as e:
                logger.error(f"Error processing weight file {weight_input_path}: {e}", exc_info=True)
        else:
            logger.warning(f"Weight input file not found: {weight_input_path}. Skipping processing for {output_fname}.")

    logger.info("--- Pre-processing script finished --- ")


if __name__ == "__main__":
    main() 