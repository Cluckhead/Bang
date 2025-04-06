# This file provides functions for calculating various statistical metrics from the preprocessed data.
# Key functionalities include calculating historical statistics (mean, max, min), latest values,
# period-over-period changes, and Z-scores for changes for both benchmark and fund columns.
# It operates on a pandas DataFrame indexed by Date and Fund Code, producing a summary DataFrame
# containing these metrics for each fund, often sorted by the most significant recent changes (Z-scores).

# metric_calculator.py
# This file contains functions for calculating metrics from the processed data.

import pandas as pd
import numpy as np
import logging
import os # Needed for logging setup
from typing import List, Dict, Any, Tuple, Optional

# --- Logging Setup ---
# Use the same log file as data_loader
LOG_FILENAME = 'data_processing_errors.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Get the logger for the current module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Prevent adding handlers multiple times (especially if imported by other modules)
if not logger.handlers:
    # Console Handler (INFO and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter(LOG_FORMAT)
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    # File Handler (WARNING and above)
    try:
        # Create log file path relative to this file's location
        log_filepath = os.path.join(os.path.dirname(__file__), '..', LOG_FILENAME)
        fh = logging.FileHandler(log_filepath, mode='a')
        fh.setLevel(logging.WARNING)
        fh_formatter = logging.Formatter(LOG_FORMAT)
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)
    except Exception as e:
        # Log to stderr if file logging setup fails
        import sys
        print(f"Error setting up file logging for metric_calculator: {e}", file=sys.stderr)
# --- End Logging Setup ---

# Configure logging (can be configured globally elsewhere if part of a larger app)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _calculate_column_stats(
    col_series: pd.Series,
    col_change_series: pd.Series,
    latest_date: pd.Timestamp,
    col_name: str
) -> Dict[str, Any]:
    """Helper function to calculate stats for a single column series.

    Calculates historical mean/max/min, latest value, latest change, and change z-score.
    Handles potential NaN values resulting from calculations or missing data gracefully.

    Args:
        col_series (pd.Series): The historical data for the column.
        col_change_series (pd.Series): The historical changes for the column.
        latest_date (pd.Timestamp): The overall latest date in the dataset.
        col_name (str): The name of the column being processed.

    Returns:
        Dict[str, Any]: A dictionary containing the calculated metrics for this column.
    """
    metrics = {}

    # Calculate base historical stats for the column level
    # Pandas functions like mean, max, min typically handle NaNs by skipping them.
    metrics[f'{col_name} Mean'] = col_series.mean()
    metrics[f'{col_name} Max'] = col_series.max()
    metrics[f'{col_name} Min'] = col_series.min()

    # Calculate stats for the column change
    change_mean = col_change_series.mean()
    change_std = col_change_series.std()

    # Get latest values if data exists for the latest date
    # Check if the latest_date exists in the specific series index
    if latest_date in col_series.index:
        latest_value = col_series.loc[latest_date]
        # Use .get() for change series to handle potential index mismatch (though unlikely if derived correctly)
        latest_change = col_change_series.get(latest_date, np.nan)

        metrics[f'{col_name} Latest Value'] = latest_value
        metrics[f'{col_name} Change'] = latest_change

        # Calculate Change Z-Score: (latest_change - change_mean) / change_std
        change_z_score = np.nan # Default to NaN
        if pd.notna(latest_change) and pd.notna(change_mean) and pd.notna(change_std) and change_std != 0:
            change_z_score = (latest_change - change_mean) / change_std
        elif change_std == 0 and pd.notna(latest_change) and pd.notna(change_mean):
             # Handle case where std dev is zero (e.g., constant series)
             if latest_change == change_mean:
                 change_z_score = 0.0 # No deviation
             else:
                 change_z_score = np.inf if latest_change > change_mean else -np.inf # Infinite deviation
             logger.debug(f"Standard deviation of change for '{col_name}' is zero. Z-score set to {change_z_score}.")
        else:
            # Log if Z-score calculation couldn't be performed due to NaNs
            if not (pd.notna(latest_change) and pd.notna(change_mean) and pd.notna(change_std)):
                 logger.debug(f"Cannot calculate Z-score for '{col_name}' due to NaN inputs (latest_change={latest_change}, change_mean={change_mean}, change_std={change_std})")

        metrics[f'{col_name} Change Z-Score'] = change_z_score

    else:
        # Data for the latest date is missing for this specific column/fund
        logger.debug(f"Latest date {latest_date} not found for column '{col_name}'. Setting latest metrics to NaN.")
        metrics[f'{col_name} Latest Value'] = np.nan
        metrics[f'{col_name} Change'] = np.nan
        metrics[f'{col_name} Change Z-Score'] = np.nan

    return metrics

