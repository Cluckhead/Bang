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
    from config import DATA_FOLDER, COLOR_PALETTE
except ImportError:
    # Handle potential import errors if the structure is different
    logging.error("Could not import required modules from parent directory.")
    # Add fallback imports or path adjustments if necessary
    # Example: sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from ..security_processing import load_and_process_security_data, calculate_security_latest_metrics
    from ..utils import parse_fund_list
    from ..config import DATA_FOLDER, COLOR_PALETTE


comparison_bp = Blueprint('comparison_bp', __name__,
                        template_folder='../templates',
                        static_folder='../static')

# Configure logging
log = logging.getLogger(__name__)

PER_PAGE_COMPARISON = 50 # Items per page for comparison summary

# --- Data Loading and Processing ---

def load_comparison_data(file1='sec_spread.csv', file2='sec_spreadSP.csv'):
    """Loads, processes, and merges data from two security spread files.

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None) on error.
    """
    log.info(f"Loading comparison data: {file1} and {file2}")
    # Pass only the filename, as load_and_process_security_data prepends DATA_FOLDER internally
    df1, static_cols1 = load_and_process_security_data(file1)
    df2, static_cols2 = load_and_process_security_data(file2)

    if df1.empty or df2.empty:
        log.warning(f"One or both dataframes are empty. File1 empty: {df1.empty}, File2 empty: {df2.empty}")
        return pd.DataFrame(), pd.DataFrame(), [], None # Return None for id_col_name

    # Identify common static columns (excluding the ID column used for merging)
    common_static_cols = list(set(static_cols1) & set(static_cols2))
    
    # Get the actual ID column name (should be the same for both, use df1)
    if df1.index.nlevels == 2:
        id_col_name = df1.index.names[1] # Assuming 'Security ID'/Name is the second level
        log.info(f"Identified ID column from index: {id_col_name}")
    else:
        log.error("Processed DataFrame df1 does not have the expected 2-level MultiIndex.")
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

    log.info(f"Successfully merged data. Shape: {merged_df.shape}")
    return merged_df, static_data, common_static_cols, id_col_name # Return the identified ID column name


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
            log.error("Failed to get ID column name during data loading.")
            return "Error loading comparison data: Could not determine ID column.", 500

        # Pass the actual ID column name to the stats calculation function
        summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

        if summary_stats.empty and not merged_data.empty:
             log.warning("Calculation resulted in empty stats DataFrame, but merged data was present.")
        elif summary_stats.empty:
             log.info("No summary statistics could be calculated.")
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
                                    message="No comparison data available.")

        # --- Collect Filter Options (From Full Dataset Before Filtering) --- 
        filter_options = {}
        potential_filter_cols = static_cols # Add other potential categorical columns from summary_stats if needed
        for col in potential_filter_cols:
            if col in summary_stats.columns:
                unique_vals = summary_stats[col].dropna().unique().tolist()
                # Basic type check and sort if possible - Improved Robust Sorting Key
                try:
                    unique_vals = sorted(unique_vals, key=lambda x: \
                        (0, float(x)) if isinstance(x, bool) else \
                        (0, x) if isinstance(x, (int, float)) else \
                        (0, float(x)) if isinstance(x, str) and x.replace('.', '', 1).lstrip('-').isdigit() else \
                        (1, x) if isinstance(x, str) else \
                        (2, x) # Fallback for other types
                    )
                except TypeError as e:
                    # If sorting fails (e.g., comparing incompatible types not caught by key),
                    # fall back to string sorting as a last resort.
                    log.warning(f"Type error during sorting unique values for column '{col}': {e}. Falling back to string sort.")
                    try:
                         unique_vals = sorted(str(x) for x in unique_vals)
                    except Exception as final_sort_err:
                        log.error(f"Final string sort failed for column '{col}': {final_sort_err}")
                        # Keep original unsorted list if all else fails
                if unique_vals:
                    filter_options[col] = unique_vals
        final_filter_options = dict(sorted(filter_options.items()))

        # --- Apply Filtering ---
        filtered_stats = summary_stats.copy()
        if active_filters:
            log.info(f"Applying filters: {active_filters}")
            for col, value in active_filters.items():
                if col in filtered_stats.columns and value:
                    # Handle potential type mismatches if filtering on numeric/boolean
                    try:
                        # Attempt direct comparison first
                        if filtered_stats[col].dtype == 'boolean':
                             filtered_stats = filtered_stats[filtered_stats[col] == (value.lower() == 'true')]
                        # Add more specific type handling if needed (e.g., numeric ranges)
                        else:
                             filtered_stats = filtered_stats[filtered_stats[col].astype(str).str.contains(value, case=False, na=False)] # Case-insensitive string contains
                    except Exception as e:
                        log.warning(f"Could not apply filter on column '{col}' with value '{value}'. Error: {e}")
                        # Optionally skip this filter or handle differently
            log.info(f"Stats shape after filtering: {filtered_stats.shape}")
        else:
             log.info("No active filters.")


        # --- Apply Sorting ---
        if sort_by in filtered_stats.columns:
            log.info(f"Sorting by '{sort_by}' {sort_order}")
            # Ensure numeric columns are sorted numerically, handle NaNs
            if pd.api.types.is_numeric_dtype(filtered_stats[sort_by]):
                 filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position='last')
            else:
                 # Attempt string sort for non-numeric, case-insensitive might be desired
                 filtered_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position='last', key=lambda col: col.astype(str).str.lower())

        else:
            log.warning(f"Sort column '{sort_by}' not found in filtered data. Skipping sort.")
            sort_by = actual_id_col # Fallback sort? Or remove sort indicator in template?
            sort_order = 'asc'
            ascending = True


        # --- Define Columns to Display ---
        # Identify fund columns (case-insensitive check) within static columns
        fund_cols = sorted([col for col in static_cols if 'fund' in col.lower() and col != actual_id_col])
        # Identify other static columns (excluding ID and fund columns)
        other_static_cols = sorted([col for col in static_cols if col != actual_id_col and col not in fund_cols])
        # Identify calculated columns to display (excluding helper/raw date/count columns)
        calculated_cols = sorted([col for col in summary_stats.columns
                                 if col not in static_cols and col != actual_id_col and
                                 col not in ['Start_Date_Orig', 'End_Date_Orig', 'Start_Date_New', 'End_Date_New',
                                              'NaN_Count_Orig', 'NaN_Count_New', 'Total_Points',
                                              'Overall_Start_Date', 'Overall_End_Date']]) # Exclude helper/raw date columns

        # Assemble the final list: ID, Other Static, Calculated, Fund Columns
        columns_to_display = [actual_id_col] + other_static_cols + calculated_cols + fund_cols
        log.debug(f"Columns to display: {columns_to_display}")


        # --- Pagination ---
        total_items = len(filtered_stats)
        if total_items == 0:
             log.info("No data remaining after filtering.")
             # Render with message if filtering resulted in empty set
             return render_template('comparison_page.html',
                                    table_data=[],
                                    columns_to_display=columns_to_display, # Still pass columns for header
                                    id_column_name=actual_id_col,
                                    filter_options=filter_options,
                                    active_filters=active_filters,
                                    current_sort_by=sort_by,
                                    current_sort_order=sort_order,
                                    pagination=None,
                                    message="No data matches the current filters.")

        # Ensure PER_PAGE_COMPARISON is positive
        safe_per_page = max(1, PER_PAGE_COMPARISON)
        total_pages = math.ceil(total_items / safe_per_page)
        total_pages = max(1, total_pages) # Ensure at least 1 page
        page = max(1, min(page, total_pages)) # Ensure page is within valid range
        start_index = (page - 1) * safe_per_page
        end_index = start_index + safe_per_page
        log.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Per page={safe_per_page}")
        
        # Calculate display page numbers
        page_window = 2
        start_page_display = max(1, page - page_window)
        end_page_display = min(total_pages, page + page_window)
        
        paginated_stats = filtered_stats.iloc[start_index:end_index]

        # --- Prepare Data for Template ---
        # Filter the DataFrame to only these columns AFTER pagination
        paginated_stats = paginated_stats[[col for col in columns_to_display if col in paginated_stats.columns]]

        table_data_list = paginated_stats.to_dict(orient='records')
        # Replace NaN with None for template rendering
        for row in table_data_list:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None

        # Create pagination context
        pagination_context = {
            'page': page,
            'per_page': safe_per_page,
            'total_pages': total_pages,
            'total_items': total_items,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1,
            'start_page_display': start_page_display, # Pass calculated start page
            'end_page_display': end_page_display,     # Pass calculated end page
            # Function to generate URLs for pagination links, preserving state
            'url_for_page': lambda p: url_for('comparison_bp.summary', 
                                              page=p, 
                                              sort_by=sort_by, 
                                              sort_order=sort_order, 
                                              **{f'filter_{k}': v for k, v in active_filters.items()})
        }

    except Exception as e:
        log.exception("Error occurred during comparison summary processing.") # Log full traceback
        return render_template('comparison_page.html', 
                               message=f"An unexpected error occurred: {e}", 
                               table_data=[], 
                               pagination=None,
                               filter_options={}, 
                               active_filters={}, 
                               columns_to_display=[],
                               id_column_name='Security') # Provide a default ID name

    # --- Render Template ---
    return render_template('comparison_page.html',
                           table_data=table_data_list,
                           columns_to_display=columns_to_display,
                           id_column_name=actual_id_col,
                           filter_options=filter_options,
                           active_filters=active_filters,
                           current_sort_by=sort_by,
                           current_sort_order=sort_order,
                           pagination=pagination_context, # Pass pagination object
                           message=None)


