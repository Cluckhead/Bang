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
try:
    from flask import current_app, request  # Added current_app and request
except ImportError:
    # Allow tests to run without Flask
    current_app = None
    request = None
import numpy as np
import csv
from typing import Any, Optional, List, Dict, Union, Tuple
from core.data_utils import read_csv_robustly, melt_wide_data
import yaml
from datetime import datetime, timedelta
import functools
import time
import threading

# Configure logging
# Removed basicConfig - logging is now configured centrally in app.py
logger = logging.getLogger(__name__)  # Get logger for this module

DEFAULT_RELATIVE_PATH = "Data"

# Global lock for thread-safe logging
timing_log_lock = threading.Lock()

def load_app_config():
    """Load application configuration from settings"""
    try:
        from core.settings_loader import get_app_config
        return get_app_config()
    except Exception as e:
        print(f"Warning: Could not load app config: {e}")
        return {}

def is_api_timing_enabled():
    """Check if API timing is enabled in configuration"""
    config = load_app_config()
    return config.get('api_timing_enabled', False)

def get_timing_log_retention_hours():
    """Get the retention hours for timing logs"""
    config = load_app_config()
    hours = config.get('api_timing_log_retention_hours', 48)
    # Convert to int if it's a string
    return int(hours) if isinstance(hours, str) else hours

def setup_timing_logger(app):
    """Set up the timing logger with proper file path"""
    timing_log_path = os.path.join(app.instance_path, 'loading_times.log')
    
    # Create timing logger
    timing_logger = logging.getLogger('api_timing')
    timing_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    timing_logger.handlers.clear()
    
    # Create file handler
    timing_handler = logging.FileHandler(timing_log_path)
    timing_formatter = logging.Formatter(
        '%(asctime)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    timing_handler.setFormatter(timing_formatter)
    timing_logger.addHandler(timing_handler)
    
    # Prevent propagation to root logger to avoid duplicate logs
    timing_logger.propagate = False
    
    return timing_logger

def prune_timing_logs(app):
    """Remove timing log entries older than configured retention period"""
    if not is_api_timing_enabled():
        return
        
    timing_log_path = os.path.join(app.instance_path, 'loading_times.log')
    
    if not os.path.exists(timing_log_path):
        return
    
    try:
        retention_hours = get_timing_log_retention_hours()
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)
        
        with timing_log_lock:
            # Read all log lines
            with open(timing_log_path, 'r') as f:
                lines = f.readlines()
            
            # Filter lines newer than cutoff
            filtered_lines = []
            for line in lines:
                try:
                    # Extract timestamp from log line (YYYY-MM-DD HH:MM:SS format)
                    timestamp_str = line.split(' | ')[0]
                    log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    
                    if log_time >= cutoff_time:
                        filtered_lines.append(line)
                except (ValueError, IndexError):
                    # Keep lines that can't be parsed
                    filtered_lines.append(line)
            
            # Write back filtered lines
            with open(timing_log_path, 'w') as f:
                f.writelines(filtered_lines)
                
            pruned_count = len(lines) - len(filtered_lines)
            if pruned_count > 0:
                app.logger.info(f"Pruned {pruned_count} old timing log entries")
                
    except Exception as e:
        app.logger.error(f"Error pruning timing logs: {e}")

def log_api_timing(endpoint, method, duration_ms, status_code, error_msg=None):
    """Log API timing information"""
    try:
        timing_logger = logging.getLogger('api_timing')
        
        # Get request details
        remote_addr = getattr(request, 'remote_addr', 'unknown') if request else 'unknown'
        user_agent = getattr(request, 'user_agent', 'unknown') if request else 'unknown'
        
        # Format timing information
        status_info = f"STATUS:{status_code}"
        if error_msg:
            status_info += f" ERROR:{error_msg}"
            
        timing_info = (
            f"ENDPOINT:{endpoint} | "
            f"METHOD:{method} | "
            f"DURATION:{duration_ms:.2f}ms | "
            f"{status_info} | "
            f"IP:{remote_addr} | "
            f"USER_AGENT:{str(user_agent)[:100]}"  # Truncate user agent
        )
        
        with timing_log_lock:
            timing_logger.info(timing_info)
            
    except Exception as e:
        # Don't let timing logging errors break the application
        if current_app:
            current_app.logger.error(f"Error logging API timing: {e}")

