# views/duration_comparison_views.py
# This module defines the Flask Blueprint for comparing two security duration datasets.
# It includes routes for a summary view listing securities with comparison metrics
# and a detail view showing overlayed time-series charts and statistics for a single security.

from flask import Blueprint, render_template, request, current_app, jsonify, url_for
import pandas as pd
import os
import logging
import math # Add math for pagination calculation
from pathlib import Path
import re
from datetime import datetime

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

# Assuming security_processing and utils are in the parent directory or configured in PYTHONPATH
try:
    from security_processing import load_and_process_security_data # May need adjustments
    from utils import parse_fund_list # Example utility
    from config import COLOR_PALETTE
except ImportError:
    # Handle potential import errors if the structure is different
    logging.error("Could not import required modules from parent directory.")
    # Add fallback imports or path adjustments if necessary
    # Example: sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from ..security_processing import load_and_process_security_data
    from ..utils import parse_fund_list
    from ..config import COLOR_PALETTE


duration_comparison_bp = Blueprint('duration_comparison_bp', __name__,
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
        # Use our local _is_date_like function
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


def load_duration_comparison_data(data_folder_path: str, file1='sec_duration.csv', file2='sec_durationSP.csv'):
    """Loads, processes, merges data from two security duration files, and gets held status.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        file1 (str, optional): Filename for the first dataset. Defaults to 'sec_duration.csv'.
        file2 (str, optional): Filename for the second dataset. Defaults to 'sec_durationSP.csv'.

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name, held_status)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None, pd.Series(dtype=bool)) on error.
    """
    log = current_app.logger # Use app logger
    log.info(f"Loading duration comparison data: {file1} and {file2} from {data_folder_path}")
    if not data_folder_path:
        log.error("No data_folder_path provided to load_duration_comparison_data.")
        return pd.DataFrame(), pd.DataFrame(), [], None, pd.Series(dtype=bool)

    # Load held status first (uses its own corrected loading logic)
    held_status = load_weights_and_held_status(data_folder_path)

    # Pass the absolute data folder path to the loading functions
    df1, static_cols1 = load_and_process_security_data(file1, data_folder_path)
    df2, static_cols2 = load_and_process_security_data(file2, data_folder_path)

    if df1.empty or df2.empty:
        log.warning(f"One or both duration dataframes are empty after loading. File1 empty: {df1.empty}, File2 empty: {df2.empty}")
        # Return held_status even if data is empty, as it might be needed
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    # --- Verify Index and Get Actual Names ---
    if df1.index.nlevels != 2 or df2.index.nlevels != 2:
        log.error("One or both duration dataframes do not have the expected 2 index levels after loading.")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    # Assume index names are consistent between df1 and df2 as they use the same loader
    date_level_name, id_level_name = df1.index.names
    log.info(f"Duration data index levels identified: Date='{date_level_name}', ID='{id_level_name}'")

    # --- Reset Index ---
    df1 = df1.reset_index()
    df2 = df2.reset_index()
    log.debug(f"Duration df1 columns after reset: {df1.columns.tolist()}")
    log.debug(f"Duration df2 columns after reset: {df2.columns.tolist()}")
    
    # --- Check Required Columns (Post-Reset) ---
    required_cols_df1 = [id_level_name, date_level_name, 'Value']
    required_cols_df2 = [id_level_name, date_level_name, 'Value'] # Assuming Value is standard output name
    
    missing_cols_df1 = [col for col in required_cols_df1 if col not in df1.columns]
    missing_cols_df2 = [col for col in required_cols_df2 if col not in df2.columns]

    if missing_cols_df1 or missing_cols_df2:
        log.error(f"Missing required columns after index reset. Df1 missing: {missing_cols_df1}, Df2 missing: {missing_cols_df2}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    # Common static columns (excluding the ID column which is now standard)
    common_static_cols = list(set(static_cols1) & set(static_cols2))
    if id_level_name in common_static_cols:
        common_static_cols.remove(id_level_name)
        log.debug(f"Removed ID column '{id_level_name}' from common_static_cols list.")
        
    # Ensure 'Value' is not accidentally in common_static_cols
    if 'Value' in common_static_cols:
        common_static_cols.remove('Value')

    # --- Merge Preparation (Using Correct Column Names) ---
    try:
        # Select using the dynamically identified date and id column names
        df1_merge = df1[[id_level_name, date_level_name, 'Value'] + common_static_cols].rename(columns={'Value': 'Value_Orig'})
        df2_merge = df2[[id_level_name, date_level_name, 'Value']].rename(columns={'Value': 'Value_New'})
    except KeyError as e:
        # This should be less likely now, but keep for safety
        log.error(f"KeyError during merge preparation using dynamic names '{id_level_name}', '{date_level_name}': {e}. Df1 cols: {df1.columns.tolist()}, Df2 cols: {df2.columns.tolist()}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    # --- Perform Merge ---
    # Merge using the dynamic date and id column names
    merged_df = pd.merge(df1_merge, df2_merge, on=[id_level_name, date_level_name], how='outer')
    merged_df = merged_df.sort_values(by=[id_level_name, date_level_name])
    
    # Calculate changes using the dynamic ID column name for grouping
    merged_df['Change_Orig'] = merged_df.groupby(id_level_name)['Value_Orig'].diff()
    merged_df['Change_New'] = merged_df.groupby(id_level_name)['Value_New'].diff()

    # Extract static data using the dynamic ID column name
    static_data = merged_df.groupby(id_level_name)[common_static_cols].last().reset_index()

    log.info(f"Successfully merged duration data. Shape: {merged_df.shape}")
    # Return the dynamic ID column name for use in later functions
    return merged_df, static_data, common_static_cols, id_level_name, held_status


def calculate_comparison_stats(merged_df, static_data, id_col):
    """Calculates comparison statistics for each security's duration.

    Args:
        merged_df (pd.DataFrame): The merged dataframe of original and new duration values.
        static_data (pd.DataFrame): DataFrame with static info per security.
        id_col (str): The name of the column containing the Security ID/Name.
    """
    log = current_app.logger # Use app logger
    if merged_df.empty:
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(f"Specified id_col '{id_col}' not found in merged_df columns: {merged_df.columns.tolist()}")
        return pd.DataFrame() # Cannot group without the ID column

    log.info(f"Calculating duration comparison statistics using ID column: {id_col}...")

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

        if len(valid_changes) >= 2:
            change_corr = valid_changes['Change_Orig_Corr'].corr(valid_changes['Change_New_Corr'])
            sec_stats['Change_Correlation'] = change_corr if pd.notna(change_corr) else None
        else:
            sec_stats['Change_Correlation'] = None
            log.debug(f"Cannot calculate Duration Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}.")

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
         log.warning(f"Could not merge static data back for duration comparison. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns}).")

    log.info(f"Finished calculating duration stats. Summary shape: {summary_df.shape}")
    return summary_df


# --- Routes ---

@duration_comparison_bp.route('/duration_comparison/summary') # Updated route
def summary():
    """Displays the duration comparison summary page with server-side filtering, sorting, and pagination."""
    current_app.logger.info("--- Starting Duration Comparison Summary Request ---")
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    try:
        # --- Get Request Parameters ---
        page = request.args.get('page', 1, type=int)
        sort_by = request.args.get('sort_by', 'Change_Correlation') # Default sort
        sort_order = request.args.get('sort_order', 'desc').lower()
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        ascending = sort_order == 'asc'

        # NEW: Get holding status filter
        show_sold = request.args.get('show_sold', 'false').lower() == 'true'

        # Get active filters (ensuring keys are correct)
        active_filters = {k.replace('filter_', ''): v
                          for k, v in request.args.items()
                          if k.startswith('filter_') and v}
        current_app.logger.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}")

        # --- Load and Prepare Data ---
        merged_data, static_data, static_cols, actual_id_col, held_status = load_duration_comparison_data(data_folder)

        if actual_id_col is None:
            current_app.logger.error("Failed to get ID column name during duration data loading.")
            return "Error loading duration comparison data: Could not determine ID column.", 500
        else:
            current_app.logger.info(f"Actual ID column identified for duration comparison data: '{actual_id_col}'")

        summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

        if summary_stats.empty:
            current_app.logger.info("No duration summary statistics could be calculated.")
            return render_template('duration_comparison_page.html', # Updated template
                                   table_data=[],
                                   columns_to_display=[],
                                   id_column_name=actual_id_col,
                                   filter_options={},
                                   active_filters={},
                                   current_sort_by=sort_by,
                                   current_sort_order=sort_order,
                                   pagination=None,
                                   show_sold=show_sold, # Pass filter status
                                   message="No duration comparison data available.")

        # --- Merge Held Status ---
        if not held_status.empty and actual_id_col in summary_stats.columns:
            # --- Convert merge keys to string BEFORE merging --- 
            try:
                original_dtype_stats = summary_stats[actual_id_col].dtype
                original_dtype_held = held_status.index.dtype
                summary_stats[actual_id_col] = summary_stats[actual_id_col].astype(str)
                held_status.index = held_status.index.astype(str)
                current_app.logger.info(f"Converted merge keys to string for duration. Original dtypes: summary_stats['{actual_id_col}']: {original_dtype_stats}, held_status.index: {original_dtype_held}")
            except Exception as e:
                current_app.logger.error(f"Error converting duration merge keys to string: {e}. Merge might fail.")

            # --- Add PRE-MERGE logging ---
            current_app.logger.info(f"PRE-MERGE CHECK: summary_stats ID column ('{actual_id_col}') dtype: {summary_stats[actual_id_col].dtype}, held_status index ('{held_status.index.name}') dtype: {held_status.index.dtype}")
            current_app.logger.info(f"PRE-MERGE CHECK: summary_stats ID column name: '{actual_id_col}', held_status index name: '{held_status.index.name}'")
            if actual_id_col != held_status.index.name:
                 current_app.logger.error(f"CRITICAL: Mismatch between duration summary_stats merge column ('{actual_id_col}') and held_status index name ('{held_status.index.name}'). Merge will likely fail or produce incorrect results.")
            # --- End PRE-MERGE logging ---

            current_app.logger.info(f"Attempting to merge held_status (index name: '{held_status.index.name}') with duration summary_stats on column '{actual_id_col}'")
            debug_cols_before = summary_stats.columns.tolist()
            current_app.logger.debug(f"summary_stats columns before merge: {debug_cols_before}")
            current_app.logger.debug(f"held_status index preview before merge: {held_status.index[:5].tolist()}")
            current_app.logger.debug(f"summary_stats ID column ('{actual_id_col}') preview before merge: {summary_stats[actual_id_col].unique()[:5].tolist()}")
            
            # Add explicit rename to 'is_held' when merging
            summary_stats = pd.merge(summary_stats, held_status.rename('is_held'), 
                                     left_on=actual_id_col, right_index=True, how='left')
            
            debug_cols_after = summary_stats.columns.tolist()
            current_app.logger.debug(f"Columns after merge attempt: {debug_cols_after}")
            held_count = summary_stats['is_held'].notna().sum()
            current_app.logger.info(f"Merged held status. Duration stats shape: {summary_stats.shape}. 'is_held' column has {held_count} non-NA values.")
            
            if held_count > 0:
                current_app.logger.debug(f"Preview of 'is_held' after merge (first 5 non-NA): {summary_stats[summary_stats['is_held'].notna()]['is_held'].head().to_dict()}")
            else:
                current_app.logger.debug("Preview of 'is_held' after merge (first 5 non-NA): {}")
            
            # Fill NaN in 'is_held'
            if 'is_held' in summary_stats.columns:
                summary_stats['is_held'] = summary_stats['is_held'].fillna(False)
                current_app.logger.info(f"Filled NA in 'is_held' with False for duration summary.")
            else:
                current_app.logger.error("'is_held' column not found after duration merge!")
                summary_stats['is_held'] = False # Add the column as False if merge failed entirely

        else:
            current_app.logger.warning(f"Could not merge held status for duration data. held_status empty: {held_status.empty}, '{actual_id_col}' in summary_stats: {actual_id_col in summary_stats.columns}")
            summary_stats['is_held'] = False

        # --- Apply Holding Status Filter ---
        original_count = len(summary_stats)
        if not show_sold:
            summary_stats = summary_stats[summary_stats['is_held'] == True]
            current_app.logger.info(f"Applied 'Show Held Only' filter. Kept {len(summary_stats)} out of {original_count} securities.")
        else:
            current_app.logger.info("Skipping 'Show Held Only' filter (show_sold is True).")

        if summary_stats.empty:
             current_app.logger.info("No securities remaining after applying holding status filter.")
             return render_template('duration_comparison_page.html', # Updated template
                                    table_data=[],
                                    columns_to_display=[actual_id_col] + static_cols, # Show basic cols
                                    id_column_name=actual_id_col,
                                    filter_options={},
                                    active_filters={},
                                    current_sort_by=sort_by,
                                    current_sort_order=sort_order,
                                    pagination=None,
                                    show_sold=show_sold, # Pass filter status
                                    message="No currently held securities found.")

        # --- Collect Filter Options (From Data *After* Holding Filter) --- 
        filter_options = {}
        potential_filter_cols = static_cols 
        for col in potential_filter_cols:
            if col in summary_stats.columns:
                unique_vals = summary_stats[col].dropna().unique().tolist()
                try:
                    sorted_vals = sorted(unique_vals, key=lambda x: (isinstance(x, (int, float)), x))
                except TypeError:
                    sorted_vals = sorted(unique_vals, key=str)
                filter_options[col] = sorted_vals
        final_filter_options = dict(sorted(filter_options.items())) # Sort filter dropdowns alphabetically
        current_app.logger.info(f"Filter options generated: {list(final_filter_options.keys())}") # Use final_filter_options

        # --- Apply Static Column Filters --- 
        filtered_data = summary_stats.copy()
        if active_filters:
            current_app.logger.info(f"Applying static column filters: {active_filters}")
            for col, value in active_filters.items():
                if col in filtered_data.columns and value:
                    try:
                        # Robust string comparison
                         filtered_data = filtered_data[filtered_data[col].astype(str).str.lower() == str(value).lower()]
                    except Exception as e:
                        current_app.logger.warning(f"Could not apply filter for column '{col}' with value '{value}'. Error: {e}. Skipping filter.")
                else:
                    current_app.logger.warning(f"Filter column '{col}' not found in data. Skipping filter.")
            current_app.logger.info(f"Data shape after static filtering: {filtered_data.shape}")
        else:
            current_app.logger.info("No active static column filters.")

        if filtered_data.empty:
             current_app.logger.info("No data remaining after applying static column filters.")
             return render_template('duration_comparison_page.html', # Updated template
                                    table_data=[],
                                    columns_to_display=[actual_id_col] + static_cols, # Show basic cols
                                    id_column_name=actual_id_col,
                                    filter_options=final_filter_options, # Show filter options
                                    active_filters=active_filters,
                                    current_sort_by=sort_by,
                                    current_sort_order=sort_order,
                                    pagination=None,
                                    show_sold=show_sold, # Pass filter status
                                    message="No data matches the current filters.")

        # --- Apply Sorting ---
        if sort_by in filtered_data.columns:
            current_app.logger.info(f"Sorting by '{sort_by}' ({'Ascending' if ascending else 'Descending'})")
            na_position = 'last' 
            try:
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
            except Exception as e:
                current_app.logger.error(f"Error during sorting by '{sort_by}': {e}. Falling back to default sort.")
                sort_by = 'Change_Correlation' 
                ascending = False
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
        else:
            current_app.logger.warning(f"Sort column '{sort_by}' not found. Using default ID sort.")
            sort_by = actual_id_col 
            ascending = True
            filtered_data = filtered_data.sort_values(by=actual_id_col, ascending=ascending, na_position='last')

        # --- Pagination ---
        total_items = len(filtered_data)
        safe_per_page = max(1, PER_PAGE_COMPARISON)
        total_pages = math.ceil(total_items / safe_per_page)
        total_pages = max(1, total_pages)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * safe_per_page
        end_index = start_index + safe_per_page
        paginated_data = filtered_data.iloc[start_index:end_index]
        current_app.logger.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Displaying items {start_index}-{end_index-1}")

        page_window = 2
        start_page_display = max(1, page - page_window)
        end_page_display = min(total_pages, page + page_window)

        # --- Prepare for Template ---
        base_cols = [
            'Level_Correlation', 'Change_Correlation',
            'Mean_Abs_Diff', 'Max_Abs_Diff',
            'NaN_Count_Orig', 'NaN_Count_New', 'Total_Points',
            'Same_Date_Range',
            # Add/remove columns as needed
        ]
        columns_to_display = [actual_id_col] + \
                             [col for col in static_cols if col != actual_id_col and col in paginated_data.columns] + \
                             [col for col in base_cols if col in paginated_data.columns]

        table_data = paginated_data.to_dict(orient='records')

        # Format specific columns 
        for row in table_data:
            for col in ['Level_Correlation', 'Change_Correlation']:
                 if col in row and pd.notna(row[col]):
                    row[col] = f"{row[col]:.4f}" 
            # Add date formatting if needed for stats cols

        # Create pagination object
        pagination_context = {
            'page': page,
            'per_page': safe_per_page,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1,
            'start_page_display': start_page_display,
            'end_page_display': end_page_display,
            # Function to generate URLs for pagination links, preserving state
             'url_for_page': lambda p: url_for('duration_comparison_bp.summary', 
                                              page=p, 
                                              sort_by=sort_by, 
                                              sort_order=sort_order, 
                                              show_sold=str(show_sold).lower(), # Pass holding status
                                              **{f'filter_{k}': v for k, v in active_filters.items()})
        }
        current_app.logger.info("--- Successfully Prepared Data for Duration Comparison Template ---")

        return render_template('duration_comparison_page.html', # Updated template
                               table_data=table_data,
                               columns_to_display=columns_to_display,
                               id_column_name=actual_id_col, # Pass the ID column name
                               filter_options=final_filter_options,
                               active_filters=active_filters,
                               current_sort_by=sort_by,
                               current_sort_order=sort_order,
                               pagination=pagination_context,
                               show_sold=show_sold, # Pass holding filter status
                               message=None) # No message if data is present

    except FileNotFoundError as e:
        current_app.logger.error(f"Duration comparison file not found: {e}")
        return f"Error: Required duration comparison file not found ({e.filename}). Check the Data folder.", 404
    except Exception as e:
        current_app.logger.exception("An unexpected error occurred in the duration comparison summary view.") # Log full traceback
        return render_template('duration_comparison_page.html', 
                               message=f"An unexpected error occurred: {e}",
                               table_data=[], pagination=None, filter_options={}, 
                               active_filters={}, show_sold=show_sold, columns_to_display=[], 
                               id_column_name='Security') # Include show_sold in error template


@duration_comparison_bp.route('/duration_comparison/details/<path:security_id>')
def duration_comparison_details(security_id):
    """Displays side-by-side historical duration charts for a specific security."""
    current_app.logger.info(f"--- Starting Duration Comparison Detail Request for Security ID: {security_id} ---")
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    try:
        # Pass the absolute data folder path
        merged_data, static_data, common_static_cols, id_col_name, _ = load_duration_comparison_data(data_folder)

        if id_col_name is None:
             current_app.logger.error(f"Failed to get ID column name for details view (Security: {security_id}).")
             return "Error loading duration comparison data: Could not determine ID column.", 500
        if merged_data.empty:
            current_app.logger.warning(f"Merged duration data is empty for details view (Security: {security_id}).")
            return f"No merged duration data found for Security ID: {security_id}", 404

        # Filter data for the specific security using the correct ID column name
        security_data = merged_data[merged_data[id_col_name] == security_id].copy() # Use .copy()

        if security_data.empty:
            current_app.logger.warning(f"No duration data found for the specific Security ID: {security_id}")
            # Consider checking if the ID exists in the original files?
            return f"Duration data not found for Security ID: {security_id}", 404

        # Get static info for this security (handle potential multiple rows if ID isn't unique, take first)
        static_info = security_data[[id_col_name] + common_static_cols].iloc[0].to_dict() if not security_data.empty else {}

        # Sort by date for charting
        security_data = security_data.sort_values(by='Date')

        # Prepare data for Chart.js
        # Ensure 'Date' is in the correct string format for JSON/JS
        security_data['Date_Str'] = security_data['Date'].dt.strftime('%Y-%m-%d')

        chart_data = {
            'labels': security_data['Date_Str'].tolist(),
            'datasets': [
                {
                    'label': 'Original Duration',
                    'data': security_data['Value_Orig'].where(pd.notna(security_data['Value_Orig']), None).tolist(), # Replace NaN with None for JSON
                    'borderColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)],
                    'fill': False,
                    'tension': 0.1
                },
                {
                    'label': 'New Duration',
                    'data': security_data['Value_New'].where(pd.notna(security_data['Value_New']), None).tolist(), # Replace NaN with None for JSON
                    'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)],
                    'fill': False,
                    'tension': 0.1
                }
            ]
        }

        # Calculate overall statistics for this security
        stats_summary = calculate_comparison_stats(security_data, pd.DataFrame([static_info]), id_col=id_col_name) # Pass single security data
        stats_dict = stats_summary.iloc[0].to_dict() if not stats_summary.empty else {}

         # Format dates and numbers in stats_dict before passing
        for key, value in stats_dict.items():
            if isinstance(value, pd.Timestamp):
                stats_dict[key] = value.strftime('%Y-%m-%d')
            elif isinstance(value, (int, float)):
                 if 'Correlation' in key and pd.notna(value):
                     stats_dict[key] = f"{value:.4f}"
                 elif 'Diff' in key and pd.notna(value):
                      stats_dict[key] = f"{value:.2f}" # Adjust formatting as needed

        current_app.logger.info(f"Successfully prepared data for duration details template (Security: {security_id})")
        return render_template('duration_comparison_details_page.html', # Updated template
                               security_id=security_id,
                               static_info=static_info, # Pass static info
                               chart_data=chart_data,
                               stats_summary=stats_dict) # Pass calculated stats

    except FileNotFoundError as e:
        current_app.logger.error(f"Duration comparison file not found for details view: {e} (Security: {security_id})")
        return f"Error: Required duration comparison file not found ({e.filename}). Check the Data folder.", 404
    except KeyError as e:
         current_app.logger.error(f"KeyError accessing data for security '{security_id}': {e}. ID column used: '{id_col_name}'")
         return f"Error accessing data for security '{security_id}'. It might be missing required columns or have unexpected formatting.", 500
    except Exception as e:
        current_app.logger.exception(f"An unexpected error occurred in the duration comparison details view for security '{security_id}'.") # Log full traceback
        return f"An internal error occurred while processing details for security '{security_id}': {e}", 500 