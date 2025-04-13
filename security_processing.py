# This file handles the loading, processing, and analysis of security-level data.
# It assumes input CSV files are structured with one security per row and time series data
# spread across columns where headers represent dates (e.g., YYYY-MM-DD).
# Key functions:
# - `load_and_process_security_data`: Reads a wide-format CSV (given filename and data path),
#   identifies the security ID column, static attribute columns, and date columns.
#   It then 'melts' the data into a long format, converting date strings to datetime objects.
# - `calculate_security_latest_metrics`: Takes the processed long-format DataFrame and calculates
#   various metrics for each security's 'Value' over time, including latest value, change,
#   historical stats (mean, max, min), and change Z-score. It also preserves the static attributes.

import pandas as pd
import os
import numpy as np
import re # For checking date-like column headers
import logging
import traceback
# Note: Does not import current_app, relies on caller to pass the path.

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

# --- Removed logging setup block --- 
# Logging is now handled centrally by the Flask app factory in app.py

# Removed DATA_FOLDER constant - path is now passed to functions

def _is_date_like(column_name):
    """Check if a column name looks like a common date format.

    Recognizes formats like YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY, M/D/YYYY, YYYYMMDD.
    """
    col_str = str(column_name)
    # Regex to match common date patterns
    # - YYYY[-/]MM[-/]DD
    # - MM[-/]DD[-/]YYYY (allows 1-2 digits for M, D and 2 or 4 for Y)
    # - YYYYMMDD
    pattern = r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/](\d{4}|\d{2})|\d{8})$'
    return bool(re.match(pattern, col_str))

