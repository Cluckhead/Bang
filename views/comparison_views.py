# views/comparison_views.py
# This module defines the Flask Blueprint for comparing two security spread datasets.
# It includes routes for a summary view listing securities with comparison metrics
# and a detail view showing overlayed time-series charts and statistics for a single security.

from flask import Blueprint, render_template, request, current_app, jsonify, url_for
import pandas as pd
import os
import logging
import math # Add math for pagination calculation

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


comparison_bp = Blueprint('comparison_bp', __name__,
                        template_folder='../templates',
                        static_folder='../static')

# Configure logging
log = logging.getLogger(__name__)

PER_PAGE_COMPARISON = 50 # Items per page for comparison summary

# --- Data Loading and Processing ---

def load_weights_and_held_status(data_folder_path: str, weights_filename='w_secs.csv'):
    """Loads weights data and determines the latest held status for each security ID.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        weights_filename (str, optional): The name of the weights file. Defaults to 'w_secs.csv'.

    Returns:
        pd.Series: Series indexed by Security ID indicating held status (True/False).
                   Returns an empty Series on error.
    """
    if not data_folder_path:
        log.error("No data_folder_path provided to load_weights_and_held_status.")
        return pd.Series(dtype=bool)

    weights_filepath = os.path.join(data_folder_path, weights_filename)
    log.info(f"Loading weights data from: {weights_filepath}")

    # Pass the full path to the data loading function
    df_weights, _ = load_and_process_security_data(weights_filename, data_folder_path)

    if df_weights.empty:
        log.warning(f"Weights file '{weights_filepath}' is empty or failed to load.")
        return pd.Series(dtype=bool)

    # --- Check index and columns AFTER loading --- 
    if df_weights.index.nlevels != 2:
        log.error(f"Weights file '{weights_filepath}' did not have the expected 2 index levels (Date, ID) after processing.")
        return pd.Series(dtype=bool)
        
    # Get index names dynamically
    date_level_name, id_level_name = df_weights.index.names
    log.info(f"Weights file index levels identified: Date='{date_level_name}', ID='{id_level_name}'")

    # Reset index to access Date and ID as columns
    df_weights = df_weights.reset_index()

    # Check if required columns are present AFTER resetting index
    required_cols = [date_level_name, id_level_name, 'Value']
    missing_cols = [col for col in required_cols if col not in df_weights.columns]
    
    if missing_cols:
        log.error(f"Weights file '{weights_filepath}' is missing required columns after processing and index reset: {missing_cols}. Available columns: {df_weights.columns.tolist()}")
        return pd.Series(dtype=bool)

    # Find the latest date in the weights data using the dynamic date column name
    latest_date = df_weights[date_level_name].max()
    if pd.isna(latest_date):
        log.warning(f"Could not determine the latest date in '{weights_filepath}'.")
        return pd.Series(dtype=bool)

    log.info(f"Latest date in weights file '{weights_filepath}': {latest_date}")

    # Filter for the latest date using the dynamic date column name
    latest_weights = df_weights[df_weights[date_level_name] == latest_date]
    
    # Set index using the dynamic ID column name and check weight > 0
    held_status = latest_weights.set_index(id_level_name)['Value'] > 0
    held_status.name = 'is_held' # Name the series for easier merging later

    log.info(f"Determined held status for {len(held_status)} IDs based on weights on {latest_date}.")
    return held_status


def load_comparison_data(data_folder_path: str, file1='sec_spread.csv', file2='sec_spreadSP.csv'):
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
    df2, static_cols2 = load_and_process_security_data(file2, data_folder_path)

    # Reset index to make Date and ID columns accessible
    if not df1.empty:
        df1 = df1.reset_index()
    if not df2.empty:
        df2 = df2.reset_index()

    # Load held status, passing the data folder path
    held_status = load_weights_and_held_status(data_folder_path) # Uses default 'w_secs.csv'

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
    return merged_df, static_data, common_static_cols, id_col_name, held_status


def calculate_comparison_stats(merged_df, static_data, id_col):
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
    return summary_df


# --- Routes ---

