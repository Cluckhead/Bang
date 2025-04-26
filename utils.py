# This file contains utility functions used throughout the Simple Data Checker application.
# These functions provide common helper functionalities like parsing specific string formats
# or validating data types, helping to keep the main application logic cleaner.

"""
Utility functions for the Flask application.
"""
import re
import pandas as pd
import os
import logging
from pathlib import Path # Added pathlib
from flask import current_app # Added current_app
import numpy as np
import csv

# Configure logging
# Removed basicConfig - logging is now configured centrally in app.py
# logger = logging.getLogger(__name__) # Get logger for this module

DEFAULT_RELATIVE_PATH = 'Data'

def _is_date_like(column_name):
    """Check if a column name looks like a date (e.g., YYYY-MM-DD or DD/MM/YYYY).
    Updated regex to match various formats and not require matching the entire string.
    Also handles cases where column name might not be a string.
    """
    if not isinstance(column_name, str):
        return False
    
    # Match common date formats potentially within column names
    # Loosened the regex to not require start/end anchors (^$)
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
        r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
        r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
        # Add more specific patterns if needed, e.g., for time
        # r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' # YYYY-MM-DDTHH:MM:SS
    ]
    
    # Return True if any pattern is found within the string
    return any(re.search(pattern, column_name) for pattern in date_patterns)

def parse_fund_list(fund_string):
    """Safely parses the fund list string like '[FUND1,FUND2]' or '[FUND1]' into a list.
       Handles potential errors and variations in spacing.
    """
    if not isinstance(fund_string, str) or not fund_string.startswith('[') or not fund_string.endswith(']'):
        return [] # Return empty list if format is unexpected
    try:
        # Remove brackets and split by comma
        content = fund_string[1:-1]
        # Split by comma, strip whitespace from each element
        funds = [f.strip() for f in content.split(',') if f.strip()]
        return funds
    except Exception as e:
        # Use logger if available, otherwise print
        logger = logging.getLogger(__name__)
        logger.error(f"Error parsing fund string '{fund_string}': {e}")
        return []

def get_data_folder_path(app_root_path=None):
    """
    Retrieves the data folder path, prioritizing config.py, then a default.

    Resolves the path to an absolute path relative to the provided
    app_root_path or the current working directory.

    Args:
        app_root_path (str, optional): The root path of the application or script.
                                      If None, os.getcwd() is used. Defaults to None.

    Returns:
        str: The absolute path to the data folder.
    """
    logger = logging.getLogger(__name__) # Use logger
    chosen_path_source = f"default ('{DEFAULT_RELATIVE_PATH}')"
    chosen_path = DEFAULT_RELATIVE_PATH

    try:
        # Attempt to import the path from config.py
        from config import DATA_FOLDER
        if isinstance(DATA_FOLDER, str) and DATA_FOLDER.strip():
            chosen_path = DATA_FOLDER.strip()
            chosen_path_source = "config.py (DATA_FOLDER)"
        else:
            logger.warning(f"DATA_FOLDER in config.py is not a valid non-empty string. Falling back to default '{DEFAULT_RELATIVE_PATH}'.")
    except ImportError:
        logger.info("config.py not found or DATA_FOLDER not defined. Using default path.")
    except Exception as e:
        logger.error(f"An unexpected error occurred while trying to read DATA_FOLDER from config.py: {e}. Falling back to default.")

    # Determine the base path for resolving relative paths
    if app_root_path:
        base_path = app_root_path
        base_path_source = "provided app_root_path"
    else:
        base_path = os.getcwd()
        base_path_source = "os.getcwd()"
        logger.warning(f"No app_root_path provided to get_data_folder_path. Using current working directory ({base_path}) as base. Ensure this is the intended behavior.")

    # Resolve the chosen path (relative or absolute) to an absolute path
    try:
        if os.path.isabs(chosen_path):
            absolute_path = chosen_path
            logger.info(f"Using absolute path from {chosen_path_source}: {absolute_path}")
        else:
            absolute_path = os.path.abspath(os.path.join(base_path, chosen_path))
            logger.info(f"Resolved relative path from {chosen_path_source} ('{chosen_path}') relative to {base_path_source} ('{base_path}') to absolute path: {absolute_path}")

        if not os.path.isdir(absolute_path):
             logger.warning(f"The determined data folder path does not exist or is not a directory: {absolute_path}")

        return absolute_path
    except Exception as e:
        logger.error(f"Failed to resolve data folder path '{chosen_path}' relative to '{base_path}'. Error: {e}. Falling back to default relative path '{DEFAULT_RELATIVE_PATH}' resolved against '{base_path}'.")
        try:
             fallback_path = os.path.abspath(os.path.join(base_path, DEFAULT_RELATIVE_PATH))
             logger.info(f"Using fallback absolute path: {fallback_path}")
             if not os.path.isdir(fallback_path):
                 logger.warning(f"The fallback data folder path does not exist or is not a directory: {fallback_path}")
             return fallback_path
        except Exception as final_e:
            logger.critical(f"CRITICAL: Failed even to resolve fallback path. Returning '.'. Error: {final_e}")
            return '.'