def load_and_process_security_data(filename: str, data_folder_path: str):
    """Loads security data, identifies static/date columns, and melts to long format."""
    log_prefix = f"[{filename}] " # Prefix for logs from this function
    logger.info(f"{log_prefix}--- Entering load_and_process_security_data ---")
    if not data_folder_path:
        logger.error(f"{log_prefix}No data_folder_path provided.")
        return pd.DataFrame(), []

    filepath = os.path.join(data_folder_path, filename)
    logger.info(f"{log_prefix}Attempting to load security data from: {filepath}")

    try:
        # --- Read Header --- 
        logger.debug(f"{log_prefix}Reading header...")
        header_df = pd.read_csv(filepath, nrows=0, on_bad_lines='skip', encoding='utf-8', encoding_errors='replace')
        all_cols = [str(col).strip() for col in header_df.columns.tolist()]
        logger.debug(f"{log_prefix}Read header columns: {all_cols}")

        if not all_cols:
            logger.error(f"{log_prefix}CSV file appears to be empty or header is missing.")
            raise ValueError(f"CSV file '{filename}' appears to be empty or header is missing.")

        # --- Identify Essential ID Columns --- 
        essential_id_cols = []
        if 'ISIN' in all_cols:
            essential_id_cols.append('ISIN')
        if 'Security Name' in all_cols:
            essential_id_cols.append('Security Name')
        
        if not essential_id_cols:
             logger.warning(f"{log_prefix}Neither 'ISIN' nor 'Security Name' found. Using first column '{all_cols[0]}' as potential ID.")
             essential_id_cols.append(all_cols[0])

        logger.info(f"{log_prefix}Essential ID Columns identified: {essential_id_cols}")

        # --- Identify Static and Date Columns --- 
        static_cols = []
        date_cols = []
        for col in all_cols:
            if col in essential_id_cols:
                continue
            if _is_date_like(col):
                date_cols.append(col)
            else:
                static_cols.append(col)

        if not date_cols:
            logger.error(f"{log_prefix}No date-like columns found using flexible patterns. Cannot process.")
            raise ValueError("No date-like columns found using flexible patterns.")

        logger.info(f"{log_prefix}Identified Static Cols: {static_cols}")
        logger.debug(f"{log_prefix}Identified {len(date_cols)} Date Cols (e.g., {date_cols[:3]}...)")

        # --- Read Full Data --- 
        logger.debug(f"{log_prefix}Reading full data...")
        df_wide = pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip', encoding_errors='replace')
        df_wide.columns = df_wide.columns.map(lambda x: str(x).strip())
        logger.info(f"{log_prefix}Read full data. Shape: {df_wide.shape}")
        
        # --- Melt Data --- 
        id_vars_melt = [col for col in essential_id_cols if col in df_wide.columns] + \
                       [col for col in static_cols if col in df_wide.columns]
        value_vars = [col for col in date_cols if col in df_wide.columns]

        if not value_vars:
             logger.error(f"{log_prefix}Date columns identified in header not found in data frame after loading. Columns available: {df_wide.columns.tolist()}")
             raise ValueError("Date columns identified in header not found in data frame after loading.")
        if not id_vars_melt:
             logger.error(f"{log_prefix}No ID or static columns found to use as id_vars. Columns available: {df_wide.columns.tolist()}")
             raise ValueError("No ID or static columns found for melting.")
        
        logger.debug(f"{log_prefix}Melting data. ID vars: {id_vars_melt}, Value vars count: {len(value_vars)}")
        df_long = pd.melt(df_wide,
                          id_vars=id_vars_melt,
                          value_vars=value_vars,
                          var_name='Date_Str',
                          value_name='Value')
        logger.info(f"{log_prefix}Melted data shape: {df_long.shape}")

        # --- Process Date and Value --- 
        date_col_str = 'Date_Str'
        date_col_dt = 'Date'
        logger.debug(f"{log_prefix}Parsing dates and converting values...")
        
        # 1. Try DD/MM/YYYY first
        df_long[date_col_dt] = pd.to_datetime(df_long[date_col_str], format='%d/%m/%Y', errors='coerce')
        
        # 2. Try YYYY-MM-DD for any remaining NaTs
        # Create a mask for rows where the first attempt failed
        nat_mask = df_long[date_col_dt].isna()
        if nat_mask.any():
            logger.info(f"{log_prefix}Attempting fallback date parsing (YYYY-MM-DD) for {nat_mask.sum()} entries.")
            # Apply the second format ONLY to the NaT rows
            df_long.loc[nat_mask, date_col_dt] = pd.to_datetime(df_long.loc[nat_mask, date_col_str], format='%Y-%m-%d', errors='coerce')

        # Check again for NaTs after both attempts
        final_nat_count = df_long[date_col_dt].isna().sum()
        if final_nat_count > 0:
            logger.warning(f"{log_prefix}Could not parse {final_nat_count} date strings using specified formats (DD/MM/YYYY, YYYY-MM-DD).")
            # Example of unparsed date strings:
            unparsed_examples = df_long.loc[df_long[date_col_dt].isna(), date_col_str].unique()[:5]
            logger.warning(f"{log_prefix}Unparsed examples: {unparsed_examples}")

        # Convert Value column
        df_long['Value'] = pd.to_numeric(df_long['Value'], errors='coerce')
        
        # Drop rows where essential data is missing
        initial_rows = len(df_long)
        required_cols_for_dropna = ['Date', 'Value'] + [col for col in essential_id_cols if col in df_long.columns]
        df_long.dropna(subset=required_cols_for_dropna, inplace=True)
        rows_dropped = initial_rows - len(df_long)
        if rows_dropped > 0:
             logger.warning(f"{log_prefix}Dropped {rows_dropped} rows due to missing required values (Date, Value, or Essential IDs).")
        
        if df_long.empty:
             logger.warning(f"{log_prefix}DataFrame is empty after melting, conversion, and NaN drop.")
             return pd.DataFrame(), static_cols

        # Determine ID column name for index
        id_col_name = None
        if 'ISIN' in df_long.columns:
            id_col_name = 'ISIN'
        elif 'Security Name' in df_long.columns:
             id_col_name = 'Security Name'
        elif essential_id_cols and essential_id_cols[0] in df_long.columns: 
             id_col_name = essential_id_cols[0]
             logger.warning(f"{log_prefix}Using fallback ID '{id_col_name}' for index setting.")
        else:
             logger.error(f"{log_prefix}Cannot determine a valid ID column ({essential_id_cols}) to set index. Columns: {df_long.columns.tolist()}")
             return pd.DataFrame(), []
        
        logger.info(f"{log_prefix}Determined ID column for index: '{id_col_name}'")

        # Drop Date_Str column BEFORE setting index
        if 'Date_Str' in df_long.columns:
            df_long.drop(columns=['Date_Str'], inplace=True)
            logger.debug(f"{log_prefix}Dropped 'Date_Str' column.")

        # Sort before setting index
        logger.debug(f"{log_prefix}Sorting by '{id_col_name}' and 'Date'...")
        df_long = df_long.sort_values(by=[id_col_name, 'Date'])

        # --- SET THE MULTIINDEX --- 
        try:
            logger.debug(f"{log_prefix}Setting index to ['Date', '{id_col_name}']...")
            df_long.set_index(['Date', id_col_name], inplace=True)
            logger.info(f"{log_prefix}Set MultiIndex ('Date', '{id_col_name}'). Final shape: {df_long.shape}")
        except KeyError as e:
             logger.error(f"{log_prefix}Failed to set index using ['Date', '{id_col_name}']. Error: {e}. Columns: {df_long.columns.tolist()}")
             return pd.DataFrame(), []
        
        # Identify static columns *excluding* essential ID cols to return
        # We return the list of non-ID static attributes
        final_static_cols = [col for col in static_cols if col in df_long.columns]

        logger.info(f"{log_prefix}--- Exiting load_and_process_security_data. Returning DataFrame and static cols: {final_static_cols} ---")
        return df_long, final_static_cols # Return only non-ID static cols

    except FileNotFoundError:
        logger.error(f"Error: File not found at {filepath}")
        return pd.DataFrame(), [] # Return empty dataframe and list
    except ValueError as ve:
        logger.error(f"Error processing header or columns in {filename}: {ve}")
        return pd.DataFrame(), []
    except KeyError as ke:
        logger.error(f"Error melting DataFrame for {filename}, likely due to missing column used as id_var or value_var: {ke}")
        return pd.DataFrame(), []
    except Exception as e:
        logger.error(f"An unexpected error occurred loading/processing {filename}: {e}", exc_info=True)
        # traceback.print_exc() # Logger handles traceback now
        return pd.DataFrame(), []


