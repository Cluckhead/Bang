# views/comparison_views.py
# This module defines the Flask Blueprint for comparing two security spread datasets.
# It includes routes for a summary view listing securities with comparison metrics
# and a detail view showing overlayed time-series charts and statistics for a single security.

from flask import Blueprint, render_template, request, current_app, jsonify, url_for
import pandas as pd
import os
import logging
import math # Add math import for pagination calculation
from pathlib import Path
import re
from datetime import datetime

# Assuming security_processing and utils are in the parent directory or configured in PYTHONPATH
try:
    from security_processing import load_and_process_security_data, calculate_security_latest_metrics # May need adjustments
    from utils import parse_fund_list # Example utility
    from config import COLOR_PALETTE # Still need colors
except ImportError:
    # Handle potential import errors if the structure is different
    logging.error("Could not import required modules from parent directory.")
    # Add fallback imports or path adjustments if necessary
    # Example: sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from ..security_processing import load_and_process_security_data, calculate_security_latest_metrics
    from ..utils import parse_fund_list
    from ..config import COLOR_PALETTE

# Import utils module properly
try: 
    from utils import _is_date_like # Try direct import
except ImportError:
    # Define our own function if import fails
    def _is_date_like(column_name):
        """Check if a column name looks like a date.
        Returns True for formats like: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, etc."""
        if not isinstance(column_name, str):
            return False
        
        # Match common date formats in column names
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
            r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
            r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # D/M/YY or D/M/YYYY
            r'\d{1,2}-\d{1,2}-\d{2,4}',  # D-M-YY or D-M-YYYY
        ]
        
        # Return True if any pattern matches
        return any(re.search(pattern, column_name) for pattern in date_patterns)


comparison_bp = Blueprint('comparison_bp', __name__,
                        template_folder='../templates',
                        static_folder='../static')

# Configure logging
# log = logging.getLogger(__name__)

PER_PAGE_COMPARISON = 50 # Items per page for comparison summary

# --- Data Loading and Processing ---

