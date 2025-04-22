# process_weights.py
# Purpose: Processes weight files in a specified data folder (data_folder_path) rather than a hardcoded path. Handles pre_w_Bench.csv, pre_w_Funds.csv, and pre_w_secs.csv to produce w_Bench.csv, w_Funds.csv, and w_secs.csv.

import os
import logging
import pandas as pd
import re
from weight_processing import process_weight_file

# Logging is now handled centrally by the Flask app factory in app.py
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

def process_securities_file(input_path, output_path, dates_path):
    """
    Special processing for the securities weight file (pre_w_secs.csv).
    This file has a different structure with multiple metadata columns.
    
    Args:
        input_path (str): Path to the pre_w_secs.csv file
        output_path (str): Path where to save the processed w_secs.csv file
        dates_path (str): Path to the Dates.csv file with dates to use for headers
    """
    logger.info(f"Processing securities weight file: {input_path} -> {output_path}")
    
    try:
        # Read the securities file
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        
        if df.empty:
            logger.warning(f"Securities file {input_path} is empty. Skipping.")
            return
            
        # Get original column names
        original_cols = df.columns.tolist()
        
        # Assuming securities file structure:
        # - First column is ISIN (or ID)
        # - There are several metadata columns (like security name, fund code, etc.)
        # - The remaining columns are weight values that need date headers
        
        # Identify metadata columns (keep first 10 columns as metadata)
        metadata_cols = original_cols[:10]  # Adjust this number if needed
        logger.info(f"Keeping these metadata columns: {metadata_cols}")
        
        # The rest are weight columns to replace with dates
        weight_cols = original_cols[10:]
        logger.info(f"Found {len(weight_cols)} weight columns to replace with dates")
        
        # Load dates
        try:
            dates_df = pd.read_csv(dates_path)
            dates = dates_df['Date'].tolist()
            logger.info(f"Loaded {len(dates)} dates from {dates_path}")
            
            # Clean up dates by removing any time component if present
            cleaned_dates = []
            for date in dates:
                # Remove time component if it exists (T00:00:00 format)
                if isinstance(date, str) and 'T' in date:
                    cleaned_date = date.split('T')[0]
                    cleaned_dates.append(cleaned_date)
                else:
                    # If date is in datetime format, convert to string in YYYY-MM-DD format
                    try:
                        if pd.notnull(date):
                            date_obj = pd.to_datetime(date)
                            cleaned_dates.append(date_obj.strftime('%Y-%m-%d'))
                        else:
                            cleaned_dates.append(date)
                    except:
                        cleaned_dates.append(date)
                     
            logger.info(f"Cleaned up date formats to remove time components")
            dates = cleaned_dates
            
        except Exception as e:
            logger.error(f"Error loading dates from {dates_path}: {e}")
            return
            
        # Check if we have enough dates for all weight columns
        if len(weight_cols) > len(dates):
            logger.warning(f"Not enough dates ({len(dates)}) for all weight columns ({len(weight_cols)}). Using available dates only.")
            dates = dates[:len(weight_cols)]
        elif len(weight_cols) < len(dates):
            logger.warning(f"More dates ({len(dates)}) than weight columns ({len(weight_cols)}). Using first {len(weight_cols)} dates.")
            dates = dates[:len(weight_cols)]
        
        # Reverse the dates list so newest dates appear on the right
        dates = dates[::-1]
        logger.info(f"Reversed dates order, newest date will be on the right")
            
        # Create new column names with metadata columns and dates
        new_columns = metadata_cols + dates
        
        # Rename the columns
        df.columns = new_columns
        logger.info(f"Replaced {len(weight_cols)} weight columns with dates")
        
        # Save the processed DataFrame to the output path
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully processed and saved securities file to: {output_path}")
        
    except Exception as e:
        logger.error(f"Error processing securities file {input_path}: {e}", exc_info=True)

def process_weight_file_with_reversed_dates(input_path, output_path, dates_path):
    """
    A wrapper around process_weight_file that reverses the dates order.
    This ensures dates are ordered with newest on the right.
    
    Args:
        input_path (str): Path to the input weight file
        output_path (str): Path where to save the processed weight file
        dates_path (str): Path to the Dates.csv file
    """
    logger.info(f"Processing weight file with reversed dates: {input_path} -> {output_path}")
    
    try:
        # Load dates
        dates_df = pd.read_csv(dates_path)
        dates = dates_df['Date'].tolist()
        
        # Clean up dates by removing any time component if present
        cleaned_dates = []
        for date in dates:
            # Remove time component if it exists (T00:00:00 format)
            if isinstance(date, str) and 'T' in date:
                cleaned_date = date.split('T')[0]
                cleaned_dates.append(cleaned_date)
            else:
                # If date is in datetime format, convert to string in YYYY-MM-DD format
                try:
                    if pd.notnull(date):
                        date_obj = pd.to_datetime(date)
                        cleaned_dates.append(date_obj.strftime('%Y-%m-%d'))
                    else:
                        cleaned_dates.append(date)
                except:
                    cleaned_dates.append(date)
                 
        logger.info(f"Cleaned up date formats to remove time components")
        dates = cleaned_dates
        
        # Read the input file
        df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        
        if df.empty:
            logger.warning(f"Weight file {input_path} is empty. Skipping.")
            return
            
        # Get original column names
        original_cols = df.columns.tolist()
        
        # First column remains as is (Fund Code)
        id_col = original_cols[0]
        
        # All other columns become dates
        data_cols = original_cols[1:]
        
        if len(data_cols) > len(dates):
            logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
            dates = dates[:len(data_cols)]
        elif len(data_cols) < len(dates):
            logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
            dates = dates[:len(data_cols)]
            
        # Reverse the dates list so newest dates appear on the right side
        dates = dates[::-1]
        logger.info(f"Reversed dates order, newest date will be on the right")
            
        # Create new column names
        new_columns = [id_col] + dates
        
        # Rename the columns
        df.columns = new_columns
        
        # Save the processed DataFrame
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully processed and saved weight file to: {output_path}")
        
    except Exception as e:
        logger.error(f"Error processing weight file {input_path}: {e}", exc_info=True)

def main(data_folder_path=None):
    """Process all weight files in the specified data directory."""
    # If no data_folder_path is provided, use the current behavior
    if data_folder_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_folder_path = os.path.join(current_dir, 'Data')

    # Path to Dates.csv
    dates_path = os.path.join(data_folder_path, 'Dates.csv')

    if not os.path.exists(dates_path):
        logger.error(f"Dates.csv not found at {dates_path}. Cannot proceed.")
        return

    # Process fund and bench weight files
    weight_files = [
        ('pre_w_Bench.csv', 'w_Bench.csv'),
        ('pre_w_Funds.csv', 'w_Funds.csv')
    ]

    # Process each weight file
    for input_file, output_file in weight_files:
        input_path = os.path.join(data_folder_path, input_file)
        output_path = os.path.join(data_folder_path, output_file)

        if os.path.exists(input_path):
            logger.info(f"Processing weight file: {input_path} -> {output_path}")
            process_weight_file_with_reversed_dates(input_path, output_path, dates_path)
        else:
            logger.warning(f"Input file not found: {input_path}")

    # Special handling for securities file
    secs_input_path = os.path.join(data_folder_path, 'pre_w_secs.csv')
    secs_output_path = os.path.join(data_folder_path, 'w_secs.csv')

    if os.path.exists(secs_input_path):
        process_securities_file(secs_input_path, secs_output_path, dates_path)
    else:
        logger.warning(f"Securities file not found: {secs_input_path}")

if __name__ == "__main__":
    main() 