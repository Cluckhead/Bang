# views/spread_duration_comparison_views.py
# This module defines the Flask Blueprint for comparing two security spread duration datasets.
# It includes routes for a summary view listing securities with comparison metrics
# and a detail view showing overlayed time-series charts and statistics for a single security.

from flask import Blueprint, render_template, request, current_app, jsonify, url_for
import pandas as pd
import os
import logging
import math # Add math for pagination calculation
from urllib.parse import unquote # Import unquote

# Assuming security_processing and utils are in the parent directory or configured in PYTHONPATH
try:
    from security_processing import load_and_process_security_data # May need adjustments
    from utils import parse_fund_list # Example utility
    from config import DATA_FOLDER, COLOR_PALETTE
except ImportError:
    # Handle potential import errors if the structure is different
    logging.error("Could not import required modules from parent directory.")
    # Add fallback imports or path adjustments if necessary
    # Example: sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from ..security_processing import load_and_process_security_data
    from ..utils import parse_fund_list
    from ..config import DATA_FOLDER, COLOR_PALETTE


spread_duration_comparison_bp = Blueprint('spread_duration_comparison_bp', __name__,
                        template_folder='../templates',
                        static_folder='../static')

# Configure logging
log = logging.getLogger(__name__)

PER_PAGE_COMPARISON = 50 # Items per page for comparison summary

# --- Data Loading and Processing ---

def load_weights_and_held_status(weights_filename='w_secs.csv'):
    """Loads weights data and determines the latest held status for each ISIN."""
    log.info(f"Loading weights data from: {weights_filename}")
    df_weights, _ = load_and_process_security_data(weights_filename)

    if df_weights.empty:
        log.warning(f"Weights file '{weights_filename}' is empty or failed to load.")
        return pd.Series(dtype=bool)

    if 'ISIN' not in df_weights.columns or 'Date' not in df_weights.columns or 'Value' not in df_weights.columns:
        log.error(f"Weights file '{weights_filename}' is missing required columns (ISIN, Date, Value).")
        return pd.Series(dtype=bool)

    # Ensure Value is numeric
    df_weights['Value'] = pd.to_numeric(df_weights['Value'], errors='coerce')

    # Find the latest entry for each ISIN
    latest_weights = df_weights.loc[df_weights.groupby('ISIN')['Date'].idxmax()]

    # Determine held status (latest weight > 0)
    held_status = latest_weights.set_index('ISIN')['Value'].fillna(0) > 0 # Fill NaN weights with 0
    held_status.name = 'is_held'

    log.info(f"Determined latest held status for {len(held_status)} ISINs from '{weights_filename}'.")
    return held_status