@comparison_bp.route('/comparison/details/<path:security_id>')
def comparison_details(security_id):
    """Displays side-by-side historical charts for a specific security."""
    log.info(f"Fetching comparison details for security: {security_id}")
    try:
        # Reload or filter the merged data for the specific security
        merged_data, static_data, _, actual_id_col = load_comparison_data()

        if actual_id_col is None:
            log.error("Failed to get ID column name during data loading for details page.")
            return "Error loading comparison data: Could not determine ID column.", 500

        # Filter using the actual ID column name
        security_data = merged_data[merged_data[actual_id_col] == security_id].copy()

        if security_data.empty:
            return "Security ID not found", 404

        # Get the static data for this specific security
        sec_static_data = static_data[static_data[actual_id_col] == security_id]

        # Recalculate detailed stats for this security, passing the correct ID column
        stats_df = calculate_comparison_stats(security_data.copy(), sec_static_data, id_col=actual_id_col)
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
        security_name_display = security_stats.get('Security Name', security_id) if actual_id_col == 'Security Name' else security_id
        
        # If 'Security Name' is not the ID, try to get it from stats
        if actual_id_col != 'Security Name' and 'Security Name' in security_stats:
             security_name_display = security_stats.get('Security Name', security_id)

        return render_template('comparison_details_page.html',
                               security_id=security_id,
                               security_name=security_name_display,
                               chart_data=chart_data, # Pass as JSONifiable dict
                               stats=security_stats, # Pass comparison stats
                               id_column_name=actual_id_col) # Pass actual ID col name


    except Exception as e:
        log.exception(f"Error generating comparison details page for {security_id}.")
        return f"An error occurred: {e}", 500 