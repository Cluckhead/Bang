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

# Configure logging
# Removed basicConfig - logging is now configured centrally in app.py
# logger = logging.getLogger(__name__) # Get logger for this module

DEFAULT_RELATIVE_PATH = 'Data'

def _is_date_like(column_name):
    """Check if a column name looks like a date (e.g., YYYY-MM-DD or DD/MM/YYYY).
    Updated regex to match both common formats.
    Ensures the pattern matches the entire string.
    """
    # Regex explanation:
    # ^            - Start of string
    # (\d{4}-\d{2}-\d{2}) - Group 1: YYYY-MM-DD format
    # |            - OR
    # (\d{2}/\d{2}/\d{4}) - Group 2: DD/MM/YYYY format
    # $            - End of string
    pattern = r'^((\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{4}))$'
    return bool(re.match(pattern, str(column_name)))

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
        print(f"Error parsing fund string '{fund_string}': {e}")
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
    chosen_path_source = f"default ('{DEFAULT_RELATIVE_PATH}')"
    chosen_path = DEFAULT_RELATIVE_PATH

    try:
        # Attempt to import the path from config.py
        # This approach allows config.py to be optional or lack the variable
        from config import DATA_FOLDER
        if isinstance(DATA_FOLDER, str) and DATA_FOLDER.strip():
            chosen_path = DATA_FOLDER.strip()
            chosen_path_source = "config.py (DATA_FOLDER)"
        else:
            logging.warning(f"DATA_FOLDER in config.py is not a valid non-empty string. Falling back to default '{DEFAULT_RELATIVE_PATH}'.")
    except ImportError:
        logging.info("config.py not found or DATA_FOLDER not defined. Using default path.")
    except Exception as e:
        logging.error(f"An unexpected error occurred while trying to read DATA_FOLDER from config.py: {e}. Falling back to default.")

    # Determine the base path for resolving relative paths
    if app_root_path:
        base_path = app_root_path
        base_path_source = "provided app_root_path"
    else:
        # Use current working directory if no app_root_path is provided
        # This is suitable for standalone scripts run from the project root,
        # but can be unreliable otherwise. Providing app_root_path is safer.
        base_path = os.getcwd()
        base_path_source = "os.getcwd()"
        logging.warning(f"No app_root_path provided to get_data_folder_path. Using current working directory ({base_path}) as base. Ensure this is the intended behavior.")

    # Resolve the chosen path (relative or absolute) to an absolute path
    try:
        if os.path.isabs(chosen_path):
            absolute_path = chosen_path
            logging.info(f"Using absolute path from {chosen_path_source}: {absolute_path}")
        else:
            absolute_path = os.path.abspath(os.path.join(base_path, chosen_path))
            logging.info(f"Resolved relative path from {chosen_path_source} ('{chosen_path}') relative to {base_path_source} ('{base_path}') to absolute path: {absolute_path}")

        # Basic check: does the directory exist? Log a warning if not.
        # Consider adding creation logic if needed, but for now, just check.
        if not os.path.isdir(absolute_path):
             logging.warning(f"The determined data folder path does not exist or is not a directory: {absolute_path}")

        return absolute_path
    except Exception as e:
        logging.error(f"Failed to resolve data folder path '{chosen_path}' relative to '{base_path}'. Error: {e}. Falling back to default relative path '{DEFAULT_RELATIVE_PATH}' resolved against '{base_path}'.")
        # Fallback resolution in case of error during primary resolution
        try:
             fallback_path = os.path.abspath(os.path.join(base_path, DEFAULT_RELATIVE_PATH))
             logging.info(f"Using fallback absolute path: {fallback_path}")
             if not os.path.isdir(fallback_path):
                 logging.warning(f"The fallback data folder path does not exist or is not a directory: {fallback_path}")
             return fallback_path
        except Exception as final_e:
            logging.critical(f"CRITICAL: Failed even to resolve fallback path. Returning '.'. Error: {final_e}")
            # Absolute last resort
            return '.'

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