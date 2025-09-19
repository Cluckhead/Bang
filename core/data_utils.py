# Purpose: Utility functions for robust data loading, parsing, and transformation in the Simple Data Checker application.
# This module provides helpers for reading CSV files, parsing dates, identifying columns, and more, with strong error handling and logging.

import logging
from typing import Optional, Any, List, Dict, Callable
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import re

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
        logger.error(f"File not found: {filepath}", exc_info=True)
    except pd.errors.EmptyDataError:
        logger.error(f"Empty data: {filepath}", exc_info=True)
    except pd.errors.ParserError as e:
        logger.error(f"Parser error in {filepath}: {e}", exc_info=True)
    except UnicodeDecodeError as e:
        logger.error(f"Unicode decode error in {filepath}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error reading {filepath}: {e}", exc_info=True)
    return None


def parse_dates_robustly(series: pd.Series, formats: list = None) -> pd.Series:
    """
    Attempts to parse a pandas Series of date strings using multiple common formats and pandas inference.
    Tries standard formats (YYYY-MM-DD, DD/MM/YYYY, ISO8601), Excel serial dates, then falls back to pandas' flexible parser.
    Logs warnings on failures and returns a Series with NaT for unparseable values.
    Args:
        series (pd.Series): Series of date strings to parse.
        formats (list, optional): List of date formats to try. If None, uses defaults.
    Returns:
        pd.Series: Series of parsed dates (dtype 'datetime64[ns]'), with NaT for unparseable values.
    """
    import re
    # Input validation
    if not isinstance(series, pd.Series):
        logger.error("parse_dates_robustly: Input must be a pandas Series")
        return pd.Series(dtype='datetime64[ns]')
    
    if series.empty:
        logger.warning("parse_dates_robustly: Input series is empty")
        return pd.Series(dtype='datetime64[ns]')
    
    # Check if series is already datetime-like
    if pd.api.types.is_datetime64_any_dtype(series):
        logger.info("parse_dates_robustly: Series already contains datetime values")
        return series
    
    if formats is None:
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]
    
    try:
        parsed = pd.Series([pd.NaT] * len(series), index=series.index, dtype='datetime64[ns]')
        remaining = series.copy()
        
        # First, try Excel serial dates for numeric values
        mask = parsed.isna() & remaining.notna()
        if mask.any():
            for idx in series[mask].index:
                val_str = str(remaining.loc[idx]).strip()
                if re.match(r'^\d+(\.\d*)?$', val_str):
                    try:
                        serial_number = float(val_str)
                        # Excel serial dates: 1 = January 1, 1900 (but Excel incorrectly treats 1900 as a leap year)
                        # Adjust for Excel's leap year bug and convert to datetime
                        if serial_number >= 60:  # After Feb 28, 1900
                            serial_number -= 1  # Adjust for Excel's 1900 leap year bug
                        excel_epoch = datetime(1900, 1, 1)
                        parsed.loc[idx] = pd.Timestamp(excel_epoch + timedelta(days=serial_number - 1))
                    except (ValueError, OverflowError):
                        pass  # Will be handled by other parsing methods
        
        for fmt in formats:
            mask = parsed.isna() & remaining.notna()
            if mask.any():
                try:
                    parsed_dates = pd.to_datetime(
                        remaining[mask], format=fmt, errors="coerce"
                    )
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
            failed_examples = series[parsed.isna()].unique()[:5]
            logger.warning(
                f"parse_dates_robustly: {nat_count}/{total} values could not be parsed as dates. "
                f"Examples of failed values: {failed_examples.tolist()}"
            )
        else:
            logger.info(
                f"parse_dates_robustly: Successfully parsed all {total} date values."
            )
        
        return parsed
        
    except Exception as e:
        logger.error(f"Critical error in parse_dates_robustly: {e}", exc_info=True)
        # Return series with all NaT values as fallback
        return pd.Series([pd.NaT] * len(series), index=series.index, dtype='datetime64[ns]')


