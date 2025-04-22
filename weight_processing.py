# weight_processing.py
# This script provides functionality to process weight files (e.g., w_Funds.csv, w_Bench.csv, w_secs.csv).
# It reads a weight file, identifies the relevant columns (including dynamic metadata detection for w_secs.csv),
# sorts date columns chronologically, and saves the processed data to a specified output path.
# It replaces duplicate headers with dates from Dates.csv. All paths should be absolute.

import pandas as pd
import logging
import os
import io
import re
from collections import Counter
from typing import List, Optional

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

def detect_metadata_columns(df: pd.DataFrame, min_numeric_cols: int = 3) -> int:
    """
    Dynamically detect the number of metadata columns in a DataFrame by finding the first column
    where at least `min_numeric_cols` subsequent columns are numeric (likely date columns).
    Returns the index (int) of the last metadata column (exclusive for slicing).
    """
    for i in range(1, len(df.columns)):
        numeric_count = 0
        for j in range(i, min(i + min_numeric_cols, len(df.columns))):
            sample = df.iloc[:, j].dropna().head(10)
            if sample.apply(lambda x: pd.api.types.is_number(x) or pd.api.types.is_float(x) or pd.api.types.is_integer(x)).all():
                numeric_count += 1
        if numeric_count == min_numeric_cols:
            return i  # metadata columns are up to i-1
    return 1  # fallback: only first column is metadata

def process_weight_file(input_path: str, output_path: str, dates_path: Optional[str] = None):
    """
    Reads a weight CSV file (w_Funds.csv, w_Bench.csv, w_secs.csv), replaces duplicate headers with dates from Dates.csv,
    sorts date columns chronologically, and saves it to the specified output path. Handles dynamic metadata detection for w_secs.csv.

    Args:
        input_path (str): Absolute path to the input weight CSV file (e.g., w_Funds.csv).
        output_path (str): Absolute path where the processed weight file should be saved.
        dates_path (str, optional): Path to the Dates.csv file. If None, will look in the same directory as the input file.
    """
    try:
        # Find the folder containing the input file to look for Dates.csv if not provided
        if dates_path is None:
            input_dir = os.path.dirname(input_path)
            dates_path = os.path.join(input_dir, 'Dates.csv')
        # Check if Dates.csv exists
        if not os.path.exists(dates_path):
            logger.error(f"Dates.csv not found at {dates_path}. Cannot replace headers.")
            return
        # Read and sort dates
        try:
            dates_df = pd.read_csv(dates_path)
            dates_df['Date'] = pd.to_datetime(dates_df['Date'], errors='coerce')
            dates_df = dates_df.dropna(subset=['Date'])
            dates_df = dates_df.sort_values(by='Date')
            sorted_dates = dates_df['Date'].tolist()
            logger.info(f"Loaded {len(sorted_dates)} dates from {dates_path}")
            dates = clean_date_format(sorted_dates)
            logger.info(f"Cleaned up date formats to remove time components")
        except FileNotFoundError:
            logger.error(f"Dates file not found: {dates_path}")
            return
        except pd.errors.EmptyDataError:
            logger.warning(f"Dates file is empty: {dates_path}")
            return
        except pd.errors.ParserError as e:
            logger.error(f"Parser error in dates file {dates_path}: {e}", exc_info=True)
            return
        except Exception as e:
            logger.error(f"Unexpected error loading dates from {dates_path}: {e}", exc_info=True)
            return
        input_basename = os.path.basename(input_path).lower()

        if "w_funds" in input_basename or "w_bench" in input_basename:
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            if df.empty:
                logger.warning(f"Weight file {input_path} is empty. Skipping.")
                return
            original_cols = df.columns.tolist()
            id_col = original_cols[0]
            data_cols = original_cols[1:]
            if len(data_cols) > len(dates):
                logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                # Truncate data columns to match the number of dates
                keep_cols = [id_col] + data_cols[:len(dates)]
                df = df[keep_cols]
                data_cols = data_cols[:len(dates)]
                # Now len(data_cols) == len(dates)
                dates = dates[:len(data_cols)]
            elif len(data_cols) < len(dates):
                logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                dates = dates[:len(data_cols)]
            new_columns = [id_col] + dates
            df.columns = new_columns
            logger.info(f"Replaced {len(data_cols)} weight columns with dates")

        elif "w_secs" in input_basename:
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            if df.empty:
                logger.warning(f"Weight file {input_path} is empty. Skipping.")
                return
            original_cols = df.columns.tolist()
            # Dynamically detect metadata columns
            meta_end_idx = detect_metadata_columns(df)
            id_col = original_cols[0]
            metadata_cols = original_cols[:meta_end_idx]
            data_cols = original_cols[meta_end_idx:]
            if len(data_cols) > len(dates):
                logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                # Truncate data columns to match the number of dates
                keep_cols = metadata_cols + data_cols[:len(dates)]
                df = df[keep_cols]
                data_cols = data_cols[:len(dates)]
                dates = dates[:len(data_cols)]
            elif len(data_cols) < len(dates):
                logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                dates = dates[:len(data_cols)]
            new_columns = metadata_cols + dates
            df.columns = new_columns
            logger.info(f"Replaced {len(data_cols)} data columns with dates after {len(metadata_cols)} metadata columns")

        else:
            logger.warning(f"Unknown file type: {input_path}. Using default handling.")
            df = pd.read_csv(input_path, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
            original_cols = df.columns.tolist()
            id_col = original_cols[0]
            data_cols = original_cols[1:]
            if len(data_cols) > len(dates):
                logger.warning(f"Not enough dates ({len(dates)}) for all data columns ({len(data_cols)}). Using available dates only.")
                # Truncate data columns to match the number of dates
                keep_cols = [id_col] + data_cols[:len(dates)]
                df = df[keep_cols]
                data_cols = data_cols[:len(dates)]
                dates = dates[:len(data_cols)]
            elif len(data_cols) < len(dates):
                logger.warning(f"More dates ({len(dates)}) than data columns ({len(data_cols)}). Using first {len(data_cols)} dates.")
                dates = dates[:len(data_cols)]
            new_columns = [id_col] + dates
            df.columns = new_columns
            logger.info(f"Replaced all columns after the first with dates")

        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully processed and saved weight file to: {output_path}")

    except FileNotFoundError:
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