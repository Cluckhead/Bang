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
from typing import List, Dict, Any, Tuple, Optional

# Configure logging (can be configured globally elsewhere if part of a larger app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _calculate_column_stats(
    col_series: pd.Series,
    col_change_series: pd.Series,
    latest_date: pd.Timestamp,
    col_name: str
) -> Dict[str, Any]:
    """Helper function to calculate stats for a single column series.

    Calculates historical mean/max/min, latest value, latest change, and change z-score.

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
    metrics[f'{col_name} Mean'] = col_series.mean()
    metrics[f'{col_name} Max'] = col_series.max()
    metrics[f'{col_name} Min'] = col_series.min()

    # Calculate stats for the column change
    change_mean = col_change_series.mean()
    change_std = col_change_series.std()

    # Get latest values if data exists for the latest date
    if latest_date in col_series.index:
        latest_value = col_series.loc[latest_date]
        latest_change = col_change_series.loc[latest_date] # Get change for the latest date

        metrics[f'{col_name} Latest Value'] = latest_value
        metrics[f'{col_name} Change'] = latest_change

        # Calculate Change Z-Score: (latest_change - change_mean) / change_std
        # Z-score indicates how many standard deviations the latest change is from the mean change.
        change_z_score = np.nan # Default to NaN
        if change_std is not None and change_std != 0 and pd.notna(change_std) and pd.notna(latest_change) and pd.notna(change_mean):
            change_z_score = (latest_change - change_mean) / change_std

        metrics[f'{col_name} Change Z-Score'] = change_z_score

    else:
        # Data for the latest date is missing for this specific column/fund
        metrics[f'{col_name} Latest Value'] = np.nan
        metrics[f'{col_name} Change'] = np.nan
        metrics[f'{col_name} Change Z-Score'] = np.nan

    return metrics

def calculate_latest_metrics(
    df: pd.DataFrame,
    fund_cols: List[str],
    benchmark_col: str
) -> pd.DataFrame:
    """Calculates latest metrics for each individual column (benchmark and funds) per fund code.

    For each fund code and for each relevant column (benchmark and funds),
    it calculates: Latest Value, Change, Mean, Max, Min, and Change Z-Score.

    Args:
        df (pd.DataFrame): Processed DataFrame indexed by Date (level 0) and Fund Code (level 1).
                           Assumes date index is sorted ascendingly within each fund code.
        fund_cols (List[str]): List of fund value column names.
        benchmark_col (str): Name of the benchmark value column.

    Returns:
        pd.DataFrame: Flattened metrics indexed by Fund Code.
                      Columns are named like '{col_name} Latest Value', '{col_name} Change', etc.
                      The DataFrame is sorted by the maximum absolute 'Change Z-Score' found
                      across all columns for each fund, in descending order.
                      Funds with no Z-scores (e.g., due to missing data or zero std dev)
                      are placed at the end.
    """
    if df.index.nlevels != 2:
        raise ValueError("Input DataFrame must have a MultiIndex with 2 levels (Date, Fund Code).")

    # Ensure the date level is sorted for correct .diff() calculation
    df_sorted = df.sort_index(level=0)

    latest_date = df_sorted.index.get_level_values(0).max()
    fund_codes = df_sorted.index.get_level_values(1).unique()
    cols_to_process = [benchmark_col] + fund_cols # Process benchmark first, then funds

    all_metrics_list = []
    # Store the maximum absolute change z-score *per fund* across all its columns for sorting purposes
    max_abs_change_z_scores: Dict[str, float] = {}

    for fund_code in fund_codes:
        try:
            # Extract historical data for the specific fund code
            # .xs drops the level, providing a DataFrame indexed by Date
            fund_data_hist = df_sorted.xs(fund_code, level=1)
        except KeyError:
            logging.warning(f"Fund code '{fund_code}' not found in DataFrame index. Skipping.")
            continue

        # Initialize metrics for this fund
        fund_metrics: Dict[str, Any] = {'Fund Code': fund_code}
        current_fund_max_abs_z: float = -1.0 # Use -1 to handle cases where all Zs are NaN

        for col_name in cols_to_process:
            if col_name not in fund_data_hist.columns:
                logging.warning(f"Column '{col_name}' not found for fund '{fund_code}'. Skipping metrics for this column.")
                # Add NaN placeholders for this column for this fund to maintain structure
                metric_keys = ['Latest Value', 'Change', 'Mean', 'Max', 'Min', 'Change Z-Score']
                for key in metric_keys:
                    fund_metrics[f'{col_name} {key}'] = np.nan
                continue # Skip to the next column for this fund

            # Get the specific column's historical data and calculate its difference
            col_hist = fund_data_hist[col_name]
            col_change_hist = col_hist.diff()

            # Calculate stats for this specific column
            col_stats = _calculate_column_stats(col_hist, col_change_hist, latest_date, col_name)
            fund_metrics.update(col_stats)

            # Update the fund's overall max absolute Z-score if this column's Z-score is valid and larger
            col_z_score = col_stats.get(f'{col_name} Change Z-Score', np.nan)
            if pd.notna(col_z_score):
                current_fund_max_abs_z = max(current_fund_max_abs_z, abs(col_z_score))

        # Store the calculated metrics dictionary for this fund
        all_metrics_list.append(fund_metrics)
        # Store the max abs change Z-score found for this fund across all its columns
        max_abs_change_z_scores[fund_code] = current_fund_max_abs_z

    # --- Post-processing --- 
    if not all_metrics_list:
        logging.warning("No funds were processed. Returning empty DataFrame.")
        return pd.DataFrame()

    # Create DataFrame from the list of metric dictionaries
    latest_metrics_df = pd.DataFrame(all_metrics_list).set_index('Fund Code')

    # Sort the DataFrame based on the calculated max absolute Z-scores
    # Create a Series from the max_abs_change_z_scores dict, align its index with the DataFrame
    # then sort the DataFrame based on the values of this series.
    sort_series = pd.Series(max_abs_change_z_scores).reindex(latest_metrics_df.index)
    # Sort descending, NaNs (represented by -1 here) go last
    latest_metrics_df_sorted = latest_metrics_df.reindex(sort_series.sort_values(ascending=False).index)

    logging.info(f"Successfully calculated metrics for {len(latest_metrics_df_sorted)} funds.")
    return latest_metrics_df_sorted 