def load_weights_and_held_status(data_folder: str, weights_filename: str = 'w_secs.csv', id_col_override: str = 'ISIN') -> pd.Series:
    """
    Loads the weights file (e.g., w_secs.csv), identifies the latest date,
    and returns a boolean Series indicating which securities (indexed by ISIN)
    have a non-zero weight on that date (i.e., are currently held).

    Args:
        data_folder: The absolute path to the data directory.
        weights_filename: The name of the weights file.
        id_col_override: The specific column name in the weights file expected to contain the ISINs for joining.

    Returns:
        A pandas Series where the index is the Security ID (ISIN) and the value
        is True if the security is held on the latest date, False otherwise.
        Returns an empty Series if the file cannot be loaded or processed.
    """
    current_app.logger.info(f"--- Entering load_weights_and_held_status for {weights_filename} ---")
    weights_filepath = Path(data_folder) / weights_filename
    if not weights_filepath.exists():
        current_app.logger.warning(f"Weights file not found: {weights_filepath}")
        return pd.Series(dtype=bool)

    try:
        current_app.logger.info(f"Loading weights data from: {weights_filepath}")
        # Load without setting index initially to easily find date/ID columns
        weights_df = pd.read_csv(weights_filepath, low_memory=False)
        weights_df.columns = weights_df.columns.str.strip() # Clean column names

        # --- Identify Date and ID columns ---
        date_col = next((col for col in weights_df.columns if 'date' in col.lower()), None)
        # Prioritize the explicitly provided id_col_override, then look for ISIN/SecurityID
        id_col_in_file = id_col_override if id_col_override in weights_df.columns else \
                         next((col for col in weights_df.columns if col.lower() in ['isin', 'securityid']), None)

        # Check for ID column - required
        if not id_col_in_file:
            current_app.logger.error(f"Could not automatically identify ID column in {weights_filepath}. Columns found: {weights_df.columns.tolist()}")
            return pd.Series(dtype=bool)
        
        current_app.logger.info(f"Weights file ID column identified: '{id_col_in_file}'")

        # --- Identify and Melt Date Columns ---
        date_columns = [col for col in weights_df.columns if _is_date_like(col)]
        
        if not date_columns:
            # If no date-like columns were found and no explicit date column exists
            if not date_col:
                current_app.logger.error(f"No date column or date-like columns found in {weights_filepath}")
                return pd.Series(dtype=bool)
                
            # Try to use the explicitly found date column
            current_app.logger.info(f"No date-like columns found. Attempting to use explicit date column: '{date_col}'")
            try:
                weights_df[date_col] = pd.to_datetime(weights_df[date_col], errors='coerce')
                if weights_df[date_col].isnull().all():
                    raise ValueError("Date column parsing failed.")
                # If successful, proceed as if it was a long-format file from the start
                value_col = next((col for col in weights_df.columns if col.lower() == 'value'), 'Value') # Assume a 'Value' column exists
                if value_col not in weights_df.columns:
                    # If no obvious value column, assume last column is value
                    value_col = weights_df.columns[-1]
                    current_app.logger.warning(f"No 'Value' column found in long-format weights file, assuming last column '{value_col}' holds weights.")

                # Rename for consistency
                weights_df = weights_df.rename(columns={date_col: 'Date', id_col_in_file: 'ISIN', value_col: 'Value'})
                weights_df['Value'] = pd.to_numeric(weights_df['Value'], errors='coerce')

            except Exception as e:
                current_app.logger.error(f"Failed to process weights file {weights_filepath} as long format after date column detection failed: {e}")
                return pd.Series(dtype=bool)
        else:
            current_app.logger.info(f"Found {len(date_columns)} date-like columns in {weights_filename}: {date_columns[:5]}{'...' if len(date_columns) > 5 else ''}")
            # Wide format: Melt the DataFrame
            id_vars = [col for col in weights_df.columns if col not in date_columns]
            melted_weights = weights_df.melt(id_vars=id_vars, value_vars=date_columns, var_name='Date', value_name='Value')

            # Attempt to convert 'Date' column to datetime objects after melting
            melted_weights['Date'] = pd.to_datetime(melted_weights['Date'], errors='coerce')
            melted_weights['Value'] = pd.to_numeric(melted_weights['Value'], errors='coerce')

            # Rename the identified ID column to 'ISIN' for consistency
            melted_weights = melted_weights.rename(columns={id_col_in_file: 'ISIN'})
            weights_df = melted_weights # Use the melted df going forward


        # Find the latest date in the entire dataset
        latest_date = weights_df['Date'].max()
        if pd.isna(latest_date):
            current_app.logger.warning(f"Could not determine the latest date in {weights_filepath}.")
            return pd.Series(dtype=bool)
        current_app.logger.info(f"Latest date in weights file '{weights_filepath}': {latest_date}")

        # Filter for the latest date and where Value is not NaN and > 0
        latest_weights = weights_df[(weights_df['Date'] == latest_date) & (weights_df['Value'].notna()) & (weights_df['Value'] > 0)].copy()

        # --- Determine Held Status using the correct ID column ---
        # We now use the *renamed* 'ISIN' column, which originally came from id_col_in_file (our target)
        held_status_col = 'ISIN'
        if held_status_col not in latest_weights.columns:
             current_app.logger.error(f"The target ID column '{held_status_col}' (derived from '{id_col_in_file}') not found after processing {weights_filepath}. Columns: {latest_weights.columns.tolist()}")
             return pd.Series(dtype=bool)

        current_app.logger.info(f"Using '{held_status_col}' column from {weights_filename} for held_status index.")

        # Create the boolean Series: index is the ISIN, value is True
        # Drop duplicates in case a security appears multiple times on the same date (e.g., different funds)
        held_ids = latest_weights.drop_duplicates(subset=[held_status_col])[held_status_col]
        held_status = pd.Series(True, index=held_ids)
        held_status.index.name = 'ISIN' # Ensure the index name is 'ISIN' for merging

        # --- Logging for Debugging ---
        current_app.logger.debug(f"Weights data before setting index (first 5 rows using '{held_status_col}'):\n{latest_weights[[held_status_col, 'Value']].head().to_string()}")
        sample_values = latest_weights[held_status_col].unique()[:5]
        current_app.logger.debug(f"Sample values from '{held_status_col}' column to be used for index: {sample_values}")

        # This renaming logic is now less critical as we set the index correctly, but keep for consistency check
        if held_status.index.name != id_col_override:
             current_app.logger.warning(f"Renaming held_status index from '{held_status.index.name}' to '{id_col_override}' to ensure merge compatibility.")
             held_status.index.name = id_col_override # Explicitly set to ISIN for clarity

        current_app.logger.debug(f"Resulting held_status Series index name after potential rename: '{held_status.index.name}'")
        current_app.logger.debug(f"Held status index preview (first 5 values): {held_status.index[:5].tolist()}")
        current_app.logger.debug(f"Held status values preview (first 5): {held_status.head().to_dict()}")
        current_app.logger.info(f"Determined held status for {len(held_status)} IDs based on weights on {latest_date}.")

        return held_status

    except Exception as e:
        current_app.logger.error(f"Error loading or processing weights file {weights_filepath}: {e}", exc_info=True)
        return pd.Series(dtype=bool)