# --- NEW: Function to load exclusions --- 
def load_exclusions(exclusion_file_path):
    """
    Loads the exclusion data from the specified CSV file.
    Args:
        exclusion_file_path (str): The full path to the exclusions CSV file.
    Returns:
        pandas.DataFrame or None: A DataFrame containing the exclusion data 
                                 if the file exists and is loaded successfully, 
                                 otherwise None.
    """
    logger = logging.getLogger(__name__)
    try:
        if not os.path.exists(exclusion_file_path):
            logger.warning(f"Exclusion file not found: {exclusion_file_path}. Returning None.")
            return None
        try:
            exclusions_df = pd.read_csv(exclusion_file_path, dtype=str) # Read all as string initially
        except FileNotFoundError:
            logger.error(f"Exclusion file not found during read: {exclusion_file_path}")
            return None
        except pd.errors.EmptyDataError:
            logger.warning(f"Exclusion file is empty: {exclusion_file_path}. Returning empty DataFrame.")
            return pd.DataFrame() # Return an empty DataFrame for consistency
        except pd.errors.ParserError as e:
            logger.error(f"Parser error in exclusion file {exclusion_file_path}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading exclusion file {exclusion_file_path}: {e}", exc_info=True)
            return None
        # Optional: Convert date columns if needed, handle potential errors
        # Example: 
        # for col in ['AddDate', 'EndDate']:
        #     if col in exclusions_df.columns:
        #         exclusions_df[col] = pd.to_datetime(exclusions_df[col], errors='coerce')
        logger.info(f"Successfully loaded exclusions from {exclusion_file_path}. Shape: {exclusions_df.shape}")
        return exclusions_df
    except Exception as e:
        logger.error(f"Error loading exclusion file {exclusion_file_path}: {e}", exc_info=True)
        return None

