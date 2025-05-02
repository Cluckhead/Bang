# This file contains utility functions used throughout the Simple Data Checker application.
# These functions provide common helper functionalities like parsing specific string formats
# or validating data types, helping to keep the main application logic cleaner.

# Purpose: Utility functions for the Flask application, including YAML config loading, date parsing, fund list parsing, and more.
# Provides helpers for robust file I/O, configuration, and data validation across the Simple Data Checker app.

"""
Utility functions for the Flask application.
"""
import re
import pandas as pd
import os
import logging
from pathlib import Path  # Added pathlib
from flask import current_app  # Added current_app
import numpy as np
import csv
from typing import Any, Optional, List, Dict
import config
from data_utils import read_csv_robustly, melt_wide_data
import yaml

# Configure logging
# Removed basicConfig - logging is now configured centrally in app.py
# logger = logging.getLogger(__name__) # Get logger for this module

DEFAULT_RELATIVE_PATH = "Data"

def load_yaml_config(filepath: str) -> dict:
    """
    Loads a YAML configuration file and returns its contents as a dictionary.
    Args:
        filepath (str): Path to the YAML file.
    Returns:
        dict: Parsed YAML contents, or empty dict on error.
    """
    logger = logging.getLogger(__name__)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            logger.info(f"Loaded YAML config from {filepath}")
            return data if data else {}
    except FileNotFoundError:
        logger.error(f"YAML config file not found: {filepath}")
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error in {filepath}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading YAML config {filepath}: {e}", exc_info=True)
    return {}

# Load date patterns from YAML once at module level
_date_patterns_yaml = load_yaml_config(os.path.join(os.path.dirname(__file__), 'config', 'date_patterns.yaml'))
DATE_COLUMN_PATTERNS = _date_patterns_yaml.get('date_patterns', [])


def _is_date_like(column_name: str) -> bool:
    """Check if a column name looks like a date (e.g., YYYY-MM-DD or DD/MM/YYYY).
    Uses regex patterns loaded from config/date_patterns.yaml.
    """
    if not isinstance(column_name, str):
        return False
    return any(re.search(pattern, column_name) for pattern in DATE_COLUMN_PATTERNS)


def parse_fund_list(fund_string: str) -> list:
    """Safely parses the fund list string like '[FUND1,FUND2]' or '[FUND1]' into a list.
    Handles potential errors and variations in spacing.
    """
    if (
        not isinstance(fund_string, str)
        or not fund_string.startswith("[")
        or not fund_string.endswith("]")
    ):
        return []  # Return empty list if format is unexpected
    try:
        # Remove brackets and split by comma
        content = fund_string[1:-1]
        # Split by comma, strip whitespace from each element
        funds = [f.strip() for f in content.split(",") if f.strip()]
        return funds
    except Exception as e:
        # Use logger if available, otherwise print
        logger = logging.getLogger(__name__)
        logger.error(f"Error parsing fund string '{fund_string}': {e}")
        return []


