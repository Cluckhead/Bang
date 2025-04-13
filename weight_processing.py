# weight_processing.py
# This script provides functionality to process weight files (e.g., w_Funds.csv).
# It reads a weight file, identifies the relevant columns, and saves the processed data
# to a specified output path. It replaces duplicate headers with dates from Dates.csv.

import pandas as pd
import logging
import os
import io
import re
from collections import Counter

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

def clean_date_format(dates):
    """
    Clean up date format by removing time components and ensuring consistent YYYY-MM-DD format.
    
    Args:
        dates (list): List of date strings or values to clean
        
    Returns:
        list: List of cleaned date strings in YYYY-MM-DD format
    """
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
                
    return cleaned_dates

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
            
            # Clean up date formats to remove time components
            dates = clean_date_format(dates)
            logger.info(f"Cleaned up date formats to remove time components")
            
        except Exception as e:
            logger.error(f"Error loading dates from {dates_path}: {e}")
            return

        # Read the input CSV - add robustness
        input_basename = os.path.basename(input_path).lower()
        
        # Special handling for different file types based on filename
        if "w_funds" in input_basename or "w_bench" in input_basename:
            # For funds and bench files, we know they have a simple structure:
            # First column is fund code, all others are weight columns to be replaced with dates
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            
            if df.empty:
                logger.warning(f"Weight file {input_path} is empty. Skipping.")
                return
                
            # Get original column names
            original_cols = df.columns.tolist()
            
            # First column remains the same (Fund Code)
            id_col = original_cols[0]
            
            # All other columns become dates
            data_cols = original_cols[1:]
            
            if len(data_cols) > len(dates):
                logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                dates = dates[:len(data_cols)]
            elif len(data_cols) < len(dates):
                logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                dates = dates[:len(data_cols)]
                
            # Create new column list
            new_columns = [id_col] + dates
            
            # Rename columns
            df.columns = new_columns
            logger.info(f"Replaced {len(data_cols)} weight columns with dates")
            
        elif "w_secs" in input_basename:
            # For securities file, we need to handle potential metadata columns
            # Read the file but skip header normalization
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            
            if df.empty:
                logger.warning(f"Weight file {input_path} is empty. Skipping.")
                return
                
            # Get original column names
            original_cols = df.columns.tolist()
            
            # For securities, we assume:
            # - First column is always the ID column (ISIN)
            # - Fixed number of metadata columns (e.g., up to column X)
            # - The rest are date columns that need replacing
            
            # Identify metadata vs data columns
            # Determine if any columns look like repeated weight/value columns
            # For simplicity, we'll assume a pattern like "Weight", "Price", etc. repeats
            value_patterns = ["weight", "price", "value", "duration"]
            
            # Count columns that match common patterns
            pattern_counts = {}
            for col in original_cols:
                col_lower = col.lower()
                for pattern in value_patterns:
                    if pattern in col_lower:
                        if pattern not in pattern_counts:
                            pattern_counts[pattern] = 0
                        pattern_counts[pattern] += 1
                        
            # Find the most common pattern
            most_common_pattern = None
            max_count = 0
            for pattern, count in pattern_counts.items():
                if count > max_count:
                    max_count = count
                    most_common_pattern = pattern
                    
            if most_common_pattern and max_count > 1:
                logger.info(f"Found repeated pattern '{most_common_pattern}' {max_count} times in {input_path}")
                
                # Create list of columns to replace (those matching the pattern)
                replace_indices = []
                for i, col in enumerate(original_cols):
                    if most_common_pattern in col.lower():
                        replace_indices.append(i)
                        
                # Ensure we don't try to use more dates than we have
                if len(replace_indices) > len(dates):
                    logger.warning(f"Not enough dates ({len(dates)}) for all pattern columns ({len(replace_indices)}). Using available dates only.")
                    dates = dates[:len(replace_indices)]
                elif len(replace_indices) < len(dates):
                    logger.warning(f"More dates ({len(dates)}) than pattern columns ({len(replace_indices)}). Using first {len(replace_indices)} dates.")
                    dates = dates[:len(replace_indices)]
                    
                # Replace columns matching the pattern with dates
                new_columns = original_cols.copy()
                for i, idx in enumerate(replace_indices):
                    if i < len(dates):
                        new_columns[idx] = dates[i]
                
                # Rename columns
                df.columns = new_columns
                logger.info(f"Replaced {len(replace_indices)} columns matching '{most_common_pattern}' with dates")
            else:
                # Fallback: use the simpler approach of taking first column as ID, rest as dates
                logger.warning(f"No clear pattern found in {input_path}. Using default approach (first column = ID, rest = dates).")
                
                id_col = original_cols[0]
                data_cols = original_cols[1:]
                
                if len(data_cols) > len(dates):
                    logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                    dates = dates[:len(data_cols)]
                elif len(data_cols) < len(dates):
                    logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                    dates = dates[:len(data_cols)]
                    
                new_columns = [id_col] + dates
                df.columns = new_columns
                logger.info(f"Replaced {len(data_cols)} columns with dates")
        else:
            # Default handling for unknown files
            logger.warning(f"Unknown file type: {input_path}. Using default handling.")
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            
            # Assume first column is ID, rest are dates
            original_cols = df.columns.tolist()
            id_col = original_cols[0]
            data_cols = original_cols[1:]
            
            if len(data_cols) > len(dates):
                logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                dates = dates[:len(data_cols)]
            elif len(data_cols) < len(dates):
                logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                dates = dates[:len(data_cols)]
                
            new_columns = [id_col] + dates
            df.columns = new_columns
            logger.info(f"Replaced all columns after the first with dates")

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
    except PermissionError as pe:
        logger.error(f"Permission error saving to {output_path}: {pe}. Ensure the file is not open in another program.", exc_info=True)
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