# --- Moved from comparison_views.py --- Function to load weights and determine held status ---
def load_weights_and_held_status(data_folder: str, weights_filename: str = 'w_secs.csv', id_col_override: str = 'ISIN') -> pd.Series:
    """
    Loads the weights file (e.g., w_secs.csv), identifies the latest date,
    and returns a boolean Series indicating which securities (indexed by the ID column)
    have a non-zero weight on that date (i.e., are currently held).

    Args:
        data_folder: The absolute path to the data directory.
        weights_filename: The name of the weights file.
        id_col_override: The specific column name in the weights file expected to contain the IDs for joining.
                         Defaults to 'ISIN'.

    Returns:
        A pandas Series where the index is the Security ID (e.g., ISIN) and the value
        is True if the security is held on the latest date, False otherwise.
        Returns an empty Series if the file cannot be loaded or processed.

    Requires:
        - pandas
        - pathlib
        - flask (for current_app.logger)
        - The _is_date_like utility function from this module.
    """
    # Use current_app.logger for logging within the Flask context
    logger = current_app.logger
    logger.info(f"--- Entering load_weights_and_held_status utility for {weights_filename} ---")
    weights_filepath = Path(data_folder) / weights_filename
    if not weights_filepath.exists():
        logger.warning(f"Weights file not found: {weights_filepath}")
        return pd.Series(dtype=bool)

    try:
        logger.info(f"Loading weights data from: {weights_filepath}")
        weights_df = pd.read_csv(weights_filepath, low_memory=False)
        weights_df.columns = weights_df.columns.str.strip()

        # --- Identify Date and ID columns ---
        date_col = next((col for col in weights_df.columns if 'date' in col.lower()), None)
        # Prioritize the explicitly provided id_col_override, then look for ISIN/SecurityID
        id_col_in_file = id_col_override if id_col_override in weights_df.columns else \
                         next((col for col in weights_df.columns if col.lower() in ['isin', 'securityid']), None)

        if not id_col_in_file:
            logger.error(f"Could not automatically identify ID column ('{id_col_override}' or fallback) in {weights_filepath}. Columns found: {weights_df.columns.tolist()}")
            return pd.Series(dtype=bool)
        logger.info(f"Weights file ID column identified: '{id_col_in_file}' (target override: '{id_col_override}')")

        # --- Identify and Melt Date Columns --- Use _is_date_like from this module
        date_columns = [col for col in weights_df.columns if _is_date_like(col)]
        
        if not date_columns:
            if not date_col:
                logger.error(f"No date column or date-like columns found in {weights_filepath}")
                return pd.Series(dtype=bool)
                
            logger.info(f"No date-like columns found. Attempting to use explicit date column: '{date_col}'")
            try:
                weights_df[date_col] = pd.to_datetime(weights_df[date_col], errors='coerce')
                if weights_df[date_col].isnull().all(): raise ValueError("Date column parsing failed.")
                
                value_col = next((col for col in weights_df.columns if col.lower() == 'value'), None)
                if not value_col:
                    # Try common weight/percentage column names if 'Value' isn't present
                    potential_value_cols = [c for c in weights_df.columns if c.lower() in ['weight', 'wgt', 'pct', 'percentage']]
                    if potential_value_cols:
                         value_col = potential_value_cols[0]
                         logger.info(f"Found potential value column: '{value_col}'")
                    else:
                        # Fallback: Assume last numeric column if no clear candidate
                        numeric_cols = weights_df.select_dtypes(include='number').columns
                        if len(numeric_cols) > 0:
                             value_col = numeric_cols[-1]
                             logger.warning(f"No 'Value' or common weight column found in long-format weights file, assuming last numeric column '{value_col}' holds weights.")
                        else:
                            logger.error(f"Could not identify a value/weight column in long-format weights file: {weights_filepath}")
                            return pd.Series(dtype=bool)

                # Rename for consistency (using the override ID name)                 
                weights_df = weights_df.rename(columns={date_col: 'Date', id_col_in_file: id_col_override, value_col: 'Value'})
                weights_df['Value'] = pd.to_numeric(weights_df['Value'], errors='coerce')
                logger.info(f"Processed weights as long format. Columns: {weights_df.columns.tolist()}")

            except Exception as e:
                logger.error(f"Failed to process weights file {weights_filepath} as long format: {e}", exc_info=True)
                return pd.Series(dtype=bool)
        else:
            logger.info(f"Found {len(date_columns)} date-like columns in {weights_filename}: {date_columns[:5]}{'...' if len(date_columns) > 5 else ''}")
            # Wide format: Melt the DataFrame
            id_vars = [col for col in weights_df.columns if col not in date_columns]
            # Ensure the identified ID column is included in id_vars
            if id_col_in_file not in id_vars:
                 # This case might happen if the ID column itself looks like a date - highly unlikely but possible
                 logger.warning(f"Identified ID column '{id_col_in_file}' was potentially misinterpreted as a date column. Forcing it as an ID variable.")
                 if id_col_in_file in date_columns: date_columns.remove(id_col_in_file)
                 id_vars.append(id_col_in_file) # Ensure it's treated as ID
            
            # Check if id_vars is empty (would happen if only ID and date columns exist)
            if not id_vars:
                logger.error(f"Error melting weights: No non-date ID variables found. Columns: {weights_df.columns.tolist()}")
                return pd.Series(dtype=bool)
                
            melted_weights = weights_df.melt(id_vars=id_vars, value_vars=date_columns, var_name='Date', value_name='Value')

            melted_weights['Date'] = pd.to_datetime(melted_weights['Date'], errors='coerce')
            melted_weights['Value'] = pd.to_numeric(melted_weights['Value'], errors='coerce')

            # Rename the identified ID column TO the standard override name (e.g., 'ISIN')
            melted_weights = melted_weights.rename(columns={id_col_in_file: id_col_override})
            weights_df = melted_weights # Use the melted df going forward
            logger.info(f"Processed weights as wide format (melted). Columns: {weights_df.columns.tolist()}")

        # --- Filter by Latest Date and Value --- 
        # Check if the required columns exist after processing
        required_cols = [id_col_override, 'Date', 'Value']
        if not all(col in weights_df.columns for col in required_cols):
             logger.error(f"Required columns ({required_cols}) not present in processed weights DataFrame. Columns found: {weights_df.columns.tolist()}")
             return pd.Series(dtype=bool)
             
        latest_date = weights_df['Date'].max()
        if pd.isna(latest_date):
            logger.warning(f"Could not determine the latest date in {weights_filepath}.")
            return pd.Series(dtype=bool)
        logger.info(f"Latest date in weights file '{weights_filepath}': {latest_date}")

        latest_weights = weights_df[
            (weights_df['Date'] == latest_date) & 
            (weights_df['Value'].notna()) & 
            (weights_df['Value'] > 0)
        ].copy()
        
        if latest_weights.empty:
            logger.warning(f"No securities found with positive weight on the latest date ({latest_date}) in {weights_filepath}. Returning empty held status.")
            return pd.Series(dtype=bool)

        # --- Determine Held Status --- Use the OVERRIDE ID column name (e.g., 'ISIN')
        held_status_col = id_col_override 
        logger.info(f"Using '{held_status_col}' column from processed {weights_filename} for held_status index.")

        # Create the boolean Series: index is the Security ID, value is True
        held_ids = latest_weights.drop_duplicates(subset=[held_status_col])[held_status_col]
        held_status = pd.Series(True, index=held_ids)
        held_status.index.name = held_status_col # Ensure index name matches the ID column

        logger.debug(f"Held status index preview (first 5 values): {held_status.index[:5].tolist()}")
        logger.debug(f"Held status values preview (first 5): {held_status.head().to_dict()}")
        logger.info(f"Determined held status for {len(held_status)} unique IDs based on weights on {latest_date}.")

        return held_status

    except FileNotFoundError:
        logger.error(f"Weights file not found at path: {weights_filepath}")
        return pd.Series(dtype=bool)
    except pd.errors.EmptyDataError:
        logger.warning(f"Weights file is empty: {weights_filepath}")
        return pd.Series(dtype=bool)
    except Exception as e:
        logger.error(f"Error loading or processing weights file {weights_filepath}: {e}", exc_info=True)
        return pd.Series(dtype=bool)

