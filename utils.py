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
        with open(filepath, "r") as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        logger.error(f"YAML config file not found: {filepath}", exc_info=True)
        return None
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error in {filepath}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error loading YAML config {filepath}: {e}", exc_info=True
        )
        return None


# Load date patterns from YAML once at module level
_date_patterns_yaml = load_yaml_config(
    os.path.join(os.path.dirname(__file__), "config", "date_patterns.yaml")
)
DATE_COLUMN_PATTERNS = _date_patterns_yaml.get("date_patterns", [])


def _is_date_like(column_name: str) -> bool:
    """
    Check if a column name appears to be a date string based on pattern matching.

    Uses regex patterns loaded from config/date_patterns.yaml to identify common
    date formats in column names (e.g., YYYY-MM-DD, DD/MM/YYYY, "Date", etc.).

    Args:
        column_name (str): Column name to check

    Returns:
        bool: True if the column name matches any of the date patterns,
              False otherwise or if column_name is not a string
    """
    if not isinstance(column_name, str):
        return False
    return any(re.search(pattern, column_name) for pattern in DATE_COLUMN_PATTERNS)


def parse_fund_list(fund_string: str) -> List[str]:
    """
    Parse a string representing a list of fund codes into a Python list.

    Takes various string formats representing a list of fund codes and
    converts them to a proper Python list of strings.

    Args:
        fund_string (str): String representing fund codes, which can be in formats:
                          '[A,B]', '[A]', '[]', 'A,B', '[ A , B ]', etc.

    Returns:
        List[str]: List of fund codes as strings. Returns empty list for empty input,
                  invalid input, or on error.
    """
    logger = logging.getLogger(__name__)
    try:
        if not fund_string or fund_string.strip() == "" or fund_string.strip() == "[]":
            return []

        # Strip surrounding [] if present
        cleaned = fund_string.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]

        # Split by commas and clean each item
        items = [item.strip() for item in cleaned.split(",") if item.strip()]
        return items
    except Exception as e:
        logger.error(f"Error parsing fund string '{fund_string}': {e}", exc_info=True)
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
    Load and prepare the exclusions data. Returns a DataFrame with exclusions if the file exists,
    None otherwise. Converts dates to datetime format and handles missing values.
    """
    logger = logging.getLogger(__name__)
    try:
        if os.path.exists(exclusion_file_path):
            logger.info(f"Loading exclusions from {exclusion_file_path}")
            exclusions_df = pd.read_csv(exclusion_file_path)

            # Convert date columns to datetime
            for date_col in ["AddDate", "EndDate"]:
                if date_col in exclusions_df.columns:
                    exclusions_df[date_col] = pd.to_datetime(
                        exclusions_df[date_col], errors="coerce"
                    )

            return exclusions_df
        else:
            logger.error(
                f"Exclusion file not found during read: {exclusion_file_path}",
                exc_info=True,
            )
            return None
    except Exception as e:
        logger.error(f"Error loading exclusions: {e}", exc_info=True)
        return None


# --- Moved from comparison_views.py --- Function to load weights and determine held status ---
def load_weights_and_held_status(
    data_folder: str,
    weights_filename: str = "w_secs.csv",
    id_col_override: str = "ISIN",
) -> pd.Series:
    """
    Loads security weights from a wide-format weights file and returns a Series indicating held status (is_held) for each security.
    Logic:
    1. Melt wide-format *w_secs.csv* to long format.
    2. Convert *Value* column to numeric (robustly, replacing zeros/invalids with NaN if configured).
    3. For each security (identified by *id_col_override*), look at the **latest date** in the data and mark *is_held* **True** only if the weight on that latest date is > 0.  This fixes the previous behaviour that flagged a security as held if it had **ever** been held in the file, even if the current/latest weight is 0.
    Returns an empty Series on error.
    """
    logger = logging.getLogger(__name__)
    try:
        weights_path = os.path.join(data_folder, weights_filename)
        df = read_csv_robustly(weights_path)
        if df is None or df.empty:
            logger.warning("Weights file could not be read or is empty: %s", weights_path)
            return pd.Series(dtype=bool)

        # Identify id column and melt to long format
        id_vars = [id_col_override] if id_col_override in df.columns else [df.columns[0]]
        df_long = melt_wide_data(df, id_vars=id_vars)
        if df_long is None or df_long.empty:
            logger.warning("Weights file could not be melted into long format or is empty after melt: %s", weights_path)
            return pd.Series(dtype=bool)

        # Convert Value to numeric robustly (with optional zero→NaN replacement)
        from data_utils import convert_to_numeric_robustly

        df_long["NumericVal"] = convert_to_numeric_robustly(df_long["Value"])

        # Ensure Date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(df_long["Date"]):
            df_long["Date"] = pd.to_datetime(df_long["Date"], errors="coerce")

        # Drop rows without a valid date
        df_long = df_long.dropna(subset=["Date"])
        if df_long.empty:
            logger.warning("All rows in weights data lacked valid dates. Returning empty Series.")
            return pd.Series(dtype=bool)

        # Sort so that the latest date per security is last
        df_long.sort_values(by=[id_vars[0], "Date"], inplace=True)

        # Get the latest row per security using groupby tail(1)
        latest_rows = df_long.groupby(id_vars[0], as_index=False).tail(1)

        # Determine held status: weight > 0
        latest_rows["is_held"] = latest_rows["NumericVal"] > 0

        held_status = latest_rows.set_index(id_vars[0])["is_held"]
        return held_status

    except Exception as e:
        logger.error("Error computing held status from weights file: %s", e, exc_info=True)
        return pd.Series(dtype=bool)


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
) -> Dict[str, List[str]]:
    """
    Load fund groups from FundGroups.csv and return as a dictionary.

    Reads the fund groups file and creates a mapping between group names and the fund
    codes that belong to each group. Uses parse_fund_list to convert fund strings
    to Python lists.

    Args:
        data_folder (str): Path to the data folder containing the file
        fund_groups_filename (str, optional): Name of the fund groups CSV file.
                                              Defaults to 'FundGroups.csv'.

    Returns:
        Dict[str, List[str]]: Dictionary mapping group names to lists of fund codes.
                             Returns empty dict if file not found or on error.
    """
    logger = logging.getLogger(__name__)
    result = {}

    try:
        fund_groups_path = os.path.join(data_folder, fund_groups_filename)
        if os.path.exists(fund_groups_path):
            df = pd.read_csv(fund_groups_path)
            if "Group" in df.columns and "Funds" in df.columns:
                for _, row in df.iterrows():
                    group_name = row["Group"]
                    funds_str = row["Funds"]
                    funds_list = parse_fund_list(funds_str)
                    result[group_name] = funds_list
        return result
    except Exception as e:
        logger.error(f"Error loading FundGroups.csv: {e}", exc_info=True)
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