def time_api_calls(f):
    """Decorator to time API calls and log the results"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if timing is enabled
        if not is_api_timing_enabled():
            return f(*args, **kwargs)
        
        start_time = time.time()
        status_code = 200
        error_msg = None
        
        try:
            response = f(*args, **kwargs)
            
            # Extract status code from response
            if hasattr(response, 'status_code'):
                status_code = response.status_code
            elif isinstance(response, tuple) and len(response) > 1:
                status_code = response[1]
                
            return response
            
        except Exception as e:
            status_code = 500
            error_msg = str(e)[:200]  # Truncate error message
            raise
            
        finally:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            # Get endpoint and method info
            endpoint = request.endpoint if request else f.__name__
            method = request.method if request else 'UNKNOWN'
            
            # Log the timing
            log_api_timing(endpoint, method, duration_ms, status_code, error_msg)
    
    return decorated_function

def load_yaml_config(yaml_file_path: str) -> Dict[str, Any]:
    """Loads a YAML configuration file and returns its contents as a dictionary.

    Args:
        yaml_file_path (str): The path to the YAML file to load.

    Returns:
        Dict[str, Any]: The contents of the YAML file as a dictionary.
                       Returns an empty dictionary if the file cannot be loaded.
    """
    try:
        with open(yaml_file_path, "r") as file:
            config_data = yaml.safe_load(file)
        return config_data if config_data is not None else {}
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {yaml_file_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {yaml_file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading YAML file {yaml_file_path}: {e}")
        return {}


# Load date patterns from settings
try:
    from core.settings_loader import get_date_patterns
    DATE_COLUMN_PATTERNS = get_date_patterns()
except Exception:
    # Fallback if settings loader not available yet
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
    
    # Load data_folder from settings
    try:
        from core.settings_loader import get_app_config
        app_cfg = get_app_config()
        data_folder_name = app_cfg.get("data_folder")
        
        if not data_folder_name:
            error_msg = "'data_folder' must be specified in settings"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        chosen_path = data_folder_name.strip()
        chosen_path_source = "settings (data_folder)"
        
    except Exception as e:
        error_msg = f"Failed to read data_folder from settings: {e}"
        logger.error(error_msg)
        raise
    
    # Determine the base path for resolving relative paths
    if app_root_path:
        base_path = app_root_path
        base_path_source = "provided app_root_path"
    else:
        # Use BASE_DIR from config.py as fallback
        from core.config import BASE_DIR
        base_path = str(BASE_DIR)
        base_path_source = "config.BASE_DIR"
 
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
            error_msg = (
                f"Configured data folder does not exist or is not a directory: {absolute_path}. "
                "Please create the folder or update DATA_FOLDER / data_folder setting."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        return absolute_path
    except Exception as e:
        # No fallback - let the error propagate
        logger.error(f"Failed to resolve data folder path: {e}")
        raise


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
        from core.data_utils import convert_to_numeric_robustly

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


def check_holidays(data_folder_path: str, currencies: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Check for holidays today or on the last business day from the holidays.csv file.
    
    Args:
        data_folder_path: Path to the data folder containing holidays.csv
        currencies: List of currencies to check (defaults to ['USD', 'EUR', 'GBP'])
    
    Returns:
        Dictionary containing holiday information:
        {
            'has_holiday_today': bool,
            'has_holiday_last_business_day': bool,
            'holidays_today': List[Dict],
            'holidays_last_business_day': List[Dict],
            'alert_message': str
        }
    """
    logger = logging.getLogger(__name__)
    
    if currencies is None:
        currencies = ['USD', 'EUR', 'GBP']
    
    holidays_file = os.path.join(data_folder_path, 'holidays.csv')
    
    # Initialize result
    result = {
        'has_holiday_today': False,
        'has_holiday_last_business_day': False,
        'holidays_today': [],
        'holidays_last_business_day': [],
        'alert_message': ''
    }
    
    try:
        # Check if holidays file exists
        if not os.path.exists(holidays_file):
            logger.warning(f"Holidays file not found: {holidays_file}")
            return result
        
        # Load holidays data
        holidays_df = pd.read_csv(holidays_file)
        
        # Convert date column to datetime
        holidays_df['date'] = pd.to_datetime(holidays_df['date'])
        
        # Get today's date and last business day
        today = datetime.now().date()
        
        # Calculate last business day (Monday = 0, Sunday = 6)
        last_business_day = today
        if today.weekday() == 0:  # Monday
            last_business_day = today - timedelta(days=3)  # Previous Friday
        elif today.weekday() == 6:  # Sunday
            last_business_day = today - timedelta(days=2)  # Previous Friday
        else:
            last_business_day = today - timedelta(days=1)  # Previous day
        
        # Filter holidays for specified currencies
        relevant_holidays = holidays_df[holidays_df['currency'].isin(currencies)]
        
        # Check for holidays today
        today_holidays = relevant_holidays[relevant_holidays['date'].dt.date == today]
        if not today_holidays.empty:
            result['has_holiday_today'] = True
            result['holidays_today'] = today_holidays.to_dict('records')
        
        # Check for holidays on last business day
        last_bd_holidays = relevant_holidays[relevant_holidays['date'].dt.date == last_business_day]
        if not last_bd_holidays.empty:
            result['has_holiday_last_business_day'] = True
            result['holidays_last_business_day'] = last_bd_holidays.to_dict('records')
        
        # Create alert message
        alert_parts = []
        if result['has_holiday_today']:
            currencies_today = [h['currency'] for h in result['holidays_today']]
            alert_parts.append(f"Holiday today for {', '.join(set(currencies_today))}")
        
        if result['has_holiday_last_business_day']:
            currencies_last_bd = [h['currency'] for h in result['holidays_last_business_day']]
            alert_parts.append(f"Holiday on last business day ({last_business_day.strftime('%Y-%m-%d')}) for {', '.join(set(currencies_last_bd))}")
        
        if alert_parts:
            result['alert_message'] = '. '.join(alert_parts) + '. This may affect data processing.'
        
    except Exception as e:
        logger.error(f"Error checking holidays: {e}")
    
    return result


