# This file provides functions for calculating various statistical metrics from the preprocessed data.
# Key functionalities include calculating historical statistics (mean, max, min), latest values,
# period-over-period changes, and Z-scores for changes for both benchmark and fund columns.
# It operates on a pandas DataFrame indexed by Date and Fund Code, producing a summary DataFrame
# containing these metrics for each fund, often sorted by the most significant recent changes (Z-scores).
# It now supports calculating metrics for both a primary and an optional secondary DataFrame.

# metric_calculator.py
# This file contains functions for calculating metrics from the processed data.
# Updated to handle primary and optional secondary data sources.

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
    col_name: str,
    prefix: str = "" # Optional prefix for metric names (e.g., "S&P " )
) -> Dict[str, Any]:
    """Helper function to calculate stats for a single column series.

    Calculates historical mean/max/min, latest value, latest change, and change z-score.
    Handles potential NaN values resulting from calculations or missing data gracefully.

    Args:
        col_series (pd.Series): The historical data for the column.
        col_change_series (pd.Series): The historical changes for the column.
        latest_date (pd.Timestamp): The overall latest date in the dataset.
        col_name (str): The name of the column being processed.
        prefix (str): A prefix to add to the metric names in the output dictionary.

    Returns:
        Dict[str, Any]: A dictionary containing the calculated metrics for this column.
    """
    metrics = {}

    # Calculate base historical stats for the column level
    # Pandas functions like mean, max, min typically handle NaNs by skipping them.
    metrics[f'{prefix}{col_name} Mean'] = col_series.mean()
    metrics[f'{prefix}{col_name} Max'] = col_series.max()
    metrics[f'{prefix}{col_name} Min'] = col_series.min()

    # Calculate stats for the column change
    change_mean = col_change_series.mean()
    change_std = col_change_series.std()

    # Get latest values if data exists for the latest date
    # Check if the latest_date exists in the specific series index
    if latest_date in col_series.index:
        latest_value = col_series.loc[latest_date]
        # Use .get() for change series to handle potential index mismatch (though unlikely if derived correctly)
        latest_change = col_change_series.get(latest_date, np.nan)

        metrics[f'{prefix}{col_name} Latest Value'] = latest_value
        metrics[f'{prefix}{col_name} Change'] = latest_change

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
             logger.debug(f"Standard deviation of change for '{prefix}{col_name}' is zero. Z-score set to {change_z_score}.")
        else:
            # Log if Z-score calculation couldn't be performed due to NaNs
            if not (pd.notna(latest_change) and pd.notna(change_mean) and pd.notna(change_std)):
                 logger.debug(f"Cannot calculate Z-score for '{prefix}{col_name}' due to NaN inputs (latest_change={latest_change}, change_mean={change_mean}, change_std={change_std})")

        metrics[f'{prefix}{col_name} Change Z-Score'] = change_z_score

    else:
        # Data for the latest date is missing for this specific column/fund
        logger.debug(f"Latest date {latest_date} not found for column '{prefix}{col_name}'. Setting latest metrics to NaN.")
        metrics[f'{prefix}{col_name} Latest Value'] = np.nan
        metrics[f'{prefix}{col_name} Change'] = np.nan
        metrics[f'{prefix}{col_name} Change Z-Score'] = np.nan

    return metrics

