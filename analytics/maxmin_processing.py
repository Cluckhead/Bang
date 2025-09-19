# Purpose: This file processes max/min threshold checks for security data, using configuration for metadata columns and thresholds.
# This module contains the core logic for identifying securities
# that breach predefined maximum or minimum value thresholds.
# It reads configuration from config.py and processes specified security-level data files (sec_*.csv)
# to find values outside the configured bounds, providing data for the dashboard and detail views.

import os
import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional
from core import config

# Default thresholds (used if not specified in config or overrides)
DEFAULT_MAX_THRESHOLD = 10000
DEFAULT_MIN_THRESHOLD = -100

# Metadata columns (same as staleness_processing.py)
# Replace any use of hardcoded META_COLS = 6 with config.METADATA_COLS
# Example: instead of using a fixed number, use len(config.METADATA_COLS) or the list itself for column selection

# Import the config dictionary
# from config import MAXMIN_THRESHOLDS

logger = logging.getLogger(__name__)


def _load_distressed_isins(data_folder: str) -> set:
    """
    Loads the set of ISINs from reference.csv where 'Is Distressed' is TRUE.
    Returns a set of ISIN strings.
    """
    distressed_isins = set()
    ref_path = os.path.join(data_folder, "reference.csv")
    if not os.path.exists(ref_path):
        return distressed_isins
    try:
        df = pd.read_csv(ref_path, dtype=str)
        if "ISIN" in df.columns and "Is Distressed" in df.columns:
            # Normalize and filter
            mask = df["Is Distressed"].astype(str).str.strip().str.upper() == "TRUE"
            distressed_isins = set(
                df.loc[mask, "ISIN"].astype(str).str.strip().str.upper()
            )
    except Exception as e:
        logger.warning(
            f"Could not load or parse reference.csv for distressed ISINs: {e}"
        )
    return distressed_isins