def calculate_security_latest_metrics(df, static_cols):
    """Calculates latest metrics for each security based on its 'Value' column.

    Args:
        df (pd.DataFrame): Processed long-format DataFrame with MultiIndex (Date, Security ID).
                           Must contain a 'Value' column.
        static_cols (list[str]): List of static column names present in the DataFrame's columns (not index).

    Returns:
        pandas.DataFrame: DataFrame indexed by Security ID, including static columns and
                          calculated metrics (Latest Value, Change, Mean, Max, Min, Change Z-Score).
                          Returns an empty DataFrame if input is empty or processing fails.
    """
    if df is None or df.empty:
        logger.warning("Input DataFrame is None or empty. Cannot calculate security metrics.")
        return pd.DataFrame()

    if 'Value' not in df.columns:
        logger.error("Input DataFrame for security metrics calculation must contain a 'Value' column.")
        return pd.DataFrame()
        
    # Ensure index has two levels and get their names dynamically
    if df.index.nlevels != 2:
        logger.error("Input DataFrame for security metrics must have 2 index levels (Date, Security ID).")
        return pd.DataFrame()
    date_level_name, id_level_name = df.index.names

    try:
        latest_date = df.index.get_level_values(date_level_name).max()
        security_ids = df.index.get_level_values(id_level_name).unique()

        all_metrics_list = []

        for sec_id in security_ids:
            try:
                # Extract data for the current security ID
                # Use .loc for potentially cleaner selection and ensure sorting
                sec_data_hist = df.loc[(slice(None), sec_id), :].reset_index(level=id_level_name, drop=True).sort_index()
                
                if sec_data_hist.empty:
                     logger.debug(f"No data found for security '{sec_id}' after extraction. Skipping.")
                     continue

                sec_metrics = {} # Dictionary to hold metrics for this security
                
                # Add static columns first
                # Take the first available row's values, assuming they are constant per security
                # Need to handle potential multi-index if static_cols contains index names by mistake
                valid_static_cols = [col for col in static_cols if col in sec_data_hist.columns]
                if not sec_data_hist.empty:
                    static_data_row = sec_data_hist.iloc[0]
                    for static_col in valid_static_cols:
                        sec_metrics[static_col] = static_data_row.get(static_col, np.nan)
                else: # Should not happen due to check above, but safeguard
                    for static_col in valid_static_cols:
                         sec_metrics[static_col] = np.nan 
                
                # Ensure all expected static cols are present in the dict, even if missing from data
                for static_col in static_cols:
                     if static_col not in sec_metrics:
                          logger.warning(f"Static column '{static_col}' not found in data for security '{sec_id}', adding as NaN.")
                          sec_metrics[static_col] = np.nan

                # Calculate metrics for the 'Value' column
                value_hist = sec_data_hist['Value']
                # Calculate diff only if series has enough data
                value_change_hist = pd.Series(index=value_hist.index, dtype=np.float64)
                if not value_hist.dropna().empty and len(value_hist.dropna()) > 1:
                    value_change_hist = value_hist.diff()
                else:
                    logger.debug(f"Cannot calculate difference for 'Value' column, security '{sec_id}' due to insufficient data.")

                # Base historical stats (level) - handle potential all-NaN series
                sec_metrics['Mean'] = value_hist.mean() if value_hist.notna().any() else np.nan
                sec_metrics['Max'] = value_hist.max() if value_hist.notna().any() else np.nan
                sec_metrics['Min'] = value_hist.min() if value_hist.notna().any() else np.nan

                # Stats for change
                change_mean = value_change_hist.mean() if value_change_hist.notna().any() else np.nan
                change_std = value_change_hist.std() if value_change_hist.notna().any() else np.nan

                # Latest values
                # Check if latest_date exists in this security's specific history
                if latest_date in sec_data_hist.index:
                    latest_value = sec_data_hist.loc[latest_date, 'Value']
                    latest_change = value_change_hist.get(latest_date, np.nan)

                    sec_metrics['Latest Value'] = latest_value
                    sec_metrics['Change'] = latest_change

                    # Calculate Change Z-Score
                    change_z_score = np.nan
                    if pd.notna(latest_change) and pd.notna(change_mean) and pd.notna(change_std) and change_std != 0:
                        change_z_score = (latest_change - change_mean) / change_std
                    elif change_std == 0 and pd.notna(latest_change) and pd.notna(change_mean):
                         # Handle zero standard deviation
                         if latest_change == change_mean:
                              change_z_score = 0.0
                         else:
                             change_z_score = np.inf if latest_change > change_mean else -np.inf
                         logger.debug(f"Std dev of change for security '{sec_id}' is zero. Z-score set to {change_z_score}.")
                    else:
                         # Log if Z-score calculation failed due to NaNs
                        if not (pd.notna(latest_change) and pd.notna(change_mean) and pd.notna(change_std)):
                             logger.debug(f"Cannot calculate Z-score for security '{sec_id}' due to NaN inputs (latest_change={latest_change}, change_mean={change_mean}, change_std={change_std})")
                            
                    sec_metrics['Change Z-Score'] = change_z_score

                else:
                    # Security missing the overall latest date
                    logger.debug(f"Security '{sec_id}' missing data for latest date {latest_date}. Setting latest metrics to NaN.")
                    sec_metrics['Latest Value'] = np.nan
                    sec_metrics['Change'] = np.nan
                    sec_metrics['Change Z-Score'] = np.nan
                
                # Add the security ID itself for setting the index later
                sec_metrics[id_level_name] = sec_id 
                
                all_metrics_list.append(sec_metrics)
            
            except Exception as inner_e:
                logger.error(f"Error calculating metrics for security '{sec_id}': {inner_e}", exc_info=True)
                # Optionally add a placeholder row with NaNs? Or just skip. Let's skip.
                continue


        if not all_metrics_list:
            logger.warning("No security metrics were successfully calculated. Returning empty DataFrame.")
            return pd.DataFrame()

        # Create DataFrame and set index
        latest_metrics_df = pd.DataFrame(all_metrics_list)
        # id_col_name = df.index.names[1] # Get the actual ID column name used
        if id_level_name in latest_metrics_df.columns:
             latest_metrics_df.set_index(id_level_name, inplace=True)
        else:
             logger.error(f"Security ID column '{id_level_name}' not found in the created metrics list for setting index. Columns: {latest_metrics_df.columns.tolist()}")
             # Fallback or error? Let's return as is for now, index might be RangeIndex.

        # Reorder columns to have static columns first, then calculated metrics
        metric_cols = ['Latest Value', 'Change', 'Mean', 'Max', 'Min', 'Change Z-Score']
        # Get static cols that are actually present in the final df columns (excluding the ID index)
        present_static_cols = [col for col in static_cols if col in latest_metrics_df.columns]
        final_col_order = present_static_cols + [m_col for m_col in metric_cols if m_col in latest_metrics_df.columns]
        
        try:
            latest_metrics_df = latest_metrics_df[final_col_order]
        except KeyError as ke:
            logger.error(f"Error reordering columns, likely a metric column is missing: {ke}. Columns available: {latest_metrics_df.columns.tolist()}")
            # Proceed with potentially incorrect order

        # Sorting (e.g., by Z-score) should be done in the view function where it's displayed
        logger.info(f"Successfully calculated metrics for {len(latest_metrics_df)} securities.")
        return latest_metrics_df

    except Exception as e:
        logger.error(f"An unexpected error occurred during security metric calculation: {e}", exc_info=True)
        # traceback.print_exc() # Logger handles traceback
        return pd.DataFrame() 