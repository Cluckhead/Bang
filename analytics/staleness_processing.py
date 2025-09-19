#!/usr/bin/env python
# staleness_processing.py
# This module contains the core logic for detecting stale data in securities files.
# It identifies securities as stale if the last N (threshold) non-null values are identical (within float tolerance),
# looking back from the most recent date columns. Only processes files with naming pattern sec_*.csv and sp_sec_*.csv.

import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from core import config

try:
    from core.config import DATA_FOLDER, ID_COLUMN
    if not DATA_FOLDER:
        raise ImportError("DATA_FOLDER not set")
except Exception:
    # Fall back to settings.yaml then default
    try:
        from core.settings_loader import get_app_config  # type: ignore
        app_cfg = get_app_config() or {}
        dfolder = app_cfg.get('data_folder') or 'Data'
        DATA_FOLDER = dfolder if os.path.isabs(dfolder) else os.path.join(os.path.dirname(__file__), dfolder)
    except Exception:
        DATA_FOLDER = "Data"
    try:
        from core.config import ID_COLUMN  # type: ignore
    except Exception:
        ID_COLUMN = "ISIN"

# Logging is now handled centrally by the Flask app factory in app.py
logger = logging.getLogger(__name__)

# Constants
FLOAT_TOLERANCE = 1e-6

# List of placeholder numeric values that indicate missing data (e.g., 100 used by data providers).
# Exposed as a public constant so that external tests/tools can import it safely.
DEFAULT_PLACEHOLDER_VALUES = config.STALENESS_PLACEHOLDERS

# Use config.STALENESS_PLACEHOLDERS for placeholder values in staleness detection


def get_staleness_summary(
    data_folder=DATA_FOLDER,
    exclusions_df=None,
    threshold_days=config.STALENESS_THRESHOLD_DAYS,
):
    """
    Generate a summary of stale data across all files in the data folder.
    """
    summary = {}
    try:
        for filename in os.listdir(data_folder):
            if filename.endswith(".csv") and (
                filename.startswith("sec_") or filename.startswith("sp_sec_")
            ):
                try:
                    file_path = os.path.join(data_folder, filename)
                    stale_securities, latest_date, total_count = (
                        get_stale_securities_details(
                            filename=filename,
                            data_folder=data_folder,
                            exclusions_df=exclusions_df,
                            threshold_days=threshold_days,
                        )
                    )
                    stale_count = len(stale_securities)
                    metric_name = filename.replace(".csv", "")
                    summary[filename] = {
                        "metric_name": metric_name,
                        "latest_date": latest_date,
                        "total_count": total_count,
                        "stale_count": stale_count,
                        "stale_percentage": (
                            round(stale_count / total_count * 100, 1)
                            if total_count > 0
                            else 0
                        ),
                    }
                    logger.debug(
                        f"File {filename}: Found {stale_count} stale out of {total_count} securities"
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing file {filename}: {e}", exc_info=True
                    )
                    summary[filename] = {
                        "metric_name": filename.replace(".csv", ""),
                        "latest_date": "Error",
                        "total_count": "Error",
                        "stale_count": f"Error: {str(e)}",
                        "stale_percentage": "Error",
                    }
    except Exception as e:
        logger.error(f"Error generating staleness summary: {e}", exc_info=True)
    return summary


