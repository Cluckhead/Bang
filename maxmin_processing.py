# maxmin_processing.py
# This module detects securities in Spread files whose values exceed configurable max/min thresholds.
# It scans sec_Spread.csv and sec_SpreadSP.csv, returning breaches for use in dashboard/detail views.

import os
import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Tuple

# Default thresholds
DEFAULT_MAX_THRESHOLD = 10000
DEFAULT_MIN_THRESHOLD = -100

# Metadata columns (same as staleness_processing.py)
META_COLS = 6  # ISIN, Security Name, Funds, Type, Callable, Currency

logger = logging.getLogger(__name__)

def find_value_breaches(
    filename: str,
    data_folder: str = "Data",
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    min_threshold: float = DEFAULT_MIN_THRESHOLD
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Scan a security-level file for values above max_threshold or below min_threshold.
    Ignores NaN/null values. Returns a list of breaches and total securities checked.
    """
    file_path = os.path.join(data_folder, filename)
    breaches = []
    total_count = 0
    try:
        df = pd.read_csv(file_path)
        id_column = df.columns[0]  # ISIN
        meta_columns = df.columns[:META_COLS]
        date_columns = df.columns[META_COLS:]
        total_count = len(df)
        for idx, row in df.iterrows():
            security_id = str(row[id_column])
            static_info = {col: row[col] for col in meta_columns if col != id_column}
            for date_col in date_columns:
                val = row[date_col]
                if pd.isna(val):
                    continue
                try:
                    num_val = float(val)
                except (ValueError, TypeError):
                    continue
                if num_val > max_threshold:
                    breaches.append({
                        'id': security_id,
                        'static_info': static_info,
                        'date': date_col,
                        'value': num_val,
                        'breach_type': 'max',
                        'threshold': max_threshold,
                        'file': filename
                    })
                elif num_val < min_threshold:
                    breaches.append({
                        'id': security_id,
                        'static_info': static_info,
                        'date': date_col,
                        'value': num_val,
                        'breach_type': 'min',
                        'threshold': min_threshold,
                        'file': filename
                    })
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}", exc_info=True)
    return breaches, total_count

def get_breach_summary(
    data_folder: str = "Data",
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    min_threshold: float = DEFAULT_MIN_THRESHOLD
) -> Dict[str, Dict[str, Any]]:
    """
    Returns a summary for each relevant file (sec_Spread.csv, sec_SpreadSP.csv):
    - total_count: total securities
    - max_breach_count: number of max breaches
    - min_breach_count: number of min breaches
    - details_url: for dashboard linking
    """
    summary = {}
    for filename in ["sec_Spread.csv", "sec_SpreadSP.csv"]:
        breaches, total_count = find_value_breaches(
            filename, data_folder, max_threshold, min_threshold
        )
        max_breach_count = sum(1 for b in breaches if b['breach_type'] == 'max')
        min_breach_count = sum(1 for b in breaches if b['breach_type'] == 'min')
        summary[filename] = {
            'filename': filename,
            'total_count': total_count,
            'max_breach_count': max_breach_count,
            'min_breach_count': min_breach_count,
            # 'details_url' to be set in the view
        }
    return summary

def get_breach_details(
    filename: str,
    breach_type: str = 'max',
    data_folder: str = "Data",
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    min_threshold: float = DEFAULT_MIN_THRESHOLD
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Returns a list of breaches of the specified type (max or min) for the given file.
    """
    breaches, total_count = find_value_breaches(
        filename, data_folder, max_threshold, min_threshold
    )
    filtered = [b for b in breaches if b['breach_type'] == breach_type]
    return filtered, total_count 