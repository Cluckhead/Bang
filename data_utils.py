# Purpose: Utility functions for robust data loading, parsing, and transformation in the Simple Data Checker application.
# This module provides helpers for reading CSV files, parsing dates, identifying columns, and more, with strong error handling and logging.

import logging
from typing import Optional, Any, List, Dict, Callable
import pandas as pd
import re
import utils

logger = logging.getLogger(__name__)

def read_csv_robustly(filepath: str, **kwargs) -> Optional[pd.DataFrame]:
    """
    Attempts to read a CSV file robustly, handling common errors gracefully.
    Returns a DataFrame if successful, or None if an error occurs.
    Logs errors with details for diagnostics.
    Accepts standard pandas.read_csv kwargs.
    """
    try:
        df = pd.read_csv(filepath, **kwargs)
        return df
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
    except pd.errors.EmptyDataError:
        logger.error(f"Empty data: {filepath}")
    except pd.errors.ParserError as e:
        logger.error(f"Parser error in {filepath}: {e}")
    except UnicodeDecodeError as e:
        logger.error(f"Unicode decode error in {filepath}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error reading {filepath}: {e}", exc_info=True)
    return None 

def parse_dates_robustly(series: pd.Series, formats: list = None) -> pd.Series:
    """
    Attempts to parse a pandas Series of date strings using multiple common formats and pandas inference.
    Tries standard formats (YYYY-MM-DD, DD/MM/YYYY, ISO8601), then falls back to pandas' flexible parser.
    Logs warnings on failures and returns a Series with NaT for unparseable values.
    Args:
        series (pd.Series): Series of date strings to parse.
        formats (list, optional): List of date formats to try. If None, uses defaults.
    Returns:
        pd.Series: Series of parsed dates (dtype 'datetime64[ns]'), with NaT for unparseable values.
    """
    if formats is None:
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]
    parsed = pd.Series([pd.NaT] * len(series), index=series.index)
    remaining = series.copy()
    for fmt in formats:
        mask = parsed.isna() & remaining.notna()
        if mask.any():
            try:
                parsed_dates = pd.to_datetime(remaining[mask], format=fmt, errors="coerce")
                parsed.loc[mask] = parsed_dates
            except Exception as e:
                logger.warning(f"Error parsing dates with format {fmt}: {e}")
    # Final fallback: pandas flexible parser
    mask = parsed.isna() & remaining.notna()
    if mask.any():
        try:
            parsed_dates = pd.to_datetime(remaining[mask], errors="coerce")
            parsed.loc[mask] = parsed_dates
        except Exception as e:
            logger.warning(f"Error in fallback flexible date parsing: {e}")
    # Log summary
    total = len(series)
    nat_count = parsed.isna().sum()
    if nat_count > 0:
        logger.warning(f"parse_dates_robustly: {nat_count}/{total} values could not be parsed as dates. Examples: {series[parsed.isna()].unique()[:5]}")
    else:
        logger.info(f"parse_dates_robustly: Successfully parsed all {total} date values.")
    return parsed 

def identify_columns(columns: List[str], patterns: Dict[str, List[str]], required: List[str]) -> Dict[str, Optional[str]]:
    """
    Identifies columns in a list based on regex patterns for each category.
    Args:
        columns (List[str]): List of column names to search.
        patterns (Dict[str, List[str]]): Dict mapping category (e.g., 'date', 'id') to list of regex patterns.
        required (List[str]): List of required categories that must be found.
    Returns:
        Dict[str, Optional[str]]: Mapping from category to found column name (or None if not found).
    Logs warnings if required categories are not found.
    """
    result = {}
    for category, regex_list in patterns.items():
        found = None
        for regex in regex_list:
            for col in columns:
                if re.search(regex, col, re.IGNORECASE):
                    found = col
                    break
            if found:
                break
        result[category] = found
        if found:
            logger.info(f"identify_columns: Found {category} column: '{found}' using pattern(s) {regex_list}")
        else:
            logger.warning(f"identify_columns: No column found for category '{category}' using patterns {regex_list}")
    # Check required
    for req in required:
        if not result.get(req):
            logger.error(f"identify_columns: Required category '{req}' not found in columns: {columns}")
    return result 

def convert_to_numeric_robustly(series: pd.Series) -> pd.Series:
    """
    Converts a pandas Series to numeric, coercing errors to NaN. Logs the number of values coerced to NaN.
    Args:
        series (pd.Series): Series to convert to numeric.
    Returns:
        pd.Series: Series of numeric values (dtype float), with NaN for unparseable values.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    coerced_nans = numeric.isna().sum() - series.isna().sum()
    if coerced_nans > 0:
        logger.warning(f"convert_to_numeric_robustly: {coerced_nans} values could not be converted to numeric and were set to NaN. Examples: {series[numeric.isna()].unique()[:5]}")
    else:
        logger.info(f"convert_to_numeric_robustly: All {len(series)} values converted to numeric.")
    return numeric 

def melt_wide_data(df: pd.DataFrame, id_vars: List[str], date_like_check_func: Optional[Callable] = None) -> Optional[pd.DataFrame]:
    """
    Converts a wide-format DataFrame (dates as columns) to long format using melt.
    Identifies date columns using the provided date_like_check_func.
    Parses dates robustly and returns the melted DataFrame, or None on error.
    Args:
        df (pd.DataFrame): Input wide-format DataFrame.
        id_vars (List[str]): List of columns to use as identifier variables.
        date_like_check_func (Callable, optional): Function to check if a column is date-like. If None, uses utils._is_date_like.
    Returns:
        Optional[pd.DataFrame]: Melted long-format DataFrame, or None on error.
    """
    try:
        if date_like_check_func is None:
            from utils import _is_date_like
            date_like_check_func = _is_date_like
        all_cols = df.columns.tolist()
        date_cols = [col for col in all_cols if date_like_check_func(col)]
        if not date_cols:
            logger.error(f"melt_wide_data: No date-like columns found in DataFrame columns: {all_cols}")
            return None
        logger.info(f"melt_wide_data: Identified date columns: {date_cols}")
        melted = pd.melt(df, id_vars=id_vars, value_vars=date_cols, var_name="Date_Str", value_name="Value")
        melted["Date"] = parse_dates_robustly(melted["Date_Str"])
        melted.drop(columns=["Date_Str"], inplace=True)
        logger.info(f"melt_wide_data: Melted DataFrame shape: {melted.shape}")
        return melted
    except Exception as e:
        logger.error(f"melt_wide_data: Error during melt: {e}", exc_info=True)
        return None 