def load_comparison_data(data_folder_path: str, file1='sec_spread.csv', file2='sec_spreadSP.csv'):
    log = current_app.logger # Use app logger
    log.info(f"--- Entering load_comparison_data: {file1}, {file2} ---") # ENTRY LOG
    """Loads, processes, merges data from two security spread files, and gets held status.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        file1 (str, optional): Filename for the first dataset. Defaults to 'sec_spread.csv'.
        file2 (str, optional): Filename for the second dataset. Defaults to 'sec_spreadSP.csv'.

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name, held_status)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None, pd.Series(dtype=bool)) on error.
    """
    log.info(f"Loading comparison data: {file1} and {file2} from {data_folder_path}")
    if not data_folder_path:
        log.error("No data_folder_path provided to load_comparison_data.")
        return pd.DataFrame(), pd.DataFrame(), [], None, pd.Series(dtype=bool)

    # Pass the absolute data folder path to the loading functions
    df1, static_cols1 = load_and_process_security_data(file1, data_folder_path)
    log.info(f"Loaded {file1}. Shape: {df1.shape if not df1.empty else 'Empty'}. Static cols: {static_cols1}")
    df2, static_cols2 = load_and_process_security_data(file2, data_folder_path)
    log.info(f"Loaded {file2}. Shape: {df2.shape if not df2.empty else 'Empty'}. Static cols: {static_cols2}")

    # Reset index to make Date and ID columns accessible
    if not df1.empty:
        df1 = df1.reset_index()
    if not df2.empty:
        df2 = df2.reset_index()

    # Load held status, passing the data folder path
    held_status = load_weights_and_held_status(data_folder_path)
    log.info(f"Loaded held_status. Is empty: {held_status.empty}")

    if df1.empty or df2.empty:
        log.warning(f"One or both dataframes are empty. File1 empty: {df1.empty}, File2 empty: {df2.empty}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status # Still return status

    common_static_cols = list(set(static_cols1) & set(static_cols2))
    
    # Identify ID column - check for 'ISIN' first
    if 'ISIN' in df1.columns:
        id_col_name = 'ISIN'
        log.info(f"Identified ID column from columns: {id_col_name}")
    # Explicitly check if there are columns before accessing index 0
    elif not df1.empty and len(df1.columns) > 0:
        potential_id = df1.columns[0]
        log.warning(f"\'ISIN\' column not found in df1. Attempting to use the first column \'{potential_id}\' as ID. This might be incorrect.")
        id_col_name = potential_id
        if id_col_name not in df2.columns:
            log.error(f"Fallback ID column '{id_col_name}' from df1 not found in df2.")
            return pd.DataFrame(), pd.DataFrame(), [], None, held_status
    else:
        log.error("Failed to identify ID column. \'ISIN\' not found and DataFrame might be empty or malformed.")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    if id_col_name in common_static_cols:
        common_static_cols.remove(id_col_name)
        log.debug(f"Removed ID column '{id_col_name}' from common_static_cols.")

    try:
        df1_merge = df1[[id_col_name, 'Date', 'Value'] + common_static_cols].rename(columns={'Value': 'Value_Orig'})
        if id_col_name not in df2.columns:
             log.error(f"ID column '{id_col_name}' identified in df1 not found in df2 columns: {df2.columns.tolist()}")
             raise KeyError(f"ID column '{id_col_name}' not found in second dataframe")
        df2_merge = df2[[id_col_name, 'Date', 'Value']].rename(columns={'Value': 'Value_New'})
    except KeyError as e:
        log.error(f"Missing required column for merge preparation: {e}. Df1 cols: {df1.columns.tolist()}, Df2 cols: {df2.columns.tolist()}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    merged_df = pd.merge(df1_merge, df2_merge, on=[id_col_name, 'Date'], how='outer')
    merged_df = merged_df.sort_values(by=[id_col_name, 'Date'])
    merged_df['Change_Orig'] = merged_df.groupby(id_col_name)['Value_Orig'].diff()
    merged_df['Change_New'] = merged_df.groupby(id_col_name)['Value_New'].diff()

    static_data = merged_df.groupby(id_col_name)[common_static_cols].last().reset_index()

    log.info(f"Successfully merged data. Shape: {merged_df.shape}")
    # Return held_status along with other data
    log.info(f"--- Exiting load_comparison_data. Merged shape: {merged_df.shape if not merged_df.empty else 'Empty'}. ID col: {id_col_name} ---") # EXIT LOG
    return merged_df, static_data, common_static_cols, id_col_name, held_status


def calculate_comparison_stats(merged_df, static_data, id_col):
    log = current_app.logger # Use app logger
    log.info(f"--- Entering calculate_comparison_stats. Input shape: {merged_df.shape if not merged_df.empty else 'Empty'} ---") # ENTRY LOG
    """Calculates comparison statistics for each security.

    Args:
        merged_df (pd.DataFrame): The merged dataframe of original and new values.
        static_data (pd.DataFrame): DataFrame with static info per security.
        id_col (str): The name of the column containing the Security ID/Name.
    """
    if merged_df.empty:
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(f"Specified id_col '{id_col}' not found in merged_df columns: {merged_df.columns.tolist()}")
        return pd.DataFrame() # Cannot group without the ID column

    log.info(f"Calculating comparison statistics using ID column: {id_col}...")

    stats_list = []

    # Use the passed id_col here
    for sec_id, group in merged_df.groupby(id_col):
        sec_stats = {id_col: sec_id} # Use actual id_col name

        # Filter out rows where both values are NaN for overall analysis period
        group_valid_overall = group.dropna(subset=['Value_Orig', 'Value_New'], how='all')
        overall_min_date = group_valid_overall['Date'].min()
        overall_max_date = group_valid_overall['Date'].max()

        # Filter out rows where EITHER value is NaN for correlation/diff calculations
        valid_comparison = group.dropna(subset=['Value_Orig', 'Value_New'])

        # 1. Correlation of Levels
        if len(valid_comparison) >= 2: # Need at least 2 points for correlation
            # Use the NaN-dropped dataframe for correlation
            level_corr = valid_comparison['Value_Orig'].corr(valid_comparison['Value_New'])
            sec_stats['Level_Correlation'] = level_corr if pd.notna(level_corr) else None
        else:
             sec_stats['Level_Correlation'] = None

        # 2. Max / Min (use original group to get true max/min including non-overlapping points)
        sec_stats['Max_Orig'] = group['Value_Orig'].max()
        sec_stats['Min_Orig'] = group['Value_Orig'].min()
        sec_stats['Max_New'] = group['Value_New'].max()
        sec_stats['Min_New'] = group['Value_New'].min()

        # 3. Date Range Comparison - Refined Logic
        # Find min/max dates within the MERGED data where each series is individually valid
        min_date_orig_idx = group['Value_Orig'].first_valid_index()
        max_date_orig_idx = group['Value_Orig'].last_valid_index()
        min_date_new_idx = group['Value_New'].first_valid_index()
        max_date_new_idx = group['Value_New'].last_valid_index()

        sec_stats['Start_Date_Orig'] = group.loc[min_date_orig_idx, 'Date'] if min_date_orig_idx is not None else None
        sec_stats['End_Date_Orig'] = group.loc[max_date_orig_idx, 'Date'] if max_date_orig_idx is not None else None
        sec_stats['Start_Date_New'] = group.loc[min_date_new_idx, 'Date'] if min_date_new_idx is not None else None
        sec_stats['End_Date_New'] = group.loc[max_date_new_idx, 'Date'] if max_date_new_idx is not None else None

        # Check if the start and end dates MATCH for the valid periods of EACH series
        same_start = pd.Timestamp(sec_stats['Start_Date_Orig']) == pd.Timestamp(sec_stats['Start_Date_New']) if sec_stats['Start_Date_Orig'] and sec_stats['Start_Date_New'] else False
        same_end = pd.Timestamp(sec_stats['End_Date_Orig']) == pd.Timestamp(sec_stats['End_Date_New']) if sec_stats['End_Date_Orig'] and sec_stats['End_Date_New'] else False
        sec_stats['Same_Date_Range'] = same_start and same_end

        # Add overall date range for info
        sec_stats['Overall_Start_Date'] = overall_min_date
        sec_stats['Overall_End_Date'] = overall_max_date

        # 4. Correlation of Daily Changes (Volatility Alignment)
        # Use the dataframe where BOTH values are non-NaN to calculate changes for correlation
        valid_comparison = valid_comparison.copy() # Avoid SettingWithCopyWarning
        valid_comparison['Change_Orig_Corr'] = valid_comparison['Value_Orig'].diff()
        valid_comparison['Change_New_Corr'] = valid_comparison['Value_New'].diff()
        
        # Drop NaNs created by the diff() itself (first row)
        valid_changes = valid_comparison.dropna(subset=['Change_Orig_Corr', 'Change_New_Corr'])

        # --- Debug Logging Start ---
        # if sec_id == 'Alpha001': # Log only for a specific security to avoid flooding
        #     log.debug(f"Debug {sec_id} - valid_changes DataFrame (first 5 rows):\n{valid_changes.head()}")
        #     log.debug(f"Debug {sec_id} - valid_changes count: {len(valid_changes)}")
        # --- Debug Logging End ---

        if len(valid_changes) >= 2:
            change_corr = valid_changes['Change_Orig_Corr'].corr(valid_changes['Change_New_Corr'])
            sec_stats['Change_Correlation'] = change_corr if pd.notna(change_corr) else None
        else:
            sec_stats['Change_Correlation'] = None
            # Log why correlation is None
            log.debug(f"Cannot calculate Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}.")

        # 5. Difference Statistics (use the valid_comparison df where both values exist)
        valid_comparison['Abs_Diff'] = (valid_comparison['Value_Orig'] - valid_comparison['Value_New']).abs()
        sec_stats['Mean_Abs_Diff'] = valid_comparison['Abs_Diff'].mean() # Mean diff where both values exist
        sec_stats['Max_Abs_Diff'] = valid_comparison['Abs_Diff'].max() # Max diff where both values exist
        
        # Count NaNs - use original group
        sec_stats['NaN_Count_Orig'] = group['Value_Orig'].isna().sum()
        sec_stats['NaN_Count_New'] = group['Value_New'].isna().sum()
        sec_stats['Total_Points'] = len(group)

        stats_list.append(sec_stats)

    summary_df = pd.DataFrame(stats_list)

    # Merge static data back
    if not static_data.empty and id_col in static_data.columns and id_col in summary_df.columns:
        summary_df = pd.merge(summary_df, static_data, on=id_col, how='left')
    elif not static_data.empty:
         log.warning(f"Could not merge static data back. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns}).")

    log.info(f"Finished calculating stats. Summary shape: {summary_df.shape}")
    log.info(f"--- Exiting calculate_comparison_stats. Output shape: {summary_df.shape if summary_df is not None and not summary_df.empty else 'Empty'} ---") # EXIT LOG
    return summary_df


# --- Routes ---

@comparison_bp.route('/comparison/logtest')
def log_test():
    current_app.logger.info("--- !!! HIT /comparison/logtest ROUTE !!! ---")
    return "Log test route executed. Check instance/app.log.", 200

@comparison_bp.route('/comparison/summary')
def summary():
    current_app.logger.info("--- Starting Spread Comparison Summary Request ---")
    data_folder = current_app.config.get('DATA_FOLDER', './Data')
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'Max_Abs_Diff') # Default sort
    sort_order = request.args.get('sort_order', 'desc')
    # Get filters from query string (e.g., ?filter_Type=Corp&filter_Currency=USD)
    active_filters = {k.replace('filter_', ''): v for k, v in request.args.items() if k.startswith('filter_') and v}
    # Get show_sold status
    show_sold_str = request.args.get('show_sold', 'false') # Default to false (only show held)
    show_sold = show_sold_str.lower() == 'true'

    current_app.logger.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}")

    # --- Load Weights/Held Status ---
    # Ensure we use the 'ISIN' column from w_secs.csv
    held_status = load_weights_and_held_status(data_folder, id_col_override='ISIN')
    if held_status.empty:
        current_app.logger.warning("Could not load held status information for comparison.")

    # --- Load and Process Comparison Data ---
    file1='sec_spread.csv'
    file2='sec_spreadSP.csv'
    id_col_name_actual = 'ISIN' # Assume ISIN as default/target

    try:
        current_app.logger.info(f"Loading comparison data: {file1} and {file2} from {data_folder}")
        # Use helper function to load, standardize, and identify columns
        merged_df, static_data, static_cols_actual, id_col_name_actual, held_status_loaded = load_comparison_data(
            data_folder, file1, file2)

        if merged_df.empty:
            raise ValueError("Failed to load one or both comparison files.")

        current_app.logger.info(f"Actual ID column identified for comparison data: '{id_col_name_actual}'")
        current_app.logger.info(f"Calculating comparison statistics using ID column: {id_col_name_actual}...")

        # Calculate stats using the identified columns
        summary_stats = calculate_comparison_stats(merged_df, static_data, id_col=id_col_name_actual)
        current_app.logger.info(f"Finished calculating stats. Summary shape: {summary_stats.shape}")

        # Prepare filter options based on actual static columns found in the summary
        filter_options = {col: sorted(summary_stats[col].dropna().unique().tolist()) 
                          for col in static_cols_actual if col in summary_stats.columns}

        # --- Merge Held Status ---
        if not held_status.empty and id_col_name_actual in summary_stats.columns:
            # Ensure merge keys are the same type (convert to string as a safe bet)
            if summary_stats[id_col_name_actual].dtype != held_status.index.dtype:
                current_app.logger.info(f"Converted merge keys to string. Original dtypes: summary_stats['{id_col_name_actual}']: {summary_stats[id_col_name_actual].dtype}, held_status.index: {held_status.index.dtype}")
                try:
                    summary_stats[id_col_name_actual] = summary_stats[id_col_name_actual].astype(str)
                    held_status.index = held_status.index.astype(str)
                except Exception as e:
                     current_app.logger.error(f"Failed to convert merge keys to string: {e}")

            current_app.logger.info(f"Attempting to merge held_status (index name: '{held_status.index.name}') with comparison summary_stats on column '{id_col_name_actual}'")
            debug_cols_before = summary_stats.columns.tolist()
            current_app.logger.debug(f"summary_stats columns before merge: {debug_cols_before}")
            current_app.logger.debug(f"held_status index preview before merge: {held_status.index[:5].tolist()}")
            current_app.logger.debug(f"summary_stats ID column ('{id_col_name_actual}') preview before merge: {summary_stats[id_col_name_actual].unique()[:5].tolist()}")
            
            # Rename the Series when merging
            summary_stats = pd.merge(summary_stats, held_status.rename('is_held'), 
                                    left_on=id_col_name_actual, right_index=True, how='left')
            
            debug_cols_after = summary_stats.columns.tolist()
            current_app.logger.debug(f"Columns after merge attempt: {debug_cols_after}")
            held_count = summary_stats['is_held'].notna().sum()
            current_app.logger.info(f"Merged held status. Comparison stats shape: {summary_stats.shape}. 'is_held' column has {held_count} non-NA values.")
            
            if held_count > 0:
                current_app.logger.debug(f"Preview of 'is_held' after merge (first 5 non-NA): {summary_stats[summary_stats['is_held'].notna()]['is_held'].head().to_dict()}")
            else:
                current_app.logger.debug("Preview of 'is_held' after merge (first 5 non-NA): {}")
            
            # Fill NaN in 'is_held'
            if 'is_held' in summary_stats.columns:
                summary_stats['is_held'] = summary_stats['is_held'].fillna(False)
                current_app.logger.info("Filled NA in 'is_held' with False for comparison summary.")
            else:
                current_app.logger.error("'is_held' column not found after comparison merge!")
                summary_stats['is_held'] = False # Add the column as False if merge failed entirely

        else:
            current_app.logger.warning("Skipping merge with held_status: held_status is empty or ID column mismatch.")
            summary_stats['is_held'] = False # Assume not held if we can't merge

        # --- Apply Filters ---
        filtered_stats = summary_stats.copy()
        # Apply holding filter first if needed
        if not show_sold:
             held_count_before = len(filtered_stats)
             filtered_stats = filtered_stats[filtered_stats['is_held'] == True]
             held_count_after = len(filtered_stats)
             current_app.logger.info(f"Applied 'Show Held Only' filter. Kept {held_count_after} out of {held_count_before} securities.")
             if held_count_after == 0:
                 current_app.logger.warning("No securities remaining after applying holding status filter.")

        # Apply other active filters
        for col, value in active_filters.items():
            if col in filtered_stats.columns:
                count_before = len(filtered_stats)
                try:
                    # Try direct comparison first
                    filtered_stats = filtered_stats[filtered_stats[col] == value]
                except TypeError:
                     try:
                         # If direct comparison fails (mixed types), try converting both to string
                         filtered_stats = filtered_stats[filtered_stats[col].astype(str) == str(value)]
                         current_app.logger.warning(f"Applied filter {col}={value} after converting column to string due to type mismatch.")
                     except Exception as e_filter:
                         current_app.logger.error(f"Could not apply filter {col}={value}: {e_filter}")
                count_after = len(filtered_stats)
                current_app.logger.info(f"Applied filter: {col} == '{value}'. Kept {count_after}/{count_before} rows.")

        # --- Handle No Data ---
        if filtered_stats.empty:
            message = "No comparison data available matching the current filters."
            # Try to provide a more helpful message
            if not show_sold and 'is_held' in summary_stats.columns and summary_stats['is_held'].any(): # Check if any securities were held *before* filtering
                 message = "No *currently held* securities match the other filters. Try enabling 'Show Sold Securities'."
            elif not active_filters and not show_sold:
                  message = "No currently held securities found in the comparison data. Try enabling 'Show Sold Securities'."
            elif not active_filters and show_sold:
                   message = "No comparison data found in the source files."

            current_app.logger.warning(message)
            return render_template('comparison_page.html',
                                   table_data=[],
                                   columns_to_display=[],
                                   id_column_name=id_col_name_actual,
                                   message=message,
                                   pagination=None,
                                   current_sort_by=sort_by,
                                   current_sort_order=sort_order,
                                   filter_options=filter_options,
                                   active_filters=active_filters,
                                   show_sold=show_sold)

        # --- Sorting ---
        if sort_by in filtered_stats.columns:
            try:
                # Define numeric columns for proper sorting
                numeric_cols = ['Level_Correlation', 'Change_Correlation', 'Mean_Abs_Diff', 'Max_Abs_Diff', 'Max_Orig', 'Min_Orig', 'Max_New', 'Min_New']
                if sort_by in numeric_cols:
                    filtered_stats[sort_by] = pd.to_numeric(filtered_stats[sort_by], errors='coerce')
                    # Ensure NaNs are handled consistently
                    na_position = 'last' if sort_order == 'asc' else 'first' # Sort NaNs last for asc, first for desc
                    filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=(sort_order == 'asc'), na_position=na_position)
                else:
                     # Sort non-numeric columns case-insensitively
                     filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=(sort_order == 'asc'), key=lambda col: col.astype(str).str.lower())
                current_app.logger.info(f"Sorted data by '{sort_by}' ({sort_order}).")
            except Exception as e:
                current_app.logger.error(f"Error sorting data by {sort_by}: {e}")
        
        # --- Pagination ---
        per_page = 50 # Number of items per page
        total_items = len(filtered_stats)
        total_pages = math.ceil(total_items / per_page)
        total_pages = max(1, total_pages)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_data = filtered_stats.iloc[start_index:end_index]
        current_app.logger.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Displaying items {start_index}-{end_index-1}")

        page_window = 2
        start_page_display = max(1, page - page_window)
        end_page_display = min(total_pages, page + page_window)

        # Create pagination context dictionary
        pagination = {
            'page': page,
            'per_page': per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1,
            'start_page_display': start_page_display,
            'end_page_display': end_page_display,
            # Function to generate URLs for pagination links, preserving state
            'url_for_page': lambda p: url_for('comparison_bp.summary', 
                                            page=p, 
                                            sort_by=sort_by, 
                                            sort_order=sort_order, 
                                            show_sold=str(show_sold).lower(),
                                            **{f'filter_{k}': v for k, v in active_filters.items()})
        }

        # Convert paginated data to list of dicts for the template
        table_data_dict = paginated_data.to_dict(orient='records')

        # Define columns to display in the summary table (ensure they exist in the data)
        columns_to_display = [id_col_name_actual, 'Type', 'Currency', 'Funds', 'Level_Correlation', 'Change_Correlation', 'Mean_Abs_Diff', 'Max_Abs_Diff', 'Same_Date_Range', 'is_held']
        columns_to_display = [col for col in columns_to_display if col in paginated_data.columns]


        current_app.logger.info(f"Rendering comparison summary page {page}/{pagination['total_pages']} with {len(table_data_dict)} rows.")
        return render_template('comparison_page.html',
                               table_data=table_data_dict,
                               columns_to_display=columns_to_display,
                               id_column_name=id_col_name_actual, # Pass the actual ID column name
                               pagination=pagination,
                               current_sort_by=sort_by,
                               current_sort_order=sort_order,
                               filter_options=filter_options,
                               active_filters=active_filters,
                               show_sold=show_sold,
                               message=None) # Clear message if data is found

    except FileNotFoundError as e:
        current_app.logger.error(f"Comparison file not found: {e}", exc_info=True)
        flash(f"Error: Required comparison file not found ({e.filename}). Please check the Data folder.", 'danger')
        return render_template('comparison_page.html', table_data=[], columns_to_display=[], pagination=None, message=f"Error: Could not find file {e.filename}.", id_column_name='ISIN', filter_options={}, active_filters={}, show_sold=show_sold)
    except Exception as e:
        current_app.logger.error(f"Error generating comparison summary: {e}", exc_info=True)
        flash(f"An unexpected error occurred during comparison: {e}", 'danger')
        return render_template('comparison_page.html', table_data=[], columns_to_display=[], pagination=None, message=f"An unexpected error occurred: {e}", id_column_name='ISIN', filter_options={}, active_filters={}, show_sold=show_sold)


