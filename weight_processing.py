# weight_processing.py
# This script provides functionality to process weight files (e.g., w_Funds.csv).
# It reads a weight file, identifies the relevant columns, and saves the processed data
# to a specified output path. It replaces duplicate column headers with dates from Dates.csv.

import pandas as pd
import logging
import os
import io

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

def process_weight_file(input_path: str, output_path: str, dates_path: str = None):
    """
    Reads a weight CSV file, replaces duplicate headers with dates from Dates.csv,
    and saves it to the specified output path.

    Args:
        input_path (str): Absolute path to the input weight CSV file (e.g., w_Funds.csv).
        output_path (str): Absolute path where the processed weight file should be saved.
        dates_path (str): Optional path to the Dates.csv file. If None, will look in the same
                          directory as the input file.
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

        # Find the folder containing the input file to look for Dates.csv if not provided
        if dates_path is None:
            input_dir = os.path.dirname(input_path)
            dates_path = os.path.join(input_dir, 'Dates.csv')

        # Check if Dates.csv exists
        if not os.path.exists(dates_path):
            logger.error(f"Dates.csv not found at {dates_path}. Cannot replace headers.")
            return

        # Read dates
        try:
            dates_df = pd.read_csv(dates_path)
            dates = dates_df['Date'].tolist()
            logger.info(f"Loaded {len(dates)} dates from {dates_path}")
        except Exception as e:
            logger.error(f"Error loading dates from {dates_path}: {e}")
            return

        # Get original column names
        original_cols = df.columns.tolist()
        
        # Identify the fund column (should be first column)
        fund_col = original_cols[0]  # Assume first column is fund column
        logger.info(f"Using '{fund_col}' as the fund identifier column")

        # Get data columns (all except the first)
        data_cols = original_cols[1:]
        
        # Check if we have enough dates for all data columns
        if len(data_cols) > len(dates):
            logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
            dates = dates[:len(data_cols)]
        elif len(data_cols) < len(dates):
            logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
            dates = dates[:len(data_cols)]

        # Create new column names with the fund column and dates
        new_columns = [fund_col] + dates
        
        # Rename the columns
        df.columns = new_columns
        logger.info(f"Replaced duplicate headers with {len(dates)} dates from Dates.csv")

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


# Example usage:
# if __name__ == "__main__":
#    # Paths are relative to the workspace
#    data_dir = "Data"
#    input_file = os.path.join(data_dir, 'pre_w_Funds.csv')
#    output_file = os.path.join(data_dir, 'w_Funds.csv')
#    dates_file = os.path.join(data_dir, 'Dates.csv')
#
#    if os.path.exists(input_file):
#        print(f"Processing weight file: {input_file} -> {output_file}")
#        process_weight_file(input_file, output_file, dates_file)
#    else:
#        print(f"Input file not found: {input_file}")