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

def load_comparison_data(file1='sec_Spread duration.csv', file2='sec_Spread durationSP.csv'): # Updated filenames
    """Loads, processes, and merges data from two security spread duration files.

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None) on error.
    """
    log.info(f"Loading spread duration comparison data: {file1} and {file2}")
    # Pass only the filename, as load_and_process_security_data prepends DATA_FOLDER internally
    df1, static_cols1 = load_and_process_security_data(file1)
    df2, static_cols2 = load_and_process_security_data(file2)

    if df1.empty or df2.empty:
        log.warning(f"One or both spread duration dataframes are empty. File1 empty: {df1.empty}, File2 empty: {df2.empty}")
        return pd.DataFrame(), pd.DataFrame(), [], None # Return None for id_col_name

    # Identify common static columns (excluding the ID column used for merging)
    common_static_cols = list(set(static_cols1) & set(static_cols2))

    # Get the actual ID column name (should be the same for both, use df1)
    if df1.index.nlevels == 2:
        id_col_name = df1.index.names[1] # Assuming 'Security ID'/Name is the second level
        log.info(f"Identified ID column from index: {id_col_name}")
    else:
        log.error("Processed Spread Duration DataFrame df1 does not have the expected 2-level MultiIndex.")
        return pd.DataFrame(), pd.DataFrame(), [], None # Return None for id_col_name

    # Prepare for merge - keep only necessary columns and rename Value columns
    df1_merge = df1.reset_index()[[id_col_name, 'Date', 'Value'] + common_static_cols].rename(columns={'Value': 'Value_Orig'})
    df2_merge = df2.reset_index()[[id_col_name, 'Date', 'Value']].rename(columns={'Value': 'Value_New'}) # Don't need static cols twice

    # Perform an outer merge to keep all dates and securities from both files
    merged_df = pd.merge(df1_merge, df2_merge, on=[id_col_name, 'Date'], how='outer')

    # Calculate daily changes
    merged_df = merged_df.sort_values(by=[id_col_name, 'Date'])
    merged_df['Change_Orig'] = merged_df.groupby(id_col_name)['Value_Orig'].diff()
    merged_df['Change_New'] = merged_df.groupby(id_col_name)['Value_New'].diff()

    # Store static data separately - get the latest version per security
    static_data = merged_df.groupby(id_col_name)[common_static_cols].last().reset_index()

    log.info(f"Successfully merged spread duration data. Shape: {merged_df.shape}")
    return merged_df, static_data, common_static_cols, id_col_name # Return the identified ID column name


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

        # Get active filters (ensuring keys are correct)
        active_filters = {k.replace('filter_', ''): v
                          for k, v in request.args.items()
                          if k.startswith('filter_') and v}
        log.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}")

        # --- Load and Prepare Data ---
        # Capture the actual ID column name returned by the load function
        merged_data, static_data, static_cols, actual_id_col = load_comparison_data()

        if actual_id_col is None:
            log.error("Failed to get ID column name during spread duration data loading.")
            return "Error loading spread duration comparison data: Could not determine ID column.", 500

        # Pass the actual ID column name to the stats calculation function
        summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

        if summary_stats.empty and not merged_data.empty:
             log.warning("Spread Duration calculation resulted in empty stats DataFrame, but merged data was present.")
        elif summary_stats.empty:
             log.info("No spread duration summary statistics could be calculated.")
             # Render with message if empty even before filtering
             return render_template('spread_duration_comparison_page.html', # Updated template
                                    table_data=[],
                                    columns_to_display=[],
                                    id_column_name=actual_id_col,
                                    filter_options={},
                                    active_filters={},
                                    current_sort_by=sort_by,
                                    current_sort_order=sort_order,
                                    pagination=None,
                                    message="No spread duration comparison data available.")

        # --- Collect Filter Options (From Full Dataset Before Filtering) ---
        filter_options = {}
        potential_filter_cols = static_cols # Add other potential categorical columns from summary_stats if needed
        for col in potential_filter_cols:
            if col in summary_stats.columns:
                unique_vals = summary_stats[col].dropna().unique().tolist()
                # Basic type check and sort if possible - Improved Robust Sorting Key
                try:
                    # Attempt numerical sort first if applicable (handles ints/floats mixed with strings gracefully)
                    sorted_vals = sorted(unique_vals, key=lambda x: (isinstance(x, (int, float)), x))
                except TypeError:
                     # Fallback to string sort if mixed types cause issues
                    sorted_vals = sorted(unique_vals, key=str)
                filter_options[col] = sorted_vals

        log.info(f"Filter options generated: {list(filter_options.keys())}")

        # --- Apply Filters ---
        filtered_data = summary_stats.copy()
        if active_filters:
            log.info(f"Applying filters: {active_filters}")
            for col, value in active_filters.items():
                if col in filtered_data.columns:
                    # Handle potential type mismatches (e.g., filter value is string, column is number)
                    try:
                         # Convert filter value to column type if possible
                        col_type = filtered_data[col].dtype
                        if pd.api.types.is_numeric_dtype(col_type):
                            value = pd.to_numeric(value, errors='ignore') # Coerce to numeric if possible
                        elif pd.api.types.is_datetime64_any_dtype(col_type):
                             value = pd.to_datetime(value, errors='ignore') # Coerce to datetime if possible

                        # Apply filter (handle NaN explicitly if needed)
                        if pd.isna(value):
                            filtered_data = filtered_data[filtered_data[col].isna()]
                        else:
                            filtered_data = filtered_data[filtered_data[col] == value]

                    except Exception as e:
                        log.warning(f"Could not apply filter for column '{col}' with value '{value}'. Error: {e}. Skipping filter.")
                else:
                    log.warning(f"Filter column '{col}' not found in data. Skipping filter.")
            log.info(f"Data shape after filtering: {filtered_data.shape}")
        else:
            log.info("No active filters.")

        # --- Apply Sorting ---
        if sort_by in filtered_data.columns:
            log.info(f"Sorting by '{sort_by}' ({'Ascending' if ascending else 'Descending'})")
            # Handle NaNs during sorting - place them appropriately
            na_position = 'last' # Default, can be 'first' if preferred
            try:
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
            except Exception as e:
                log.error(f"Error during sorting by '{sort_by}': {e}. Falling back to default sort.")
                sort_by = 'Change_Correlation' # Revert to default if error
                ascending = False
                filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
        else:
            log.warning(f"Sort column '{sort_by}' not found. Using default 'Change_Correlation'.")
            sort_by = 'Change_Correlation' # Ensure default is used if provided key is invalid
            ascending = False
            filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position='last')

        # --- Pagination ---
        total_items = len(filtered_data)
        total_pages = math.ceil(total_items / PER_PAGE_COMPARISON)
        start_index = (page - 1) * PER_PAGE_COMPARISON
        end_index = start_index + PER_PAGE_COMPARISON
        paginated_data = filtered_data.iloc[start_index:end_index]
        log.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Displaying items {start_index}-{end_index-1}")

        # --- Prepare for Template ---
        # Define columns to display (ensure actual_id_col is first)
        # Base columns - adjust as needed for spread duration comparison specifics
        base_cols = [
            'Level_Correlation', 'Change_Correlation',
            'Mean_Abs_Diff', 'Max_Abs_Diff',
            'NaN_Count_Orig', 'NaN_Count_New', 'Total_Points',
            'Same_Date_Range',
            'Start_Date_Orig', 'End_Date_Orig',
            'Start_Date_New', 'End_Date_New',
            'Max_Orig', 'Min_Orig', 'Max_New', 'Min_New'
            # Add/remove columns as needed
        ]
        # Ensure static columns come after the ID and before the calculated stats
        columns_to_display = [actual_id_col] + \
                             [col for col in static_cols if col != actual_id_col and col in paginated_data.columns] + \
                             [col for col in base_cols if col in paginated_data.columns]


        # Convert DataFrame to list of dictionaries for easy template iteration
        table_data = paginated_data.to_dict(orient='records')

        # Format specific columns (like correlations, dates)
        for row in table_data:
            for col in ['Level_Correlation', 'Change_Correlation']:
                 if col in row and pd.notna(row[col]):
                    row[col] = f"{row[col]:.4f}" # Format correlation
            for col in ['Start_Date_Orig', 'End_Date_Orig', 'Start_Date_New', 'End_Date_New']:
                 if col in row and pd.notna(row[col]):
                    try:
                        # Ensure it's a Timestamp before formatting
                        if isinstance(row[col], pd.Timestamp):
                             row[col] = row[col].strftime('%Y-%m-%d')
                        # If already string, assume correct format or skip
                    except AttributeError:
                        log.debug(f"Could not format date column '{col}' with value '{row[col]}'. Type: {type(row[col])}")
                        pass # Keep original value if formatting fails

        # Create pagination object
        pagination = {
            'page': page,
            'per_page': PER_PAGE_COMPARISON,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
        }
        log.info("--- Successfully Prepared Data for Spread Duration Comparison Template ---")

        return render_template('spread_duration_comparison_page.html', # Updated template
                               table_data=table_data,
                               columns_to_display=columns_to_display,
                               id_column_name=actual_id_col, # Pass the ID column name
                               filter_options=filter_options,
                               active_filters=active_filters,
                               current_sort_by=sort_by,
                               current_sort_order=sort_order,
                               pagination=pagination,
                               message=None) # No message if data is present

    except FileNotFoundError as e:
        log.error(f"Spread duration comparison file not found: {e}")
        return f"Error: Required spread duration comparison file not found ({e.filename}). Check the Data folder.", 404
    except Exception as e:
        log.exception("An unexpected error occurred in the spread duration comparison summary view.") # Log full traceback
        return f"An internal error occurred: {e}", 500


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
        merged_df, _, common_static_cols, id_col_name = load_comparison_data(file1='sec_Spread duration.csv', file2='sec_Spread durationSP.csv')

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