def calculate_latest_metrics(
    df: pd.DataFrame,
    fund_cols: List[str],
    benchmark_col: Optional[str] # Allow benchmark_col to be None
) -> pd.DataFrame:
    """Calculates latest metrics for each individual column (benchmark and funds) per fund code.

    For each fund code and for each relevant column (benchmark and funds),
    it calculates: Latest Value, Change, Mean, Max, Min, and Change Z-Score.

    Args:
        df (pd.DataFrame): Processed DataFrame indexed by Date (level 0) and Fund Code (level 1).
                           Assumes date index is sorted ascendingly within each fund code.
        fund_cols (List[str]): List of fund value column names (original names from loader).
        benchmark_col (Optional[str]): Name of the *standardized* benchmark value column ('Benchmark'), or None if not present.

    Returns:
        pd.DataFrame: Flattened metrics indexed by Fund Code.
                      Columns are named like '{col_name} Latest Value', '{col_name} Change', etc.
                      (Note: Uses original fund column names and standardized benchmark name in output cols).
                      The DataFrame is sorted by the maximum absolute 'Change Z-Score' found
                      across all columns for each fund, in descending order.
                      Funds with no Z-scores (e.g., due to missing data or zero std dev)
                      are placed at the end.
    """
    if df is None or df.empty:
        logger.warning("Input DataFrame is None or empty. Cannot calculate metrics.")
        return pd.DataFrame()
    
    if df.index.nlevels != 2:
        logger.error("Input DataFrame must have a MultiIndex with 2 levels (Date, Fund Code).")
        # Consider raising ValueError or returning empty DataFrame? Let's return empty for resilience.
        return pd.DataFrame()

    # Ensure the date level is sorted for correct .diff() calculation
    try:
        df_sorted = df.sort_index(level=0)
        latest_date = df_sorted.index.get_level_values(0).max()
        fund_codes = df_sorted.index.get_level_values(1).unique()
    except Exception as e:
         logger.error(f"Error preparing DataFrame for metric calculation (sorting/indexing): {e}", exc_info=True)
         return pd.DataFrame()

    # Determine which columns to actually process based on presence in df
    cols_to_process = []
    output_col_name_map = {} # Map processed col name (potentially std) to output name (original/std)
    
    if benchmark_col and benchmark_col in df_sorted.columns:
        cols_to_process.append(benchmark_col) # Use the standardized name for processing
        output_col_name_map[benchmark_col] = benchmark_col # Output name is the same std name
    elif benchmark_col:
        logger.warning(f"Specified benchmark column '{benchmark_col}' not found in DataFrame columns: {df_sorted.columns.tolist()}")
        
    # Use the *original* fund column names provided by the loader
    for f_col in fund_cols:
        if f_col in df_sorted.columns:
            cols_to_process.append(f_col)
            output_col_name_map[f_col] = f_col # Output name is the original fund name
        else:
            logger.warning(f"Specified fund column '{f_col}' not found in DataFrame columns: {df_sorted.columns.tolist()}")

    if not cols_to_process:
        logger.error("No valid columns (benchmark or funds) found in the DataFrame to calculate metrics for.")
        return pd.DataFrame()

    logger.info(f"Calculating metrics for columns: {cols_to_process}")

    all_metrics_list = []
    # Store the maximum absolute change z-score *per fund* across all its columns for sorting purposes
    max_abs_change_z_scores: Dict[str, float] = {}

    for fund_code in fund_codes:
        try:
            # Extract historical data for the specific fund code
            # .xs drops the level, providing a DataFrame indexed by Date
            # Use .loc to avoid potential KeyError if fund_code doesn't exist
            if fund_code not in df_sorted.index.get_level_values(1):
                 logger.warning(f"Fund code '{fund_code}' not found in DataFrame index level 1. Skipping.")
                 continue
            # Select only columns we intend to process to avoid carrying unused data
            fund_data_hist = df_sorted.loc[(slice(None), fund_code), cols_to_process]
            # After .loc, the index might still be MultiIndex if only one fund exists, reset to Date
            fund_data_hist = fund_data_hist.reset_index(level=1, drop=True).sort_index()

        except Exception as e: # Catch broader errors during data extraction
            logger.error(f"Error extracting data for fund code '{fund_code}': {e}", exc_info=True)
            continue

        # Initialize metrics for this fund
        fund_metrics: Dict[str, Any] = {'Fund Code': fund_code}
        current_fund_max_abs_z: float = -1.0 # Use -1 to handle cases where all Zs are NaN or non-positive

        for col_name in cols_to_process:
            # This check should be redundant now due to filtering `cols_to_process` above, but keep as safeguard
            if col_name not in fund_data_hist.columns:
                logger.warning(f"Column '{col_name}' unexpectedly not found for fund '{fund_code}' after filtering. Skipping metrics.")
                continue

            # Get the specific column's historical data and calculate its difference
            col_hist = fund_data_hist[col_name]
            # Calculate diff only if series is not empty and has more than one non-NaN value
            col_change_hist = pd.Series(index=col_hist.index, dtype=np.float64) # Initialize with NaNs
            if not col_hist.dropna().empty and len(col_hist.dropna()) > 1:
                 col_change_hist = col_hist.diff()
            else:
                 logger.debug(f"Cannot calculate difference for column '{col_name}', fund '{fund_code}' due to insufficient data.")
                 

            # Calculate stats for this specific column
            # Use the mapped output name for the metric dictionary keys
            output_name = output_col_name_map[col_name]
            col_stats = _calculate_column_stats(col_hist, col_change_hist, latest_date, output_name)
            fund_metrics.update(col_stats)

            # Update the fund's overall max absolute Z-score if this column's Z-score is valid and larger
            col_z_score = col_stats.get(f'{output_name} Change Z-Score', np.nan)
            # Replace inf/-inf with a large number for sorting comparison, but keep original in metrics
            compare_z_score = col_z_score
            if np.isinf(compare_z_score):
                compare_z_score = 1e9 * np.sign(compare_z_score) # Large number with correct sign
                
            if pd.notna(compare_z_score):
                current_fund_max_abs_z = max(current_fund_max_abs_z, abs(compare_z_score))

        # Store the calculated metrics dictionary for this fund
        all_metrics_list.append(fund_metrics)
        # Store the max abs change Z-score found for this fund across all its columns
        # Use the potentially modified value (inf replaced) for sorting
        max_abs_change_z_scores[fund_code] = current_fund_max_abs_z if current_fund_max_abs_z >= 0 else np.nan

    # --- Post-processing --- 
    if not all_metrics_list:
        logger.warning("No funds were processed successfully. Returning empty DataFrame.")
        return pd.DataFrame()

    # Create DataFrame from the list of metric dictionaries
    try:
        latest_metrics_df = pd.DataFrame(all_metrics_list).set_index('Fund Code')
    except Exception as e:
         logger.error(f"Error creating final metrics DataFrame: {e}", exc_info=True)
         return pd.DataFrame()

    # Sort the DataFrame based on the calculated max absolute Z-scores
    # Create a Series from the max_abs_change_z_scores dict, align its index with the DataFrame
    # then sort the DataFrame based on the values of this series.
    try:
        sort_series = pd.Series(max_abs_change_z_scores).reindex(latest_metrics_df.index)
        # Sort descending, NaNs go last
        latest_metrics_df_sorted = latest_metrics_df.reindex(sort_series.sort_values(ascending=False, na_position='last').index)
    except Exception as e:
        logger.error(f"Error sorting metrics DataFrame: {e}", exc_info=True)
        latest_metrics_df_sorted = latest_metrics_df # Return unsorted if sorting fails

    logger.info(f"Successfully calculated metrics for {len(latest_metrics_df_sorted)} funds.")
    return latest_metrics_df_sorted 