def find_value_breaches(
    filename: str,
    data_folder: str = "Data",
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    min_threshold: float = DEFAULT_MIN_THRESHOLD,
    include_distressed: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Scan a security-level file for values above max_threshold or below min_threshold.
    Ignores NaN/null values. Returns a list of breaches and total securities checked.
    Excludes securities marked as distressed in reference.csv unless include_distressed is True.
    """
    file_path = os.path.join(data_folder, filename)
    breaches = []
    total_count = 0
    distressed_isins = (
        _load_distressed_isins(data_folder) if not include_distressed else set()
    )
    try:
        df = pd.read_csv(file_path)
        id_column = df.columns[0]  # ISIN
        meta_columns = df.columns[: len(config.METADATA_COLS)]
        date_columns = df.columns[len(config.METADATA_COLS) :]
        total_count = len(df)
        for idx, row in df.iterrows():
            # Normalize ISIN for comparison
            security_id = str(row[id_column]).strip().upper()
            if not include_distressed and security_id in distressed_isins:
                continue  # Exclude distressed
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
                    breaches.append(
                        {
                            "id": security_id,
                            "static_info": static_info,
                            "date": date_col,
                            "value": num_val,
                            "breach_type": "max",
                            "threshold": max_threshold,
                            "file": filename,
                        }
                    )
                elif num_val < min_threshold:
                    breaches.append(
                        {
                            "id": security_id,
                            "static_info": static_info,
                            "date": date_col,
                            "value": num_val,
                            "breach_type": "min",
                            "threshold": min_threshold,
                            "file": filename,
                        }
                    )
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}", exc_info=True)
    return breaches, total_count


def get_breach_summary(
    data_folder: str,
    threshold_config: Dict[
        str, Dict[str, Any]
    ],  # Pass the relevant subset of MAXMIN_THRESHOLDS
    override_max: Optional[float] = None,
    override_min: Optional[float] = None,
    include_distressed: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Returns a summary for each file defined in the provided threshold_config.
    Uses override thresholds if provided, otherwise uses thresholds from the config.

    Args:
        data_folder: Path to the data directory.
        threshold_config: A dictionary (subset of MAXMIN_THRESHOLDS) containing the files
                          and their configurations (min, max, display_name, group) to process.
        override_max: If provided, use this value as the max threshold for all files.
        override_min: If provided, use this value as the min threshold for all files.
        include_distressed: If True, include securities marked as distressed in the summary.

    Returns:
        A dictionary where keys are filenames and values are summaries containing:
        - filename: The name of the file checked.
        - display_name: User-friendly name from config.
        - total_count: total securities checked.
        - max_breach_count: number of max breaches using the applied threshold.
        - min_breach_count: number of min breaches using the applied threshold.
        - max_threshold: The actual maximum threshold used (override or config).
        - min_threshold: The actual minimum threshold used (override or config).
        - has_error: Boolean indicating if processing failed for this file.
    """
    summary = {}
    for filename, config in threshold_config.items():
        # Determine the thresholds to use: override or config default
        if override_max is not None:
            applied_max_threshold = override_max
        else:
            applied_max_threshold = config.get("max", DEFAULT_MAX_THRESHOLD)

        if override_min is not None:
            applied_min_threshold = override_min
        else:
            applied_min_threshold = config.get("min", DEFAULT_MIN_THRESHOLD)

        display_name = config.get("display_name", filename)

        try:
            # Use the determined thresholds
            breaches, total_count = find_value_breaches(
                filename,
                data_folder,
                applied_max_threshold,
                applied_min_threshold,
                include_distressed=include_distressed,
            )
            max_breach_count = sum(1 for b in breaches if b["breach_type"] == "max")
            min_breach_count = sum(1 for b in breaches if b["breach_type"] == "min")
            has_error = False
        except FileNotFoundError:
            logger.warning(
                f"File not found for Max/Min check: {os.path.join(data_folder, filename)}. Skipping."
            )
            total_count = 0
            max_breach_count = 0
            min_breach_count = 0
            has_error = True
        except Exception as e:
            logger.error(f"Error processing {filename} for summary: {e}", exc_info=True)
            total_count = 0
            max_breach_count = 0
            min_breach_count = 0
            has_error = True

        summary[filename] = {
            "filename": filename,
            "display_name": display_name,
            "total_count": total_count,
            "max_breach_count": max_breach_count,
            "min_breach_count": min_breach_count,
            "max_threshold": applied_max_threshold,  # Report the threshold actually used
            "min_threshold": applied_min_threshold,  # Report the threshold actually used
            "has_error": has_error,  # Indicate if processing failed
            # Add detailed breach information for ticket generation
            "max_breaches": [
                {"ISIN": b["id"], "value": b["value"], "threshold": b["threshold"]} 
                for b in (breaches if not has_error else []) if b["breach_type"] == "max"
            ],
            "min_breaches": [
                {"ISIN": b["id"], "value": b["value"], "threshold": b["threshold"]} 
                for b in (breaches if not has_error else []) if b["breach_type"] == "min"
            ],
            # 'details_url' will be added in the view
        }
    return summary


def get_breach_details(
    filename: str,
    breach_type: str = "max",
    data_folder: str = "Data",
    max_threshold: float = DEFAULT_MAX_THRESHOLD,
    min_threshold: float = DEFAULT_MIN_THRESHOLD,
    include_distressed: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Returns a list of breaches of the specified type (max or min) for the given file.
    Aggregates by security, counting the number of days breaching.
    """
    breaches, total_count = find_value_breaches(
        filename,
        data_folder,
        max_threshold,
        min_threshold,
        include_distressed=include_distressed,
    )
    filtered = [b for b in breaches if b["breach_type"] == breach_type]
    # Aggregate by security id
    agg = {}
    for b in filtered:
        sec_id = b["id"]
        if sec_id not in agg:
            agg[sec_id] = {
                "id": sec_id,
                "static_info": b["static_info"],
                "count": 0,
                "dates": [],
                "values": [],
                "breach_type": b["breach_type"],
                "threshold": b["threshold"],
                "file": b["file"],
            }
        agg[sec_id]["count"] += 1
        agg[sec_id]["dates"].append(b["date"])
        agg[sec_id]["values"].append(b["value"])
    # Prepare output: one row per security
    result = list(agg.values())
    return result, total_count