def _load_holidays_set(
    data_folder_path: str,
    countries: Optional[List[str]] = None,
    currencies: Optional[List[str]] = None,
) -> set:
    """
    Load holidays.csv from the data folder and return a set of holiday dates (date objects)
    filtered by optional countries and/or currencies.

    Expected CSV columns: 'date' (YYYY-MM-DD), optional 'country', optional 'currency'.
    """
    logger = logging.getLogger(__name__)
    holidays_file = os.path.join(data_folder_path, 'holidays.csv')

    if not os.path.exists(holidays_file):
        return set()

    try:
        df = pd.read_csv(holidays_file)
        if 'date' not in df.columns:
            logger.warning("holidays.csv missing required 'date' column; ignoring file")
            return set()

        # Normalize and filter
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])

        if countries is not None and 'country' in df.columns:
            df = df[df['country'].isin(countries)]
        if currencies is not None and 'currency' in df.columns:
            df = df[df['currency'].isin(currencies)]

        return set(df['date'].dt.date.tolist())
    except Exception as e:
        logger.warning(f"Failed to load holidays from {holidays_file}: {e}")
        return set()


def filter_business_dates(
    date_strings: List[str],
    data_folder_path: str,
    countries: Optional[List[str]] = None,
    currencies: Optional[List[str]] = None,
) -> List[str]:
    """
    Given a list of date strings (mixed formats allowed), return a new list containing only
    business days (Mon-Fri) excluding any holidays listed in Data/holidays.csv.

    Returns dates formatted as YYYY-MM-DD, preserving chronological order.
    """
    if not date_strings:
        return []

    # Load holidays (default to UK/GBP if not specified)
    if countries is None and currencies is None:
        holidays = _load_holidays_set(data_folder_path, countries=['UK'], currencies=['GBP'])
    else:
        holidays = _load_holidays_set(data_folder_path, countries=countries, currencies=currencies)

    parsed = pd.to_datetime(pd.Series(date_strings), errors='coerce', dayfirst=False)
    # Drop invalid
    parsed = parsed.dropna()
    if parsed.empty:
        return []

    # Filter weekdays and not in holidays
    def _is_business_day(ts: pd.Timestamp) -> bool:
        d = ts.date()
        return ts.weekday() < 5 and d not in holidays

    filtered = [ts.strftime('%Y-%m-%d') for ts in parsed if _is_business_day(ts)]
    return filtered

def get_business_day_offset(date: datetime, offset: int) -> datetime:
    """
    Get a business day with the specified offset from the given date.
    
    Args:
        date: Starting date
        offset: Number of business days to offset (negative for past, positive for future)
    
    Returns:
        datetime object representing the business day
    """
    current_date = date
    days_moved = 0
    
    while days_moved != abs(offset):
        if offset > 0:
            current_date += timedelta(days=1)
        else:
            current_date -= timedelta(days=1)
        
        # Check if it's a weekday (Monday=0, Sunday=6)
        if current_date.weekday() < 5:  # Monday to Friday
            days_moved += 1
    
    return current_date

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
