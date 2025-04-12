# weight_processing.py
# This script provides functionality to process weight files (e.g., w_Funds.csv).
# It reads a weight file, identifies the relevant columns, and saves the processed data
# to a specified output path. (Original header replacement logic is removed as per the
# simplification in process_data.py's call).

import pandas as pd
import logging
import os
import io

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

def process_weight_file(input_path: str, output_path: str):
    """
    Reads a weight CSV file, performs necessary processing (if any), and saves
    it to the specified output path.

    Currently, this function primarily copies the file, assuming pre-processing
    (like header replacement) might happen elsewhere or is not needed for weights.
    Add specific weight processing logic here if required in the future.

    Args:
        input_path (str): Absolute path to the input weight CSV file (e.g., w_Funds.csv).
        output_path (str): Absolute path where the processed weight file should be saved.
    """
    if not os.path.exists(input_path):
        logger.error(f"Weight file not found: {input_path}. Skipping processing.")
        return

    logger.info(f"Processing weight file: {input_path} -> {output_path}")

    try:
        # Read the input CSV - add robustness
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')

        # Log DataFrame info at DEBUG level
        buf = io.StringIO()
        df.info(verbose=True, buf=buf)
        logger.debug(f"DataFrame info after read for {input_path}:\n{buf.getvalue()}")

        if df.empty:
            logger.warning(f"Weight file {input_path} is empty or contains only invalid lines. Saving empty file to {output_path}.")
            # Save an empty file or a file with just headers, depending on desired behavior
            df.to_csv(output_path, index=False, encoding='utf-8')
            return

        # --- Placeholder for future weight-specific processing --- 
        # Example: Rename columns, calculate new metrics, filter rows, etc.
        # df['NewWeight'] = df['SomeWeight'] * 100 
        # logger.info(f"Applied custom processing to weight data from {input_path}.")
        # --- End Placeholder --- 

        # Save the processed DataFrame to the output path
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully processed and saved weight file to: {output_path}")

    except FileNotFoundError:
        # This case is handled by the initial check, but included for completeness
        logger.error(f"Error: Input weight file not found during processing - {input_path}")
    except pd.errors.EmptyDataError:
         logger.warning(f"Weight file is empty - {input_path}. Skipping save.")
    except pd.errors.ParserError as pe:
        logger.error(f"Error parsing CSV weight file {input_path}: {pe}. Check file format and integrity.", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred processing weight file {input_path} to {output_path}: {e}", exc_info=True)


# Example usage note:
# This script is typically called by process_data.py, which provides
# the absolute input and output paths derived from the configured data directory.
# Standalone execution would require manual path specification.
#
# Example (for understanding, not direct execution without setup):
# if __name__ == "__main__":
#    # Requires manual setup of paths if run standalone
#    test_input_dir = '/path/to/your/data' # Replace with actual path
#    test_input_file = os.path.join(test_input_dir, 'w_Funds.csv')
#    test_output_file = os.path.join(test_input_dir, 'w_Funds_Processed.csv')
#
#    if os.path.exists(test_input_file):
#        print(f"Testing weight processing: {test_input_file} -> {test_output_file}")
#        process_weight_file(test_input_file, test_output_file)
#    else:
#        print(f"Test input file not found: {test_input_file}")