@comparison_bp.route('/comparison/details/<path:security_id>')
def comparison_details(security_id):
    """Displays side-by-side historical charts for a specific security."""
    current_app.logger.info(f"--- Starting Comparison Detail Request for Security ID: {security_id} ---")
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    try:
        # Pass the absolute data folder path here
        merged_df, static_data, common_static_cols, id_col, _ = load_comparison_data(data_folder)
        if merged_df.empty:
            current_app.logger.warning("Merged data is empty, cannot show details.")
            return "Error: Could not load comparison data.", 404
        if id_col is None or id_col not in merged_df.columns:
             current_app.logger.error(f"ID column ('{id_col}') not found in merged data for details view.")
             return "Error: Could not identify security ID column in data.", 500

        # Filter using the actual ID column name
        security_data = merged_df[merged_df[id_col] == security_id].copy()

        if security_data.empty:
            return "Security ID not found", 404

        # Get the static data for this specific security
        sec_static_data = static_data[static_data[id_col] == security_id]

        # Recalculate detailed stats for this security, passing the correct ID column
        stats_df = calculate_comparison_stats(security_data.copy(), sec_static_data, id_col=id_col)
        security_stats = stats_df.iloc[0].where(pd.notnull(stats_df.iloc[0]), None).to_dict() if not stats_df.empty else {}

        # Prepare chart data
        security_data['Date_Str'] = security_data['Date'].dt.strftime('%Y-%m-%d')
        
        # Convert NaN to None using list comprehension after .tolist()
        data_orig = security_data['Value_Orig'].tolist()
        data_orig_processed = [None if pd.isna(x) else x for x in data_orig]
        
        data_new = security_data['Value_New'].tolist()
        data_new_processed = [None if pd.isna(x) else x for x in data_new]
        
        chart_data = {
            'labels': security_data['Date_Str'].tolist(),
            'datasets': [
                {
                    'label': 'Original Spread (Sec_spread)',
                    'data': data_orig_processed, # Use processed list
                    'borderColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)],
                    'tension': 0.1
                },
                {
                    'label': 'New Spread (Sec_spreadSP)',
                    'data': data_new_processed, # Use processed list
                    'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)],
                    'tension': 0.1
                }
            ]
        }
        
        # Get static attributes for display (use actual_id_col if it's 'Security Name')
        # Best to get from security_stats which should now include merged static data
        security_name_display = security_stats.get('Security Name', security_id) if id_col == 'Security Name' else security_id
        
        # If 'Security Name' is not the ID, try to get it from stats
        if id_col != 'Security Name' and 'Security Name' in security_stats:
             security_name_display = security_stats.get('Security Name', security_id)

        return render_template('comparison_details_page.html',
                               security_id=security_id,
                               security_name=security_name_display,
                               chart_data=chart_data, # Pass as JSONifiable dict
                               stats=security_stats, # Pass comparison stats
                               id_column_name=id_col) # Pass actual ID col name


    except Exception as e:
        current_app.logger.exception(f"Error generating comparison details page for {security_id}.")
        return f"An error occurred: {e}", 500 