def identify_columns(
    columns: List[str], patterns: Dict[str, List[str]], required: List[str]
) -> Dict[str, Optional[str]]:
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
            logger.info(
                f"identify_columns: Found {category} column: '{found}' using pattern(s) {regex_list}"
            )
        else:
            logger.warning(
                f"identify_columns: No column found for category '{category}' using patterns {regex_list}"
            )
    # After scanning, ensure all required categories were located.
    missing_required = [req for req in required if not result.get(req)]
    for req in missing_required:
        logger.error(
            f"identify_columns: Required category '{req}' not found in columns: {columns}",
            exc_info=True,
        )

    # If any required category is absent, raise an explicit error so callers/tests can react.
    if missing_required:
        # Joining for a readable message; keep list for diagnostics.
        missing_str = ", ".join(missing_required)
        raise ValueError(
            f"Required column(s) not found: {missing_str}. Columns provided: {columns}"
        )
    return result


def replace_zeros_with_nan(series: pd.Series, log: bool = True) -> pd.Series:
    """
    Replaces all zeros in a numeric pandas Series with NaN.
    This is used to prevent zeros from causing issues in charts and correlation calculations.
    Args:
        series (pd.Series): Numeric series that may contain zeros.
    Returns:
        pd.Series: Series with zeros replaced by NaN.
    """
    # Only process numeric series
    if not pd.api.types.is_numeric_dtype(series):
        logger.debug("replace_zeros_with_nan: Series is not numeric, returning unchanged.")
        return series
    
    # Count zeros being replaced
    zero_count = (series == 0).sum()
    
    # Replace zeros with NaN
    result = series.replace(0, np.nan)
    
    if log:
        if zero_count > 0:
            logger.debug(
                f"replace_zeros_with_nan: Replaced {zero_count} zeros with NaN to prevent chart and correlation issues."
            )
        else:
            logger.debug("replace_zeros_with_nan: No zeros found to replace.")
    
    return result


def convert_to_numeric_robustly(series: pd.Series, replace_zeros: bool = True, log: bool = True) -> pd.Series:
    """
    Converts a pandas Series to numeric, coercing errors to NaN. 
    Optionally replaces zeros with NaN to prevent issues in charts and correlation calculations.
    Logs the number of values coerced to NaN and zeros replaced.
    Args:
        series (pd.Series): Series to convert to numeric.
        replace_zeros (bool): Whether to replace zeros with NaN after conversion. Default is True.
    Returns:
        pd.Series: Series of numeric values (dtype float), with NaN for unparseable values and optionally zeros.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    coerced_nans = numeric.isna().sum() - series.isna().sum()
    if log:
        if coerced_nans > 0:
            logger.warning(
                f"convert_to_numeric_robustly: {coerced_nans} values could not be converted to numeric and were set to NaN. Examples: {series[numeric.isna()].unique()[:5]}"
            )
        else:
            logger.debug(
                f"convert_to_numeric_robustly: All {len(series)} values converted to numeric."
            )
    
    # Replace zeros with NaN if requested
    if replace_zeros:
        numeric = replace_zeros_with_nan(numeric, log=log)
    
    return numeric


def melt_wide_data(
    df: pd.DataFrame,
    id_vars: List[str],
    date_like_check_func: Optional[Callable] = None,
) -> Optional[pd.DataFrame]:
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
            from core.utils import _is_date_like

            date_like_check_func = _is_date_like
        all_cols = df.columns.tolist()
        date_cols = [col for col in all_cols if date_like_check_func(col)]
        if not date_cols:
            logger.error(
                f"melt_wide_data: No date-like columns found in DataFrame columns: {all_cols}",
                exc_info=True,
            )
            return None
        logger.info(f"melt_wide_data: Identified date columns: {date_cols}")
        melted = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=date_cols,
            var_name="Date_Str",
            value_name="Value",
        )
        melted["Date"] = parse_dates_robustly(melted["Date_Str"])
        melted.drop(columns=["Date_Str"], inplace=True)
        logger.info(f"melt_wide_data: Melted DataFrame shape: {melted.shape}")
        return melted
    except Exception as e:
        logger.error(f"melt_wide_data: Error during melt: {e}", exc_info=True)
        return None
