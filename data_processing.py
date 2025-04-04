# This file contains functions for loading and processing the data.
import pandas as pd
import os
import numpy as np # Import numpy for NaN handling

DATA_FOLDER = 'Data'

def load_and_process_data(filename):
    """Loads a CSV file, identifies key columns, parses dates, sets index, and ensures numeric types.

    Assumes the structure:
    Column 0: Date identifier
    Column 1: Fund Code identifier
    Column 2: First Fund Value
    Column 3: Benchmark Value
    Column 4+: Optional additional Fund Values

    Returns:
        tuple: (pandas.DataFrame, list[str], str):
               Processed DataFrame, list of fund column names, benchmark column name.
    """
    filepath = os.path.join(DATA_FOLDER, filename)
    header_df = pd.read_csv(filepath, nrows=0)
    original_cols = header_df.columns.tolist()

    if len(original_cols) < 4:
        raise ValueError(f"File '{filename}' must have at least 4 columns (Date, Code, Fund Value, Benchmark Value).")

    # --- Identify column names --- 
    date_col_name = original_cols[0]
    fund_code_col_name = original_cols[1]
    # Assume benchmark is column 3
    benchmark_val_col_name = original_cols[3].strip()
    # All other columns (except date and code) are treated as fund values
    fund_val_col_names = [col.strip() for i, col in enumerate(original_cols) 
                            if i != 0 and i != 1]
    
    # Ensure benchmark column is not accidentally included in fund columns if file structure changes
    if benchmark_val_col_name in fund_val_col_names:
        fund_val_col_names.remove(benchmark_val_col_name)
        # Re-add it separately if it wasn't column 3 (handle edge case)
        if original_cols[3].strip() != benchmark_val_col_name:
             print(f"Warning: Identified benchmark column '{benchmark_val_col_name}' was not in expected position 3.")
    else: 
        # If benchmark col wasn't in the list (i.e., it was col 0 or 1), raise error
         if benchmark_val_col_name == date_col_name or benchmark_val_col_name == fund_code_col_name:
              raise ValueError(f"Benchmark column '{benchmark_val_col_name}' cannot be the same as Date or Fund Code column.")
         # Otherwise, if benchmark wasn't col 3 and not in fund list, something is wrong
         elif original_cols[3].strip() != benchmark_val_col_name:
             raise ValueError(f"Could not reliably identify benchmark column '{benchmark_val_col_name}'. Expected at index 3.")

    # Read the full CSV
    df = pd.read_csv(filepath, parse_dates=[date_col_name], dayfirst=True)
    df.columns = df.columns.str.strip()
    df.set_index([date_col_name, fund_code_col_name], inplace=True)

    # Convert all identified fund value columns AND the benchmark column to numeric
    value_cols_to_convert = fund_val_col_names + [benchmark_val_col_name]
    df[value_cols_to_convert] = df[value_cols_to_convert].apply(pd.to_numeric, errors='coerce')

    # Return the DataFrame, LIST of fund columns, and the benchmark column
    return df, fund_val_col_names, benchmark_val_col_name

# Modify calculate_latest_metrics to handle multiple fund columns
def calculate_latest_metrics(df, fund_cols, benchmark_col):
    """Calculates metrics for the latest data point, focusing on spreads for multiple fund columns.

    Args:
        df (pd.DataFrame): Processed DataFrame.
        fund_cols (list[str]): List of fund value column names.
        benchmark_col (str): Name of the benchmark value column.

    Returns:
        pandas.DataFrame: Metrics including spreads and Z-scores for all fund columns,
                          indexed by Fund Code, sorted by the MAX absolute Z-Score across columns.
    """
    latest_date = df.index.get_level_values(0).max()
    fund_codes = df.index.get_level_values(1).unique()

    latest_metrics_list = []
    max_abs_z_scores = {} # To store max Z-score for sorting

    for fund_code in fund_codes:
        fund_data_hist = df.xs(fund_code, level=1).sort_index()
        metrics = {'Fund Code': fund_code}
        current_max_abs_z = 0.0
        has_latest_data = latest_date in fund_data_hist.index

        # Store latest benchmark value once
        if has_latest_data:
            metrics[f'Latest {benchmark_col}'] = fund_data_hist.loc[latest_date, benchmark_col]
        else:
            metrics[f'Latest {benchmark_col}'] = np.nan

        # Calculate metrics for EACH fund column
        for fund_col in fund_cols:
            spread_col_name = f'{fund_col} Spread'
            z_score_col_name = f'{spread_col_name} Z-Score'
            fund_change_col_name = f'{fund_col} Change'
            spread_change_col_name = f'{spread_col_name} Change'
            hist_mean_col_name = f'{spread_col_name} Mean'
            hist_std_dev_col_name = f'{spread_col_name} Std Dev'

            # Calculate spread for this column
            fund_data_hist[spread_col_name] = fund_data_hist[fund_col] - fund_data_hist[benchmark_col]

            historical_spread = fund_data_hist[spread_col_name]
            spread_mean = historical_spread.mean()
            spread_std = historical_spread.std()

            metrics[hist_mean_col_name] = spread_mean
            metrics[hist_std_dev_col_name] = spread_std

            if has_latest_data:
                latest_row = fund_data_hist.loc[latest_date]
                latest_spread = latest_row[spread_col_name]
                
                metrics[f'Latest {fund_col}'] = latest_row[fund_col]
                metrics[f'Latest {spread_col_name}'] = latest_spread

                # Calculate Z-score
                if spread_std is not None and spread_std != 0 and not np.isnan(spread_std):
                    z = (latest_spread - spread_mean) / spread_std
                    metrics[z_score_col_name] = z
                    current_max_abs_z = max(current_max_abs_z, abs(z))
                else:
                    metrics[z_score_col_name] = 0.0
                
                # Calculate changes
                fund_data_hist[fund_change_col_name] = fund_data_hist[fund_col].diff()
                fund_data_hist[spread_change_col_name] = fund_data_hist[spread_col_name].diff()
                latest_changes = fund_data_hist.loc[latest_date]
                metrics[fund_change_col_name] = latest_changes[fund_change_col_name]
                metrics[spread_change_col_name] = latest_changes[spread_change_col_name]

            else:
                 # Handle missing latest data for this column
                metrics[f'Latest {fund_col}'] = np.nan
                metrics[f'Latest {spread_col_name}'] = np.nan
                metrics[z_score_col_name] = np.nan
                metrics[fund_change_col_name] = np.nan
                metrics[spread_change_col_name] = np.nan

        latest_metrics_list.append(metrics)
        # Store the maximum absolute Z-score found for this fund code for sorting
        max_abs_z_scores[fund_code] = current_max_abs_z if pd.notna(current_max_abs_z) else -1 # Use -1 for missing to sort last

    # Create DataFrame
    latest_metrics_df = pd.DataFrame(latest_metrics_list).set_index('Fund Code')

    # Create a Series from the max Z-scores for sorting
    sort_series = pd.Series(max_abs_z_scores)
    
    # Sort DataFrame based on the max absolute Z-score across all spread columns
    latest_metrics_df = latest_metrics_df.reindex(sort_series.sort_values(ascending=False).index)

    return latest_metrics_df 