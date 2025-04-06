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

def process_csv_file(input_path, output_path):
    """
    Reads a 'pre_' CSV file, processes it according to the rules,
    and writes the result to a 'new_' CSV file.

    Args:
        input_path (str): Path to the input CSV file (e.g., 'Data/pre_sec_duration.csv').
        output_path (str): Path to the output CSV file (e.g., 'Data/new_sec_duration.csv').
    """
    try:
        # Read the input CSV - add robustness
        # Skip bad lines, handle encoding errors
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        logger.info(f"Processing file: {input_path}")

        if df.empty:
            logger.warning(f"Input file {input_path} is empty or contains only invalid lines. Skipping processing.")
            # Optionally create an empty output file or just skip
            # Let's skip creating an output file if input is empty/invalid
            return

        # Ensure required columns are present
        original_cols = df.columns.tolist()
        required_cols = ['Funds', 'Security Name']
        if not all(col in original_cols for col in required_cols):
             missing = [col for col in required_cols if col not in original_cols]
             logger.error(f"Skipping {input_path}: Missing required columns: {missing}. Found: {original_cols}")
             return

        # Identify columns to check for identity (all except Funds and Security Name)
        id_cols = [col for col in original_cols if col not in ['Security Name', 'Funds']]

        processed_rows = []

        # Fill NaN values with a placeholder string for grouping purposes, as pandas groupby drops NaN keys by default
        # We use dropna=False in groupby now, but filling might be safer for complex types if needed later
        # df_filled = df.fillna("__NAN_PLACEHOLDER__") # Consider implications if "__NAN_PLACEHOLDER__" is real data
        # Use original df and rely on dropna=False in groupby

        # Group by the primary identifier 'Security Name'
        # Convert 'Security Name' to string first to handle potential non-string types causing groupby issues
        df['Security Name'] = df['Security Name'].astype(str)
        grouped_by_sec = df.groupby('Security Name', sort=False, dropna=False)

        for sec_name, sec_group in grouped_by_sec:
            # Within each security group, further group by all other identifying columns
            # This separates rows where the same Security Name has different associated data
            distinct_versions = []
            if id_cols: # Only subgroup if there are other identifying columns
                try:
                    # dropna=False treats NaNs in id_cols as equal for grouping
                    sub_grouped = sec_group.groupby(id_cols, dropna=False, sort=False)
                    distinct_versions = [group for _, group in sub_grouped]
                except KeyError as e:
                    logger.error(f"KeyError during sub-grouping for Security Name '{sec_name}' in {input_path}. Column: {e}. Skipping this security.", exc_info=True)
                    continue # Skip this security name if subgrouping fails
                except Exception as e:
                     logger.error(f"Unexpected error during sub-grouping for Security Name '{sec_name}' in {input_path}: {e}. Skipping this security.", exc_info=True)
                     continue
            else:
                # If only Security Name and Funds exist, treat the whole sec_group as one version
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
             # Ensure the column order matches the original input file
             # Filter original_cols to only those present in output_df to avoid KeyErrors
            final_cols = [col for col in original_cols if col in output_df.columns]
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
    input_dir = 'Data'
    input_prefix = 'pre_'
    output_prefix = 'new_'

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
                process_csv_file(input_file_path, output_file_path)
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