def get_stale_securities_details(
    filename,
    data_folder=DATA_FOLDER,
    exclusions_df=None,
    threshold_days=config.STALENESS_THRESHOLD_DAYS,
):
    """
    Get detailed information about stale securities in a specific file.
    Flags a security as stale if the last N (threshold_days) non-null values are identical (within float tolerance),
    looking back from the most recent date columns. NaN/nulls are skipped.
    Sequences of zeros are NOT considered stale.
    """
    file_path = os.path.join(data_folder, filename)
    stale_securities = []
    latest_date = None
    total_count = 0
    
    # Counters for summary logging
    zero_sequence_count = 0
    stale_marked_count = 0
    stale_examples = []  # Store a few examples for logging
    
    try:
        df = pd.read_csv(file_path)
        metric_name = filename.replace(".csv", "")
        if ID_COLUMN not in df.columns:
            id_column = df.columns[0]
            logger.info(
                f"ID column '{ID_COLUMN}' not found in {filename}, using {id_column} instead."
            )
        else:
            id_column = ID_COLUMN
        meta_columns = df.columns[: len(config.METADATA_COLS)]
        date_columns = df.columns[len(config.METADATA_COLS) :]
        # Parse date columns for latest date
        date_objects = []
        for col in date_columns:
            try:
                date_obj = pd.to_datetime(col, errors="raise")
                date_objects.append(date_obj)
            except Exception:
                logger.warning(
                    f"Column {col} in {filename} doesn't appear to be a date."
                )
                date_objects.append(None)
        valid_dates = [d for d in date_objects if d is not None]
        if valid_dates:
            latest_date = max(valid_dates).strftime("%d/%m/%Y")
        else:
            latest_date = "Unknown"
        excluded_ids = []
        if exclusions_df is not None and not exclusions_df.empty:
            if id_column in exclusions_df.columns:
                excluded_ids = exclusions_df[id_column].astype(str).tolist()
            elif "SecurityID" in exclusions_df.columns:
                excluded_ids = exclusions_df["SecurityID"].astype(str).tolist()
            else:
                logger.warning(
                    f"Exclusions DataFrame does not contain expected ID column '{id_column}' or 'SecurityID'. No exclusions will be applied."
                )
        total_count = 0
        for idx, row in df.iterrows():
            security_id = str(row[id_column])
            if security_id in excluded_ids:
                continue
            total_count += 1
            static_info = {col: row[col] for col in meta_columns if col != id_column}
            date_values = row[date_columns].values
            # Only consider non-null values from the end
            non_null_values = [
                v
                for v in reversed(date_values)
                if not pd.isna(v)
                and str(v).strip().lower() not in {"n/a", "na", "", "null", "none"}
            ]
            if len(non_null_values) >= threshold_days:
                # last_n contains the last 'threshold_days' non-null values, in their original chronological order.
                last_n = list(reversed(non_null_values[:threshold_days]))
                
                if not last_n: # Should not happen if threshold_days > 0 and len >= threshold
                    continue

                ref_value = last_n[0] # The first value in the sequence of potentially identical values

                is_ref_numeric = False
                numeric_ref_val = 0.0
                try:
                    numeric_ref_val = float(ref_value)
                    is_ref_numeric = True
                except (ValueError, TypeError):
                    pass # ref_value is not numeric

                all_equal = True
                for val_item in last_n:
                    is_item_numeric = False
                    numeric_item_val = 0.0
                    try:
                        numeric_item_val = float(val_item)
                        is_item_numeric = True
                    except (ValueError, TypeError):
                        pass
                    
                    if is_ref_numeric and is_item_numeric:
                        if abs(numeric_item_val - numeric_ref_val) >= FLOAT_TOLERANCE:
                            all_equal = False
                            break
                    elif not is_ref_numeric and not is_item_numeric:
                        if str(val_item) != str(ref_value):
                            all_equal = False
                            break
                    else: # Mixed types (numeric vs non-numeric)
                        all_equal = False
                        break
                
                if all_equal:
                    is_repeating_zero = False
                    if is_ref_numeric and abs(numeric_ref_val) < FLOAT_TOLERANCE:
                        is_repeating_zero = True
                    
                    if is_repeating_zero:
                        zero_sequence_count += 1
                    else:
                        stale_type_detail = "last_n_identical_non_zero_numeric" if is_ref_numeric else "last_n_identical_non_numeric"
                        stale_marked_count += 1
                        
                        # Store example for logging (limit to first 3)
                        if len(stale_examples) < 3:
                            stale_examples.append({
                                'security_id': security_id,
                                'stale_type': stale_type_detail,
                                'repeating_value': ref_value,
                                'sequence': last_n
                            })
                        
                        stale_securities.append(
                            {
                                "id": security_id,
                                "metric_name": metric_name,
                                "static_info": static_info,
                                "last_update": date_columns[-threshold_days], # First date of the stale sequence
                                "days_stale": threshold_days, # Length of the stale sequence
                                "stale_type": stale_type_detail,
                                "repeating_value": ref_value # Actual repeating value
                            }
                        )
        
        # Summary logging
        logger.info(
            f"[{filename}] Processing complete: {total_count} securities analyzed, "
            f"{stale_marked_count} marked as stale, {zero_sequence_count} had zero sequences (not marked stale)"
        )
        
        # Log a few examples if any stale securities were found
        if stale_examples:
            logger.debug(f"[{filename}] Examples of stale securities detected:")
            for example in stale_examples:
                logger.debug(
                    f"  - {example['security_id']}: {example['stale_type']}, "
                    f"value='{example['repeating_value']}', sequence={example['sequence']}"
                )
        
    except Exception as e:
        logger.error(f"Error analyzing file {filename}: {e}", exc_info=True)
    return stale_securities, latest_date, total_count
