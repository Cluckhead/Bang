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
    # **IMPORTANT**: Ensure benchmark is NOT in the fund list if it was already identified
    fund_val_col_names = [col.strip() for i, col in enumerate(original_cols)
                            if i != 0 and i != 1 and col.strip() != benchmark_val_col_name]

    # Validate benchmark identification
    if original_cols[3].strip() != benchmark_val_col_name:
         # This case should ideally not happen if the previous list comprehension works
         # but check just in case columns were rearranged weirdly
         print(f"Warning: Identified benchmark column '{benchmark_val_col_name}' was not in expected position 3.")
         # Ensure it's not the date or fund code col
         if benchmark_val_col_name == date_col_name or benchmark_val_col_name == fund_code_col_name:
              raise ValueError(f"Benchmark column '{benchmark_val_col_name}' cannot be the same as Date or Fund Code column.")

    # Read the full CSV
    df = pd.read_csv(filepath, parse_dates=[date_col_name], dayfirst=True)
    df.columns = df.columns.str.strip() # Strip whitespace from column names during read
    df.set_index([date_col_name, fund_code_col_name], inplace=True)

    # Convert all identified fund value columns AND the benchmark column to numeric
    # Ensure we only try to convert columns that actually exist after stripping whitespace
    value_cols_to_convert = [col for col in fund_val_col_names + [benchmark_val_col_name] if col in df.columns]
    if not value_cols_to_convert:
        raise ValueError(f"No valid fund or benchmark columns found to convert in {filename}.")

    df[value_cols_to_convert] = df[value_cols_to_convert].apply(pd.to_numeric, errors='coerce')

    # Return the DataFrame, LIST of fund columns, and the benchmark column
    return df, fund_val_col_names, benchmark_val_col_name


# Completely rewritten function
def calculate_latest_metrics(df, fund_cols, benchmark_col):
    """Calculates latest metrics for *each individual column* (benchmark and funds).

    For each column, calculates: Latest Value, Change, Mean, Max, Min, and Change Z-Score.

    Args:
        df (pd.DataFrame): Processed DataFrame indexed by Date and Fund Code.
        fund_cols (list[str]): List of fund value column names.
        benchmark_col (str): Name of the benchmark value column.

    Returns:
        pandas.DataFrame: Flattened metrics indexed by Fund Code, sorted by the MAX absolute
                          'Change Z-Score' across all columns for that fund.
                          Columns are named like '{col_name} Latest Value', '{col_name} Change', etc.
    """
    latest_date = df.index.get_level_values(0).max()
    fund_codes = df.index.get_level_values(1).unique()
    cols_to_process = [benchmark_col] + fund_cols # Process benchmark first, then funds

    all_metrics_list = []
    max_abs_change_z_scores = {} # Store max z-score *per fund* for sorting

    for fund_code in fund_codes:
        fund_data_hist = df.xs(fund_code, level=1).sort_index()
        fund_metrics = {'Fund Code': fund_code}
        current_fund_max_abs_z = 0.0 # Track max Z for *this fund* across all columns
        has_latest_data_for_fund = latest_date in fund_data_hist.index

        for col_name in cols_to_process:
            if col_name not in fund_data_hist.columns:
                print(f"Warning: Column '{col_name}' not found for fund '{fund_code}'. Skipping metrics for this column.")
                # Add NaN placeholders for this column for this fund
                fund_metrics[f'{col_name} Latest Value'] = np.nan
                fund_metrics[f'{col_name} Change'] = np.nan
                fund_metrics[f'{col_name} Mean'] = np.nan
                fund_metrics[f'{col_name} Max'] = np.nan
                fund_metrics[f'{col_name} Min'] = np.nan
                fund_metrics[f'{col_name} Change Z-Score'] = np.nan
                continue # Skip to the next column for this fund

            col_hist = fund_data_hist[col_name]
            col_change_hist = col_hist.diff()

            # Calculate base historical stats for the column *level*
            hist_mean = col_hist.mean()
            hist_max = col_hist.max()
            hist_min = col_hist.min()

            fund_metrics[f'{col_name} Mean'] = hist_mean
            fund_metrics[f'{col_name} Max'] = hist_max
            fund_metrics[f'{col_name} Min'] = hist_min

            # Calculate stats for the column *change*
            change_mean = col_change_hist.mean()
            change_std = col_change_hist.std()

            # Get latest values if the fund has data for the overall latest date
            if has_latest_data_for_fund:
                latest_value = fund_data_hist.loc[latest_date, col_name]
                latest_change = col_change_hist.loc[latest_date] # Get change for the latest date

                fund_metrics[f'{col_name} Latest Value'] = latest_value
                fund_metrics[f'{col_name} Change'] = latest_change

                # Calculate Change Z-Score
                change_z_score = np.nan # Default to NaN
                if change_std is not None and change_std != 0 and pd.notna(change_std) and pd.notna(latest_change):
                    change_z_score = (latest_change - change_mean) / change_std
                    # Update the fund's overall max abs Z if this one is larger
                    current_fund_max_abs_z = max(current_fund_max_abs_z, abs(change_z_score))
                
                fund_metrics[f'{col_name} Change Z-Score'] = change_z_score

            else:
                # Fund is missing the latest date entirely
                fund_metrics[f'{col_name} Latest Value'] = np.nan
                fund_metrics[f'{col_name} Change'] = np.nan
                fund_metrics[f'{col_name} Change Z-Score'] = np.nan

        # Store the calculated metrics for this fund
        all_metrics_list.append(fund_metrics)
        # Store the max abs change Z-score found *for this fund* across all its columns
        max_abs_change_z_scores[fund_code] = current_fund_max_abs_z if pd.notna(current_fund_max_abs_z) else -1

    if not all_metrics_list:
        return pd.DataFrame() # Return empty DataFrame if no funds were processed

    # Create DataFrame
    latest_metrics_df = pd.DataFrame(all_metrics_list).set_index('Fund Code')

    # Sort by the max absolute change Z-score across any column for the fund
    sort_series = pd.Series(max_abs_change_z_scores)
    latest_metrics_df = latest_metrics_df.reindex(sort_series.sort_values(ascending=False).index)

    return latest_metrics_df 