def get_data_folder_path(app_root_path: Optional[str] = None) -> str:
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
    logger = logging.getLogger(__name__)  # Use logger
    chosen_path_source = f"default ('{DEFAULT_RELATIVE_PATH}')"
    chosen_path = DEFAULT_RELATIVE_PATH

    try:
        # Attempt to import the path from config.py
        from config import DATA_FOLDER

        if isinstance(DATA_FOLDER, str) and DATA_FOLDER.strip():
            chosen_path = DATA_FOLDER.strip()
            chosen_path_source = "config.py (DATA_FOLDER)"
        else:
            logger.warning(
                f"DATA_FOLDER in config.py is not a valid non-empty string. Falling back to default '{DEFAULT_RELATIVE_PATH}'."
            )
    except ImportError:
        logger.info(
            "config.py not found or DATA_FOLDER not defined. Using default path."
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while trying to read DATA_FOLDER from config.py: {e}. Falling back to default."
        )

    # Determine the base path for resolving relative paths
    if app_root_path:
        base_path = app_root_path
        base_path_source = "provided app_root_path"
    else:
        base_path = os.getcwd()
        base_path_source = "os.getcwd()"
        logger.warning(
            f"No app_root_path provided to get_data_folder_path. Using current working directory ({base_path}) as base. Ensure this is the intended behavior."
        )

    # Resolve the chosen path (relative or absolute) to an absolute path
    try:
        if os.path.isabs(chosen_path):
            absolute_path = chosen_path
            logger.info(
                f"Using absolute path from {chosen_path_source}: {absolute_path}"
            )
        else:
            absolute_path = os.path.abspath(os.path.join(base_path, chosen_path))
            logger.info(
                f"Resolved relative path from {chosen_path_source} ('{chosen_path}') relative to {base_path_source} ('{base_path}') to absolute path: {absolute_path}"
            )

        if not os.path.isdir(absolute_path):
            logger.warning(
                f"The determined data folder path does not exist or is not a directory: {absolute_path}"
            )

        return absolute_path
    except Exception as e:
        logger.error(
            f"Failed to resolve data folder path '{chosen_path}' relative to '{base_path}'. Error: {e}. Falling back to default relative path '{DEFAULT_RELATIVE_PATH}' resolved against '{base_path}'."
        )
        try:
            fallback_path = os.path.abspath(
                os.path.join(base_path, DEFAULT_RELATIVE_PATH)
            )
            logger.info(f"Using fallback absolute path: {fallback_path}")
            if not os.path.isdir(fallback_path):
                logger.warning(
                    f"The fallback data folder path does not exist or is not a directory: {fallback_path}"
                )
            return fallback_path
        except Exception as final_e:
            logger.critical(
                f"CRITICAL: Failed even to resolve fallback path. Returning '.'. Error: {final_e}"
            )
            return "."


# --- NEW: Function to load exclusions ---
def load_exclusions(exclusion_file_path: str) -> Optional[pd.DataFrame]:
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
            logger.warning(
                f"Exclusion file not found: {exclusion_file_path}. Returning None."
            )
            return None
        try:
            exclusions_df = pd.read_csv(
                exclusion_file_path, dtype=str
            )  # Read all as string initially
        except FileNotFoundError:
            logger.error(f"Exclusion file not found during read: {exclusion_file_path}")
            return None
        except pd.errors.EmptyDataError:
            logger.warning(
                f"Exclusion file is empty: {exclusion_file_path}. Returning empty DataFrame."
            )
            return pd.DataFrame()  # Return an empty DataFrame for consistency
        except pd.errors.ParserError as e:
            logger.error(
                f"Parser error in exclusion file {exclusion_file_path}: {e}",
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error reading exclusion file {exclusion_file_path}: {e}",
                exc_info=True,
            )
            return None
        # Optional: Convert date columns if needed, handle potential errors
        # Example:
        # for col in ['AddDate', 'EndDate']:
        #     if col in exclusions_df.columns:
        #         exclusions_df[col] = pd.to_datetime(exclusions_df[col], errors='coerce')
        logger.info(
            f"Successfully loaded exclusions from {exclusion_file_path}. Shape: {exclusions_df.shape}"
        )
        return exclusions_df
    except Exception as e:
        logger.error(
            f"Error loading exclusion file {exclusion_file_path}: {e}", exc_info=True
        )
        return None


# --- Moved from comparison_views.py --- Function to load weights and determine held status ---
def load_weights_and_held_status(
    data_folder: str,
    weights_filename: str = "w_secs.csv",
    id_col_override: str = "ISIN",
) -> pd.Series:
    """
    Loads security weights from a wide-format weights file and returns a Series indicating held status (is_held) for each security.
    Uses melt_wide_data for robust wide-to-long conversion.
    """
    weights_path = os.path.join(data_folder, weights_filename)
    df = read_csv_robustly(weights_path)
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    # Identify id columns and use melt_wide_data
    id_vars = [id_col_override] if id_col_override in df.columns else [df.columns[0]]
    df_long = melt_wide_data(df, id_vars=id_vars)
    if df_long is None or df_long.empty:
        return pd.Series(dtype=bool)
    # Determine held status: is_held if Value is numeric and > 0
    df_long["is_held"] = pd.to_numeric(df_long["Value"], errors="coerce") > 0
    held_status = df_long.groupby(id_vars[0])["is_held"].any()
    return held_status


def replace_nan_with_none(obj: Any) -> Any:
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


def load_fund_groups(
    data_folder: str, fund_groups_filename: str = "FundGroups.csv"
) -> dict:
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
        with open(fund_groups_path, newline="", encoding="utf-8") as csvfile:
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