def replace_nan_with_none(obj):
    """Recursively replaces np.nan with None in a nested structure (dicts, lists).
    Useful for preparing data for JSON serialization where NaN is not valid.
    """
    if isinstance(obj, dict):
        return {k: replace_nan_with_none(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_nan_with_none(elem) for elem in obj]
    # Check specifically for pandas/numpy NaN values
    elif pd.isna(obj) and isinstance(obj, (float, np.floating)):
        return None
    else:
        return obj

def load_fund_groups(data_folder: str, fund_groups_filename: str = 'FundGroups.csv') -> dict:
    """
    Loads fund group definitions from FundGroups.csv in the given data folder.
    Returns a dict mapping group name to list of fund codes.
    Skips empty cells and trims whitespace. Ignores empty groups.
    """
    logger = logging.getLogger(__name__)
    fund_groups_path = os.path.join(data_folder, fund_groups_filename)
    if not os.path.exists(fund_groups_path):
        logger.warning(f"FundGroups.csv not found at {fund_groups_path}")
        return {}
    groups = {}
    try:
        with open(fund_groups_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            # DictReader uses first row as fieldnames
            for row in reader:
                for group, fund in row.items():
                    if fund and fund.strip():
                        groups.setdefault(group, []).append(fund.strip())
        # Remove empty groups
        groups = {k: v for k, v in groups.items() if v}
        return groups
    except Exception as e:
        logger.error(f"Error loading FundGroups.csv: {e}")
        return {}

# Example usage (for testing purposes, typically called from app.py or scripts)
# if __name__ == '__main__':
#     # Simulate being called from an app context
#     script_dir = os.path.dirname(os.path.abspath(__file__))
#     project_root = os.path.dirname(script_dir) # Assuming utils.py is one level down from root
#     print(f"Simulating call with project root: {project_root}")
#     data_path_from_app = get_data_folder_path(app_root_path=project_root)
#     print(f"Data path (app context): {data_path_from_app}")
#
#     # Simulate being called from a standalone script without app_root_path
#     print("\nSimulating call without providing app_root_path (uses CWD):")
#     data_path_standalone = get_data_folder_path()
#     print(f"Data path (standalone context): {data_path_standalone}") 