@comparison_bp.route('/comparison/summary')
def summary():
    """Displays the comparison summary page with server-side filtering, sorting, and pagination."""
    log.info("--- Starting Comparison Summary Request ---")
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # --- Get Request Parameters ---
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'Change_Correlation') # Default sort
    sort_order = request.args.get('sort_order', 'desc').lower()
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    ascending = sort_order == 'asc'

    # NEW: Get holding status filter (default to 'false' -> show only held)
    show_sold = request.args.get('show_sold', 'false').lower() == 'true'
    log.info(f"Show Sold filter: {show_sold}")

    # Get active filters (ensuring keys are correct)
    active_filters = {k.replace('filter_', ''): v 
                      for k, v in request.args.items() 
                      if k.startswith('filter_') and v}
    log.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}")

    # --- Load and Prepare Data --- 
    # Capture the actual ID column name and held status returned by the load function
    merged_data, static_data, static_cols, actual_id_col, held_status = load_comparison_data(data_folder)
        
    if actual_id_col is None:
        log.error("Failed to get ID column name during data loading.")
        return "Error loading comparison data: Could not determine ID column.", 500

    # Pass the actual ID column name to the stats calculation function
    summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

    if summary_stats.empty:
         # Log reason if possible
         if merged_data.empty:
             log.info("Merged data was empty, no stats calculated.")
         else:
             log.warning("Merged data was present, but calculation resulted in empty stats DataFrame.")
        
         # Render with message if empty even before filtering
         return render_template('comparison_page.html',
                                table_data=[],
                                columns_to_display=[],
                                id_column_name=actual_id_col,
                                filter_options={},
                                active_filters={},
                                current_sort_by=sort_by,
                                current_sort_order=sort_order,
                                pagination=None,
                                show_sold=show_sold, # Pass filter status
                                message="No comparison data available.")

    # --- Merge Held Status --- 
    if not held_status.empty and actual_id_col in summary_stats.columns:
        summary_stats = pd.merge(summary_stats, held_status, left_on=actual_id_col, right_index=True, how='left')
        # Fill NaN in 'is_held' with False (assume not held if not in weights file/latest date)
        summary_stats['is_held'] = summary_stats['is_held'].fillna(False)
        log.info(f"Merged held status. Stats shape: {summary_stats.shape}")
    else:
        log.warning("Could not merge held status. Weights data might be missing or empty, or ID column mismatch.")
        summary_stats['is_held'] = False # Assume all are not held if merge fails

    # --- Apply Holding Status Filter --- 
    original_count = len(summary_stats)
    if not show_sold:
        summary_stats = summary_stats[summary_stats['is_held'] == True]
        log.info(f"Applied 'Show Held Only' filter. Kept {len(summary_stats)} out of {original_count} securities.")
    else:
        log.info("Skipping 'Show Held Only' filter (show_sold is True).")

    # If filtering by holding status resulted in empty df, render with message
    if summary_stats.empty:
         log.info("No securities remaining after applying holding status filter.")
         return render_template('comparison_page.html',
                                table_data=[],
                                columns_to_display=[actual_id_col] + static_cols, # Show basic cols
                                id_column_name=actual_id_col,
                                filter_options={}, # Filters not relevant now
                                active_filters={},
                                current_sort_by=sort_by,
                                current_sort_order=sort_order,
                                pagination=None,
                                show_sold=show_sold, # Pass filter status
                                message="No currently held securities found.")

    # --- Collect Filter Options (From Dataset *After* Holding Filter) --- 
    filter_options = {}
    # Use static_cols identified earlier
    potential_filter_cols = static_cols 
    for col in potential_filter_cols:
        if col in summary_stats.columns:
            # Get unique non-NA values from the *potentially filtered* stats df
            unique_vals = summary_stats[col].dropna().unique().tolist()
            # Basic type check and sort if possible - Improved Robust Sorting Key
            try:
                unique_vals = sorted(unique_vals, key=lambda x: \
                    (0, float(x)) if isinstance(x, bool) else \
                    (0, x) if isinstance(x, (int, float)) else \
                    (0, float(x)) if isinstance(x, str) and x.replace('.', '', 1).lstrip('-').isdigit() else \
                    (1, str(x)) if isinstance(x, str) else \
                    (2, str(x)) # Fallback for other types, sort as string
                )
            except (TypeError, ValueError) as e:
                log.warning(f"Type error or value error during sorting unique values for column '{col}': {e}. Falling back to simple string sort.")
                try:
                     unique_vals = sorted(str(x) for x in unique_vals)
                except Exception as final_sort_err:
                    log.error(f"Final string sort failed for column '{col}': {final_sort_err}")
                    # Keep original unsorted list if all else fails
            if unique_vals:
                filter_options[col] = unique_vals
    final_filter_options = dict(sorted(filter_options.items())) # Sort filter dropdowns alphabetically

    # --- Apply Static Column Filtering (on potentially pre-filtered data) ---
    filtered_stats = summary_stats.copy()
    if active_filters:
        log.info(f"Applying static column filters: {active_filters}")
        for col, value in active_filters.items():
            if col in filtered_stats.columns and value:
                # Ensure comparison is robust (e.g., string comparison)
                try:
                    filtered_stats = filtered_stats[filtered_stats[col].astype(str).str.lower() == str(value).lower()]
                except Exception as e:
                    log.warning(f"Could not apply filter on column '{col}' with value '{value}'. Error: {e}")
        log.info(f"Stats shape after static filtering: {filtered_stats.shape}")
    else:
         log.info("No active static column filters.")

    # If filtering resulted in empty df, render with message
    if filtered_stats.empty:
         log.info("No data remaining after applying static column filters.")
         return render_template('comparison_page.html',
                                table_data=[],
                                columns_to_display=[actual_id_col] + static_cols, # Show basic cols
                                id_column_name=actual_id_col,
                                filter_options=final_filter_options, # Still show filter options
                                active_filters=active_filters,
                                current_sort_by=sort_by,
                                current_sort_order=sort_order,
                                pagination=None,
                                show_sold=show_sold, # Pass filter status
                                message="No data matches the current filters.")

    # --- Apply Sorting ---
    # Sort the filtered data
    if sort_by in filtered_stats.columns:
        log.info(f"Sorting by '{sort_by}' {sort_order}")
        if pd.api.types.is_numeric_dtype(filtered_stats[sort_by]):
             filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position='last')
        else:
             filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position='last', key=lambda col: col.astype(str).str.lower())
    else:
        log.warning(f"Sort column '{sort_by}' not found in filtered data. Defaulting to ID sort.")
        sort_by = actual_id_col 
        sort_order = 'asc'
        ascending = True
        filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position='last')

    # --- Define Columns to Display ---
    # Identify fund columns 
    fund_cols = sorted([col for col in static_cols if 'fund' in col.lower() and col != actual_id_col])
    other_static_cols = sorted([col for col in static_cols if col != actual_id_col and col not in fund_cols])
    calculated_cols = sorted([col for col in summary_stats.columns # Use summary_stats to get all potential cols
                             if col not in static_cols and col != actual_id_col and
                             col not in ['Start_Date_Orig', 'End_Date_Orig', 'Start_Date_New', 'End_Date_New',
                                          'NaN_Count_Orig', 'NaN_Count_New', 'Total_Points',
                                          'Overall_Start_Date', 'Overall_End_Date', 'is_held']]) # Exclude is_held too

    columns_to_display = [actual_id_col] + other_static_cols + calculated_cols + fund_cols
    log.debug(f"Columns to display: {columns_to_display}")

    # --- Pagination ---
    total_items = len(filtered_stats)
    # This check is now redundant due to earlier checks, but keep for safety
    if total_items == 0:
         log.info("Pagination step: No items remain after all filtering/sorting.") 
         return render_template('comparison_page.html',
                                table_data=[],
                                columns_to_display=columns_to_display, \
                                id_column_name=actual_id_col,
                                filter_options=final_filter_options,
                                active_filters=active_filters,
                                current_sort_by=sort_by,
                                current_sort_order=sort_order,
                                pagination=None,
                                show_sold=show_sold, # Pass filter status
                                message="No data matches the current criteria.")

    safe_per_page = max(1, PER_PAGE_COMPARISON)
    total_pages = math.ceil(total_items / safe_per_page)
    total_pages = max(1, total_pages) 
    page = max(1, min(page, total_pages)) 
    start_index = (page - 1) * safe_per_page
    end_index = start_index + safe_per_page
    log.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Per page={safe_per_page}")
    
    page_window = 2
    start_page_display = max(1, page - page_window)
    end_page_display = min(total_pages, page + page_window)
    
    paginated_stats = filtered_stats.iloc[start_index:end_index]

    # --- Prepare Data for Template ---
    paginated_stats = paginated_stats[[col for col in columns_to_display if col in paginated_stats.columns]]
    table_data_list = paginated_stats.to_dict(orient='records')
    for row in table_data_list:
        for key, value in row.items():
            if pd.isna(value):
                row[key] = None

    pagination_context = {
        'page': page,
        'per_page': safe_per_page,
        'total_pages': total_pages,
        'total_items': total_items,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1,
        'start_page_display': start_page_display, \
        'end_page_display': end_page_display,     \
        # Function to generate URLs for pagination links, preserving ALL filters including show_sold
        'url_for_page': lambda p: url_for('comparison_bp.summary', 
                                          page=p, 
                                          sort_by=sort_by, 
                                          sort_order=sort_order, 
                                          show_sold=str(show_sold).lower(), # Pass holding status
                                          **{f'filter_{k}': v for k, v in active_filters.items()})
    }

    return render_template('comparison_page.html',
                           table_data=table_data_list,
                           columns_to_display=columns_to_display,
                           id_column_name=actual_id_col,
                           filter_options=final_filter_options, # Use sorted options
                           active_filters=active_filters,
                           current_sort_by=sort_by,
                           current_sort_order=sort_order,
                           pagination=pagination_context,
                           show_sold=show_sold, # Pass holding filter status
                           message=None)


@comparison_bp.route('/comparison/details/<path:security_id>')
def comparison_details(security_id):
    """Displays side-by-side historical charts for a specific security."""
    log.info(f"--- Starting Comparison Detail Request for Security ID: {security_id} ---")
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    try:
        # Pass the absolute data folder path here
        merged_df, static_data, common_static_cols, id_col, _ = load_comparison_data(data_folder)
        if merged_df.empty:
            log.warning("Merged data is empty, cannot show details.")
            return "Error: Could not load comparison data.", 404
        if id_col is None or id_col not in merged_df.columns:
             log.error(f"ID column ('{id_col}') not found in merged data for details view.")
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
        log.exception(f"Error generating comparison details page for {security_id}.")
        return f"An error occurred: {e}", 500 