def load_spread_duration_comparison_data(file1='sec_Spread duration.csv', file2='sec_Spread durationSP.csv'):
    """Loads, processes, merges data from two security spread duration files, and gets held status.

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name, held_status)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None, pd.Series(dtype=bool)) on error.
    """
    log.info(f"Loading spread duration comparison data: {file1} and {file2}")
    df1, static_cols1 = load_and_process_security_data(file1)
    df2, static_cols2 = load_and_process_security_data(file2)

    # Load held status
    held_status = load_weights_and_held_status()

    if df1.empty or df2.empty:
        log.warning(f"One or both spread duration dataframes are empty. File1 empty: {df1.empty}, File2 empty: {df2.empty}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    common_static_cols = list(set(static_cols1) & set(static_cols2))

    # Identify ID column - check for 'ISIN' first
    if 'ISIN' in df1.columns:
        id_col_name = 'ISIN'
        log.info(f"Identified ID column from columns: {id_col_name}")
    elif not df1.empty and df1.columns:
        potential_id = df1.columns[0]
        log.warning(f"'ISIN' column not found in df1. Attempting to use first column '{potential_id}' as ID.")
        id_col_name = potential_id
        if id_col_name not in df2.columns:
            log.error(f"Fallback ID column '{id_col_name}' from df1 not found in df2.")
            return pd.DataFrame(), pd.DataFrame(), [], None, held_status
    else:
        log.error("Failed to identify ID column in spread duration data.")
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
        log.error(f"Missing required column for merge preparation in spread duration data: {e}. Df1 cols: {df1.columns.tolist()}, Df2 cols: {df2.columns.tolist()}")
        return pd.DataFrame(), pd.DataFrame(), [], None, held_status

    merged_df = pd.merge(df1_merge, df2_merge, on=[id_col_name, 'Date'], how='outer')
    merged_df = merged_df.sort_values(by=[id_col_name, 'Date'])
    merged_df['Change_Orig'] = merged_df.groupby(id_col_name)['Value_Orig'].diff()
    merged_df['Change_New'] = merged_df.groupby(id_col_name)['Value_New'].diff()

    static_data = merged_df.groupby(id_col_name)[common_static_cols].last().reset_index()

    log.info(f"Successfully merged spread duration data. Shape: {merged_df.shape}")
    return merged_df, static_data, common_static_cols, id_col_name, held_status


def calculate_comparison_stats(merged_df, static_data, id_col):
    """Calculates comparison statistics for each security's spread duration.

    Args:
        merged_df (pd.DataFrame): The merged dataframe of original and new spread duration values.
        static_data (pd.DataFrame): DataFrame with static info per security.
        id_col (str): The name of the column containing the Security ID/Name.
    """
    if merged_df.empty:
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(f"Specified id_col '{id_col}' not found in merged_df columns: {merged_df.columns.tolist()}")
        return pd.DataFrame() # Cannot group without the ID column

    log.info(f"Calculating spread duration comparison statistics using ID column: {id_col}...")

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
            log.debug(f"Cannot calculate Spread Duration Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}.")

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
         log.warning(f"Could not merge static data back for spread duration comparison. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns}).")

    log.info(f"Finished calculating spread duration stats. Summary shape: {summary_df.shape}")
    return summary_df


# --- Routes ---

@spread_duration_comparison_bp.route('/spread_duration_comparison/summary') # Updated route
def summary():
    """Displays the spread duration comparison summary page with server-side filtering, sorting, and pagination."""
    log.info("--- Starting Spread Duration Comparison Summary Request ---")
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
        log.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}")

        # --- Load and Prepare Data ---
        merged_data, static_data, static_cols, actual_id_col, held_status = load_spread_duration_comparison_data()

        if actual_id_col is None:
            log.error("Failed to get ID column name during spread duration data loading.")
            return "Error loading spread duration comparison data: Could not determine ID column.", 500

        summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

        if summary_stats.empty:
             log.info("No spread duration summary statistics could be calculated.")
             return render_template('spread_duration_comparison_page.html', # Updated template
                                    table_data=[],
                                    columns_to_display=[],
                                    id_column_name=actual_id_col,
                                    filter_options={},
                                    active_filters={},
                                    current_sort_by=sort_by,
                                    current_sort_order=sort_order,
                                    pagination=None,
                                    show_sold=show_sold, # Pass filter status
                                    message="No spread duration comparison data available.")

        # --- Merge Held Status --- 
        if not held_status.empty and actual_id_col in summary_stats.columns:
            summary_stats = pd.merge(summary_stats, held_status, left_on=actual_id_col, right_index=True, how='left')
            summary_stats['is_held'] = summary_stats['is_held'].fillna(False)
            log.info(f"Merged held status. Stats shape: {summary_stats.shape}")
        else:
            log.warning("Could not merge held status for spread duration data.")
            summary_stats['is_held'] = False

        # --- Apply Holding Status Filter --- 
        original_count = len(summary_stats)
        if not show_sold:
            summary_stats = summary_stats[summary_stats['is_held'] == True]
            log.info(f"Applied 'Show Held Only' filter. Kept {len(summary_stats)} out of {original_count} securities.")
        else:
            log.info("Skipping 'Show Held Only' filter (show_sold is True).")

        if summary_stats.empty:
             log.info("No securities remaining after applying holding status filter.")
             return render_template('spread_duration_comparison_page.html', # Updated template
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
        log.info(f"Filter options generated: {list(final_filter_options.keys())}") # Use final_filter_options

        # --- Apply Static Column Filters --- 
        filtered_data = summary_stats.copy()
        if active_filters:
            log.info(f"Applying static column filters: {active_filters}")
            for col, value in active_filters.items():
                if col in filtered_data.columns and value:
                    try:
                        # Robust string comparison
                         filtered_data = filtered_data[filtered_data[col].astype(str).str.lower() == str(value).lower()]
                    except Exception as e:
                        log.warning(f"Could not apply filter for column '{col}' with value '{value}'. Error: {e}. Skipping filter.")
                else:
                    log.warning(f"Filter column '{col}' not found in data. Skipping filter.")
            log.info(f"Data shape after static filtering: {filtered_data.shape}")
        else:
            log.info("No active static column filters.")

        if filtered_data.empty:
             log.info("No data remaining after applying static column filters.")
             return render_template('spread_duration_comparison_page.html', # Updated template
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
            log.info(f"Sorting by '{sort_by}' ({'Ascending' if ascending else 'Descending'})")
            na_position = 'last' 
            try:
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
            except Exception as e:
                log.error(f"Error during sorting by '{sort_by}': {e}. Falling back to default sort.")
                sort_by = 'Change_Correlation' 
                ascending = False
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
        else:
            log.warning(f"Sort column '{sort_by}' not found. Using default ID sort.")
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
        log.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Displaying items {start_index}-{end_index-1}")

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
             'url_for_page': lambda p: url_for('spread_duration_comparison_bp.summary', 
                                              page=p, 
                                              sort_by=sort_by, 
                                              sort_order=sort_order, 
                                              show_sold=str(show_sold).lower(), # Pass holding status
                                              **{f'filter_{k}': v for k, v in active_filters.items()})
        }
        log.info("--- Successfully Prepared Data for Spread Duration Comparison Template ---")

        return render_template('spread_duration_comparison_page.html', # Updated template
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
        log.error(f"Spread duration comparison file not found: {e}")
        return f"Error: Required spread duration comparison file not found ({e.filename}). Check the Data folder.", 404
    except Exception as e:
        log.exception("An unexpected error occurred in the spread duration comparison summary view.") # Log full traceback
        return render_template('spread_duration_comparison_page.html', 
                               message=f"An unexpected error occurred: {e}",
                               table_data=[], pagination=None, filter_options={}, 
                               active_filters={}, show_sold=show_sold, columns_to_display=[], 
                               id_column_name='Security') # Include show_sold in error template


@spread_duration_comparison_bp.route('/spread_duration_comparison/details/<path:security_id>')
def spread_duration_comparison_details(security_id):
    """Displays side-by-side historical spread duration charts for a specific security."""
    # --- Debugging: Log the received security ID --- START
    log.info(f"--- Entering spread_duration_comparison_details ---")
    log.info(f"Received security_id (raw from path): '{security_id}' (Type: {type(security_id)})")

    # --- Explicitly Decode the ID --- START
    try:
        decoded_security_id = unquote(security_id)
        log.info(f"Decoded security_id: '{decoded_security_id}' (Type: {type(decoded_security_id)})")
    except Exception as e:
        log.error(f"Error decoding security_id '{security_id}': {e}")
        # Fallback or return error? Using original for now, but likely to fail.
        decoded_security_id = security_id
        log.warning("Proceeding with potentially undecoded security_id due to decoding error.")
    # --- Explicitly Decode the ID --- END

    log.info(f"Fetching spread duration comparison details for security: {decoded_security_id}") # Use decoded ID in log

    try:
        # Load the merged data again (could potentially cache this)
        # Specify filenames explicitly
        merged_df, _, common_static_cols, id_col_name, _ = load_spread_duration_comparison_data(file1='sec_Spread duration.csv', file2='sec_Spread durationSP.csv')

        if id_col_name is None:
             log.error(f"Failed to get ID column name for details view (Security: {decoded_security_id}).") # Use decoded ID
             return "Error loading spread duration comparison data: Could not determine ID column.", 500
        if merged_df.empty:
            log.warning(f"Merged spread duration data is empty for details view (Security: {decoded_security_id}).") # Use decoded ID
            return f"No merged spread duration data found for Security ID: {decoded_security_id}", 404 # Use decoded ID

        # --- Debugging: Log ID column and sample IDs from DataFrame --- START
        log.info(f"Identified ID column name: '{id_col_name}'")
        if id_col_name in merged_df.columns:
             sample_ids = merged_df[id_col_name].unique()[:5] # Get first 5 unique IDs
             log.info(f"Sample IDs from DataFrame column '{id_col_name}': {sample_ids}")
             log.info(f"Data type of column '{id_col_name}': {merged_df[id_col_name].dtype}")
        else:
            log.warning(f"ID column '{id_col_name}' not found in merged_df columns for sampling.")
        # --- Debugging: Log ID column and sample IDs from DataFrame --- END

        # Filter data for the specific security using the DECODED ID and correct ID column name
        security_data = merged_df[merged_df[id_col_name] == decoded_security_id].copy() # Use decoded_security_id

        if security_data.empty:
            log.warning(f"No spread duration data found after filtering for the specific Security ID: {decoded_security_id}") # Use decoded ID
            # Consider checking if the ID exists in the original files?
            return f"Spread Duration data not found for Security ID: {decoded_security_id}", 404 # Use decoded ID

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
                    'label': 'Original Spread Duration', # Updated Label
                    'data': security_data['Value_Orig'].where(pd.notna(security_data['Value_Orig']), None).tolist(), # Replace NaN with None for JSON
                    'borderColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)],
                    'fill': False,
                    'tension': 0.1
                },
                {
                    'label': 'New Spread Duration', # Updated Label
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

        log.info(f"Successfully prepared data for spread duration details template (Security: {decoded_security_id})") # Use decoded ID
        return render_template('spread_duration_comparison_details_page.html', # Updated template
                               security_id=decoded_security_id, # Pass decoded ID to template
                               static_info=static_info, # Pass static info
                               chart_data=chart_data,
                               stats_summary=stats_dict) # Pass calculated stats

    except FileNotFoundError as e:
        log.error(f"Spread duration comparison file not found for details view: {e} (Security: {decoded_security_id})") # Use decoded ID
        return f"Error: Required spread duration comparison file not found ({e.filename}). Check the Data folder.", 404
    except KeyError as e:
         log.error(f"KeyError accessing data for security '{decoded_security_id}': {e}. ID column used: '{id_col_name}'") # Use decoded ID
         return f"Error accessing data for security '{decoded_security_id}'. It might be missing required columns or have unexpected formatting.", 500 # Use decoded ID
    except Exception as e:
        log.exception(f"An unexpected error occurred in the spread duration comparison details view for security '{decoded_security_id}'.") # Use decoded ID
        return f"An internal error occurred while processing details for security '{decoded_security_id}': {e}", 500 # Use decoded ID 