def _process_dataframe_metrics(
    df: pd.DataFrame,
    fund_codes: pd.Index,
    fund_cols: List[str],
    benchmark_col: Optional[str],
    latest_date: pd.Timestamp,
    metric_prefix: str = ""
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Processes a single DataFrame (primary or secondary) to calculate metrics.

    Args:
        df (pd.DataFrame): The DataFrame to process (already sorted by date index).
        fund_codes (pd.Index): Unique fund codes from the combined data.
        fund_cols (List[str]): List of original fund value column names for this df.
        benchmark_col (Optional[str]): Standardized benchmark column name for this df, if present.
        latest_date (pd.Timestamp): The latest date across combined data.
        metric_prefix (str): Prefix to add to metric names (e.g., "S&P ").

    Returns:
        Tuple[List[Dict[str, Any]], Dict[str, float]]:
            - List of metric dictionaries, one per fund.
            - Dictionary mapping fund code to its max absolute change Z-score for sorting.
    """
    if df is None or df.empty:
        logger.warning(f"Input DataFrame for prefix '{metric_prefix}' is None or empty. Returning empty results.")
        return [], {}

    # Determine which columns to actually process based on presence in df
    cols_to_process = []
    output_col_name_map = {} # Map processed col name to output name (original/std)

    if benchmark_col and benchmark_col in df.columns:
        cols_to_process.append(benchmark_col)
        output_col_name_map[benchmark_col] = benchmark_col
    elif benchmark_col:
        logger.warning(f"Specified {metric_prefix}benchmark column '{benchmark_col}' not found in DataFrame columns: {df.columns.tolist()}")

    for f_col in fund_cols:
        if f_col in df.columns:
            cols_to_process.append(f_col)
            output_col_name_map[f_col] = f_col
        else:
            logger.warning(f"Specified {metric_prefix}fund column '{f_col}' not found in DataFrame columns: {df.columns.tolist()}")

    if not cols_to_process:
        logger.error(f"No valid columns (benchmark or funds) found in the {metric_prefix}DataFrame to calculate metrics for.")
        return [], {}

    logger.info(f"Calculating {metric_prefix}metrics for columns: {cols_to_process}")

    fund_metrics_list = []
    max_abs_z_scores: Dict[str, float] = {}

    for fund_code in fund_codes:
        fund_specific_metrics: Dict[str, Any] = {'Fund Code': fund_code} # Initialize with Fund Code
        current_fund_max_abs_z: float = -1.0

        try:
            # Check if fund exists in this specific dataframe
            if fund_code not in df.index.get_level_values(1):
                logger.debug(f"Fund code '{fund_code}' not found in {metric_prefix}DataFrame. Adding empty metrics.")
                # Add NaN placeholders for all expected metrics for this source
                for col_name_proc in cols_to_process:
                    output_name = output_col_name_map[col_name_proc]
                    fund_specific_metrics[f'{metric_prefix}{output_name} Mean'] = np.nan
                    fund_specific_metrics[f'{metric_prefix}{output_name} Max'] = np.nan
                    fund_specific_metrics[f'{metric_prefix}{output_name} Min'] = np.nan
                    fund_specific_metrics[f'{metric_prefix}{output_name} Latest Value'] = np.nan
                    fund_specific_metrics[f'{metric_prefix}{output_name} Change'] = np.nan
                    fund_specific_metrics[f'{metric_prefix}{output_name} Change Z-Score'] = np.nan
                fund_metrics_list.append(fund_specific_metrics)
                max_abs_z_scores[fund_code] = np.nan # No Z-score if fund not present
                continue # Move to the next fund code

            # Extract data for the fund
            fund_data_hist = df.loc[(slice(None), fund_code), cols_to_process]
            fund_data_hist = fund_data_hist.reset_index(level=1, drop=True).sort_index()

            for col_name in cols_to_process:
                if col_name not in fund_data_hist.columns:
                    logger.warning(f"Column '{col_name}' unexpectedly not found for fund '{fund_code}' in {metric_prefix}DF. Skipping metrics.")
                    continue

                col_hist = fund_data_hist[col_name]
                col_change_hist = pd.Series(index=col_hist.index, dtype=np.float64)
                if not col_hist.dropna().empty and len(col_hist.dropna()) > 1:
                    col_change_hist = col_hist.diff()
                else:
                    logger.debug(f"Cannot calculate difference for {metric_prefix}column '{col_name}', fund '{fund_code}' due to insufficient data.")

                # Calculate stats for this specific column
                output_name = output_col_name_map[col_name]
                col_stats = _calculate_column_stats(col_hist, col_change_hist, latest_date, output_name, prefix=metric_prefix)
                fund_specific_metrics.update(col_stats)

                # Update the fund's max absolute Z-score *for this source*
                col_z_score = col_stats.get(f'{metric_prefix}{output_name} Change Z-Score', np.nan)
                compare_z_score = col_z_score
                if np.isinf(compare_z_score):
                    compare_z_score = 1e9 * np.sign(compare_z_score)
                if pd.notna(compare_z_score):
                    current_fund_max_abs_z = max(current_fund_max_abs_z, abs(compare_z_score))

            fund_metrics_list.append(fund_specific_metrics)
            max_abs_z_scores[fund_code] = current_fund_max_abs_z if current_fund_max_abs_z >= 0 else np.nan

        except Exception as e:
            logger.error(f"Error processing {metric_prefix}metrics for fund code '{fund_code}': {e}", exc_info=True)
            # Add placeholder with NaNs if error occurs mid-fund processing
            if 'Fund Code' not in fund_specific_metrics: # Ensure Fund Code is there
                fund_specific_metrics['Fund Code'] = fund_code
            # Add NaN placeholders for potentially missing metrics
            for col_name_proc in cols_to_process:
                output_name = output_col_name_map[col_name_proc]
                if f'{metric_prefix}{output_name} Mean' not in fund_specific_metrics: fund_specific_metrics[f'{metric_prefix}{output_name} Mean'] = np.nan
                if f'{metric_prefix}{output_name} Max' not in fund_specific_metrics: fund_specific_metrics[f'{metric_prefix}{output_name} Max'] = np.nan
                # ... (add for all metrics) ...
                if f'{metric_prefix}{output_name} Change Z-Score' not in fund_specific_metrics: fund_specific_metrics[f'{metric_prefix}{output_name} Change Z-Score'] = np.nan

            fund_metrics_list.append(fund_specific_metrics)
            max_abs_z_scores[fund_code] = np.nan # Mark as NaN for sorting if error occurred

    return fund_metrics_list, max_abs_z_scores

def calculate_latest_metrics(
    primary_df: Optional[pd.DataFrame],
    primary_fund_cols: Optional[List[str]],
    primary_benchmark_col: Optional[str],
    secondary_df: Optional[pd.DataFrame] = None,
    secondary_fund_cols: Optional[List[str]] = None,
    secondary_benchmark_col: Optional[str] = None,
    secondary_prefix: str = "S&P " # Prefix for secondary metrics
) -> pd.DataFrame:
    """Calculates latest metrics for primary and optional secondary data.

    Merges metrics from both sources based on Fund Code.
    Sorts the final DataFrame by the maximum absolute Z-score from the *primary* source.

    Args:
        primary_df (Optional[pd.DataFrame]): Primary processed DataFrame.
        primary_fund_cols (Optional[List[str]]): List of primary fund value column names.
        primary_benchmark_col (Optional[str]): Standardized primary benchmark column name.
        secondary_df (Optional[pd.DataFrame]): Secondary processed DataFrame. Defaults to None.
        secondary_fund_cols (Optional[List[str]]): List of secondary fund value column names. Defaults to None.
        secondary_benchmark_col (Optional[str]): Standardized secondary benchmark column name. Defaults to None.
        secondary_prefix (str): Prefix for secondary metric columns. Defaults to "S&P ".

    Returns:
        pd.DataFrame: Combined metrics indexed by Fund Code, sorted by primary max abs Z-score.
                      Returns an empty DataFrame if primary data is missing or processing fails critically.
    """
    if primary_df is None or primary_df.empty or primary_fund_cols is None:
        logger.warning("Primary DataFrame or fund columns are missing. Cannot calculate metrics.")
        return pd.DataFrame()

    if primary_df.index.nlevels != 2:
        logger.error("Primary DataFrame must have a MultiIndex with 2 levels (Date, Fund Code).")
        return pd.DataFrame()

    # Combine fund codes and find the overall latest date
    all_dfs = [df for df in [primary_df, secondary_df] if df is not None and not df.empty]
    if not all_dfs:
        logger.warning("No valid DataFrames provided. Cannot calculate metrics.")
        return pd.DataFrame()

    try:
        combined_index = pd.concat(all_dfs).index
        latest_date = combined_index.get_level_values(0).max()
        fund_codes = combined_index.get_level_values(1).unique()
        # Ensure DataFrames are sorted by date index for diff calculation
        primary_df_sorted = primary_df.sort_index(level=0)
        secondary_df_sorted = secondary_df.sort_index(level=0) if secondary_df is not None else None

    except Exception as e:
        logger.error(f"Error preparing combined data for metric calculation: {e}", exc_info=True)
        return pd.DataFrame()

    # --- Calculate Metrics for Primary Data --- #
    primary_metrics_list, primary_max_abs_z = _process_dataframe_metrics(
        primary_df_sorted,
        fund_codes, # Use combined fund codes
        primary_fund_cols,
        primary_benchmark_col,
        latest_date,
        metric_prefix="" # No prefix for primary
    )

    # --- Calculate Metrics for Secondary Data (if present) --- #
    secondary_metrics_list = []
    if secondary_df_sorted is not None and secondary_fund_cols is not None:
        logger.info(f"Processing secondary data with prefix: '{secondary_prefix}'")
        secondary_metrics_list, _ = _process_dataframe_metrics(
            secondary_df_sorted,
            fund_codes, # Use combined fund codes
            secondary_fund_cols,
            secondary_benchmark_col,
            latest_date,
            metric_prefix=secondary_prefix
        )
    else:
        logger.info("No valid secondary data provided or fund columns missing, skipping secondary metrics.")

    # --- Combine Metrics --- #
    if not primary_metrics_list:
        logger.warning("Primary metric calculation resulted in empty list. Returning empty DataFrame.")
        return pd.DataFrame()

    # Convert lists of dicts to DataFrames
    primary_metrics_df = pd.DataFrame(primary_metrics_list).set_index('Fund Code')

    if secondary_metrics_list:
        secondary_metrics_df = pd.DataFrame(secondary_metrics_list).set_index('Fund Code')
        # Merge based on Fund Code index, keeping all funds (outer merge)
        combined_metrics_df = primary_metrics_df.merge(
            secondary_metrics_df, left_index=True, right_index=True, how='outer'
        )
    else:
        combined_metrics_df = primary_metrics_df

    # --- Sort Results --- #
    # Add the primary max abs Z-score as a temporary column for sorting
    # Use .get() on the dictionary to handle funds potentially missing from primary results
    combined_metrics_df['_sort_z'] = combined_metrics_df.index.map(lambda fc: primary_max_abs_z.get(fc, np.nan))

    # Sort by the temporary Z-score column (descending), put NaNs last
    combined_metrics_df_sorted = combined_metrics_df.sort_values(by='_sort_z', ascending=False, na_position='last')

    # Drop the temporary sorting column
    combined_metrics_df_sorted = combined_metrics_df_sorted.drop(columns=['_sort_z'])

    logger.info(f"Successfully calculated and combined metrics. Final shape: {combined_metrics_df_sorted.shape}")
    return combined_metrics_df_sorted 