# views/generic_comparison_views.py
# This module defines a generic Flask Blueprint for comparing two security datasets (e.g., spread, duration).
# It supports multiple comparison types defined in config.py.
# Features include:
# - Dynamic loading of configured comparison files.
# - Calculation of comparison statistics.
# - Merging with held status from weights data.
# - Server-side filtering, sorting, and pagination for the summary view.
# - Detail view showing overlayed time-series charts and statistics for a single security.

import pandas as pd
import math
import logging
from flask import Blueprint, render_template, request, current_app, url_for, flash, abort
from urllib.parse import unquote, urlencode # For handling security IDs with special chars

# Import shared utilities and processing functions
try:
    from utils import load_weights_and_held_status # Moved here
    from security_processing import load_and_process_security_data # Keep using this standard loader
    from config import COMPARISON_CONFIG, COLOR_PALETTE # Import the new config
except ImportError as e:
    logging.error(f"Error importing modules in generic_comparison_views: {e}")
    # Fallback imports if running standalone or structure differs (adjust path as needed)
    from ..utils import load_weights_and_held_status
    from ..security_processing import load_and_process_security_data
    from ..config import COMPARISON_CONFIG, COLOR_PALETTE

# Define the Blueprint
generic_comparison_bp = Blueprint('generic_comparison_bp', __name__,
                                  template_folder='../templates',
                                  static_folder='../static')

PER_PAGE_COMPARISON = 50 # Items per page for summary view

# --- Refactored Helper Functions ---

def load_generic_comparison_data(data_folder_path: str, file1: str, file2: str):
    """
    Loads, processes, and merges data from two specified security data files.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        file1 (str): Filename for the first dataset (e.g., 'original').
        file2 (str): Filename for the second dataset (e.g., 'new' or 'comparison').

    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None) on error or if files are empty.
               Note: held_status is loaded separately in the view function.
    """
    log = current_app.logger
    log.info(f"--- Entering load_generic_comparison_data: {file1}, {file2} ---")

    if not data_folder_path:
        log.error("No data_folder_path provided to load_generic_comparison_data.")
        return pd.DataFrame(), pd.DataFrame(), [], None

    try:
        # Load data using the standard security data processor
        df1, static_cols1 = load_and_process_security_data(file1, data_folder_path)
        df2, static_cols2 = load_and_process_security_data(file2, data_folder_path)

        if df1.empty or df2.empty:
            log.warning(f"One or both dataframes are empty after loading. File1 ({file1}) empty: {df1.empty}, File2 ({file2}) empty: {df2.empty}")
            # Return empty structures, but don't raise an error here
            return pd.DataFrame(), pd.DataFrame(), [], None

        # --- Verify Index and Get Actual Names ---
        if df1.index.nlevels != 2 or df2.index.nlevels != 2:
            log.error(f"One or both dataframes ({file1}, {file2}) do not have the expected 2 index levels after loading.")
            return pd.DataFrame(), pd.DataFrame(), [], None

        # Get index names (assuming they are consistent between df1 and df2)
        date_level_name, id_level_name = df1.index.names
        log.info(f"Data index levels identified for {file1}/{file2}: Date='{date_level_name}', ID='{id_level_name}'")

        # --- Reset Index ---
        df1 = df1.reset_index()
        df2 = df2.reset_index()
        log.debug(f"Columns after reset for {file1}: {df1.columns.tolist()}")
        log.debug(f"Columns after reset for {file2}: {df2.columns.tolist()}")
        
        # --- Check Required Columns (Post-Reset) ---
        required_cols = [id_level_name, date_level_name, 'Value'] # 'Value' is the standard output name from loader
        missing_cols_df1 = [col for col in required_cols if col not in df1.columns]
        missing_cols_df2 = [col for col in required_cols if col not in df2.columns]

        if missing_cols_df1 or missing_cols_df2:
            log.error(f"Missing required columns after index reset. Df1 ({file1}) missing: {missing_cols_df1}, Df2 ({file2}) missing: {missing_cols_df2}")
            return pd.DataFrame(), pd.DataFrame(), [], None

        # --- Prepare for Merge ---
        common_static_cols = list(set(static_cols1) & set(static_cols2))
        # Remove the ID column name from static columns if present
        if id_level_name in common_static_cols:
            common_static_cols.remove(id_level_name)
        # Ensure 'Value' isn't treated as a static column
        if 'Value' in common_static_cols:
            common_static_cols.remove('Value')
        log.debug(f"Common static columns identified: {common_static_cols}")

        try:
            # Select necessary columns using the dynamically identified date and id names
            df1_merge = df1[[id_level_name, date_level_name, 'Value'] + common_static_cols].rename(columns={'Value': 'Value_Orig'})
            df2_merge = df2[[id_level_name, date_level_name, 'Value']].rename(columns={'Value': 'Value_New'})
        except KeyError as e:
            log.error(f"KeyError during merge preparation using names '{id_level_name}', '{date_level_name}': {e}. Df1 cols: {df1.columns.tolist()}, Df2 cols: {df2.columns.tolist()}")
            return pd.DataFrame(), pd.DataFrame(), [], None

        # --- Perform Merge and Calculate Changes ---
        merged_df = pd.merge(df1_merge, df2_merge, on=[id_level_name, date_level_name], how='outer')
        merged_df = merged_df.sort_values(by=[id_level_name, date_level_name])
        
        # Group by the dynamically identified ID column
        merged_df['Change_Orig'] = merged_df.groupby(id_level_name)['Value_Orig'].diff()
        merged_df['Change_New'] = merged_df.groupby(id_level_name)['Value_New'].diff()

        # --- Extract Static Data ---
        # Group by the identified ID column
        # Use .first() instead of .last() for static data? Check original loader's intent. Assuming .last() is okay for now.
        if common_static_cols:
             static_data = merged_df.groupby(id_level_name)[common_static_cols].last().reset_index()
        else:
             static_data = pd.DataFrame({id_level_name: merged_df[id_level_name].unique()}) # Just get unique IDs if no static cols
             log.info("No common static columns found between the two files.")


        log.info(f"Successfully merged data for {file1}/{file2}. Shape: {merged_df.shape}")
        # Return the dynamically identified ID column name
        log.info(f"--- Exiting load_generic_comparison_data. Merged shape: {merged_df.shape}. ID col: {id_level_name} ---")
        return merged_df, static_data, common_static_cols, id_level_name

    except FileNotFoundError as e:
        log.error(f"File not found during comparison data load: {e}")
        flash(f"Error: Required comparison file not found ({e.filename}). Please check the Data folder.", 'danger')
        # Reraise or return empty DFs? Returning empty for now.
        return pd.DataFrame(), pd.DataFrame(), [], None
    except Exception as e:
        log.error(f"Error loading or processing generic comparison data ({file1}, {file2}): {e}", exc_info=True)
        flash(f"An unexpected error occurred loading comparison data: {e}", 'danger')
        return pd.DataFrame(), pd.DataFrame(), [], None


# Calculate comparison stats function (seems largely reusable, maybe minor tweaks needed)
# Keep it similar to the original version found in comparison_views.py etc.
def calculate_generic_comparison_stats(merged_df, static_data, id_col):
    """
    Calculates comparison statistics for each security. 
    Generic version adaptable to different comparison types.

    Args:
        merged_df (pd.DataFrame): The merged dataframe with 'Value_Orig', 'Value_New', 'Date', and the id_col.
        static_data (pd.DataFrame): DataFrame with static info per security, indexed or containing id_col.
        id_col (str): The name of the column containing the Security ID/Name.

    Returns:
        pd.DataFrame: A DataFrame containing comparison statistics for each security.
    """
    log = current_app.logger
    if merged_df.empty:
        log.warning("calculate_generic_comparison_stats received an empty merged_df.")
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(f"Specified id_col '{id_col}' not found in merged_df columns for stats calculation: {merged_df.columns.tolist()}")
        return pd.DataFrame()

    log.info(f"Calculating generic comparison statistics using ID column: '{id_col}'...")
    stats_list = []

    for sec_id, group in merged_df.groupby(id_col):
        sec_stats = {id_col: sec_id}

        # Ensure Date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(group['Date']):
            group['Date'] = pd.to_datetime(group['Date'], errors='coerce')
            
        # Ensure Value columns are numeric
        group['Value_Orig'] = pd.to_numeric(group['Value_Orig'], errors='coerce')
        group['Value_New'] = pd.to_numeric(group['Value_New'], errors='coerce')


        # Filter for overall date range (where at least one value exists)
        group_valid_overall = group.dropna(subset=['Value_Orig', 'Value_New'], how='all')
        overall_min_date = group_valid_overall['Date'].min()
        overall_max_date = group_valid_overall['Date'].max()

        # Filter for valid comparison points (where BOTH values exist)
        valid_comparison = group.dropna(subset=['Value_Orig', 'Value_New'])

        # 1. Correlation of Levels
        if len(valid_comparison) >= 2:
            level_corr = valid_comparison['Value_Orig'].corr(valid_comparison['Value_New'])
            sec_stats['Level_Correlation'] = level_corr if pd.notna(level_corr) else None
        else:
            sec_stats['Level_Correlation'] = None

        # 2. Max / Min (using original group)
        sec_stats['Max_Orig'] = group['Value_Orig'].max()
        sec_stats['Min_Orig'] = group['Value_Orig'].min()
        sec_stats['Max_New'] = group['Value_New'].max()
        sec_stats['Min_New'] = group['Value_New'].min()

        # 3. Date Range Comparison
        min_date_orig_idx = group['Value_Orig'].first_valid_index()
        max_date_orig_idx = group['Value_Orig'].last_valid_index()
        min_date_new_idx = group['Value_New'].first_valid_index()
        max_date_new_idx = group['Value_New'].last_valid_index()

        sec_stats['Start_Date_Orig'] = group.loc[min_date_orig_idx, 'Date'] if min_date_orig_idx is not None else None
        sec_stats['End_Date_Orig'] = group.loc[max_date_orig_idx, 'Date'] if max_date_orig_idx is not None else None
        sec_stats['Start_Date_New'] = group.loc[min_date_new_idx, 'Date'] if min_date_new_idx is not None else None
        sec_stats['End_Date_New'] = group.loc[max_date_new_idx, 'Date'] if max_date_new_idx is not None else None

        same_start = (pd.notna(sec_stats['Start_Date_Orig']) and pd.notna(sec_stats['Start_Date_New']) and
                      pd.Timestamp(sec_stats['Start_Date_Orig']) == pd.Timestamp(sec_stats['Start_Date_New']))
        same_end = (pd.notna(sec_stats['End_Date_Orig']) and pd.notna(sec_stats['End_Date_New']) and
                    pd.Timestamp(sec_stats['End_Date_Orig']) == pd.Timestamp(sec_stats['End_Date_New']))
        sec_stats['Same_Date_Range'] = same_start and same_end

        # Add overall date range for info
        sec_stats['Overall_Start_Date'] = overall_min_date
        sec_stats['Overall_End_Date'] = overall_max_date

        # 4. Correlation of Daily Changes
        if len(valid_comparison) >= 1: # Need at least 1 point to calculate diff
            valid_comparison = valid_comparison.copy() # Avoid SettingWithCopyWarning
            valid_comparison['Change_Orig_Corr'] = valid_comparison['Value_Orig'].diff()
            valid_comparison['Change_New_Corr'] = valid_comparison['Value_New'].diff()
            
            # Drop NaNs created by the diff() itself and any pre-existing NaNs in changes
            valid_changes = valid_comparison.dropna(subset=['Change_Orig_Corr', 'Change_New_Corr'])

            if len(valid_changes) >= 2: # Need 2 pairs of *changes* for correlation
                change_corr = valid_changes['Change_Orig_Corr'].corr(valid_changes['Change_New_Corr'])
                sec_stats['Change_Correlation'] = change_corr if pd.notna(change_corr) else None
            else:
                sec_stats['Change_Correlation'] = None
                log.debug(f"Cannot calculate Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}.")
        else:
            sec_stats['Change_Correlation'] = None
            log.debug(f"Cannot calculate Change_Correlation for {sec_id}. Need >= 1 valid comparison point to calculate diffs, found {len(valid_comparison)}.")


        # 5. Difference Statistics (use valid_comparison df)
        if not valid_comparison.empty:
            valid_comparison['Abs_Diff'] = (valid_comparison['Value_Orig'] - valid_comparison['Value_New']).abs()
            sec_stats['Mean_Abs_Diff'] = valid_comparison['Abs_Diff'].mean()
            sec_stats['Max_Abs_Diff'] = valid_comparison['Abs_Diff'].max()
        else:
            sec_stats['Mean_Abs_Diff'] = None
            sec_stats['Max_Abs_Diff'] = None

        # Count NaNs (use original group)
        sec_stats['NaN_Count_Orig'] = group['Value_Orig'].isna().sum()
        sec_stats['NaN_Count_New'] = group['Value_New'].isna().sum()
        sec_stats['Total_Points'] = len(group)

        stats_list.append(sec_stats)

    if not stats_list:
        log.warning("No statistics were generated.")
        return pd.DataFrame()

    summary_df = pd.DataFrame(stats_list)

    # Merge static data back (ensure ID columns match)
    if not static_data.empty and id_col in static_data.columns and id_col in summary_df.columns:
         # Ensure consistent types before merge if possible
        try:
            if static_data[id_col].dtype != summary_df[id_col].dtype:
                log.warning(f"Attempting merge with different dtypes for ID column '{id_col}': Static ({static_data[id_col].dtype}), Summary ({summary_df[id_col].dtype}). Converting static to summary type.")
                static_data[id_col] = static_data[id_col].astype(summary_df[id_col].dtype)
        except Exception as e:
            log.warning(f"Could not ensure matching dtypes for merge key '{id_col}': {e}")

        summary_df = pd.merge(summary_df, static_data, on=id_col, how='left')
        log.info(f"Successfully merged static data back. Summary shape: {summary_df.shape}")
    elif not static_data.empty:
         log.warning(f"Could not merge static data. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns}).")

    log.info(f"--- Exiting calculate_generic_comparison_stats. Output shape: {summary_df.shape} ---")
    return summary_df


# --- Routes ---

@generic_comparison_bp.route('/<comparison_type>/summary')
def summary(comparison_type):
    """Displays the generic comparison summary page with filtering, sorting, and pagination."""
    log = current_app.logger
    log.info(f"--- Starting Generic Comparison Summary Request: Type = {comparison_type} ---")

    # --- Validate comparison_type and get config ---
    comp_config = COMPARISON_CONFIG.get(comparison_type)
    if not comp_config:
        log.error(f"Invalid comparison_type requested: {comparison_type}")
        abort(404, description=f"Comparison type '{comparison_type}' not found.")

    display_name = comp_config['display_name']
    file1 = comp_config['file1']
    file2 = comp_config['file2']
    log.info(f"Config loaded for '{comparison_type}': file1='{file1}', file2='{file2}'")

    # --- Get Request Parameters ---
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'Change_Correlation') # Consistent default? Or Max_Abs_Diff?
    sort_order = request.args.get('sort_order', 'desc').lower()
    ascending = sort_order == 'asc'
    show_sold = request.args.get('show_sold', 'false').lower() == 'true'
    active_filters = {k.replace('filter_', ''): v
                      for k, v in request.args.items()
                      if k.startswith('filter_') and v}
    log.info(f"Request Params: Page={page}, SortBy={sort_by}, Order={sort_order}, Filters={active_filters}, ShowSold={show_sold}")

    # --- Load Data ---
    data_folder = current_app.config['DATA_FOLDER']
    merged_data, static_data, static_cols, actual_id_col = load_generic_comparison_data(data_folder, file1, file2)

    if actual_id_col is None or merged_data.empty:
        log.warning(f"Failed to load or merge data for comparison type '{comparison_type}'. Rendering empty page.")
        # Flash message might have been set in load function
        return render_template('comparison_summary_base.html', # Use the new base template
                               comparison_type=comparison_type,
                               display_name=display_name,
                               table_data=[], columns_to_display=[], id_column_name='Security', # Default ID name if unknown
                               filter_options={}, active_filters={}, pagination=None,
                               current_sort_by=sort_by, current_sort_order=sort_order,
                               show_sold=show_sold,
                               message=f"Could not load data for {display_name} comparison.")

    log.info(f"Actual ID column identified for '{comparison_type}': '{actual_id_col}'")

    # --- Calculate Stats ---
    summary_stats = calculate_generic_comparison_stats(merged_data, static_data, id_col=actual_id_col)

    if summary_stats.empty:
        log.info(f"No summary statistics could be calculated for {comparison_type}.")
        return render_template('comparison_summary_base.html',
                               comparison_type=comparison_type, display_name=display_name,
                               table_data=[], columns_to_display=[], id_column_name=actual_id_col,
                               filter_options={}, active_filters={}, pagination=None,
                               current_sort_by=sort_by, current_sort_order=sort_order,
                               show_sold=show_sold,
                               message=f"No {display_name} comparison statistics available.")

    # --- Load and Merge Held Status ---
    # Assuming 'ISIN' is the standard ID in w_secs.csv, adjust if needed
    held_status = load_weights_and_held_status(data_folder, id_col_override='ISIN') # Use utility function
    if not held_status.empty and actual_id_col in summary_stats.columns:
         # Ensure merge keys match type (string conversion is safest)
        try:
            if summary_stats[actual_id_col].dtype != held_status.index.dtype:
                 log.info(f"Converting merge keys to string for held status merge (Summary: {summary_stats[actual_id_col].dtype}, Held: {held_status.index.dtype})")
                 summary_stats[actual_id_col] = summary_stats[actual_id_col].astype(str)
                 held_status.index = held_status.index.astype(str)
                 held_status.index.name = actual_id_col # Ensure index name matches column name after conversion
        except Exception as e:
             log.error(f"Failed to convert merge keys for held status merge: {e}")

        # Check names before merge
        log.info(f"Attempting held status merge: left_on='{actual_id_col}', right_index name='{held_status.index.name}'")

        # Perform merge
        summary_stats = pd.merge(summary_stats, held_status.rename('is_held'),
                                 left_on=actual_id_col, right_index=True, how='left')
        
        if 'is_held' in summary_stats.columns:
            summary_stats['is_held'] = summary_stats['is_held'].fillna(False)
            log.info("Merged held status and filled NaNs.")
        else:
            log.error("'is_held' column missing after merge attempt!")
            summary_stats['is_held'] = False # Add column as False if merge failed

    else:
        log.warning(f"Could not merge held status. Held status empty: {held_status.empty} or ID mismatch ('{actual_id_col}' in summary: {actual_id_col in summary_stats.columns})")
        summary_stats['is_held'] = False # Assume not held if data is missing

    # --- Apply Holding Filter ---
    original_count = len(summary_stats)
    if not show_sold:
        if 'is_held' in summary_stats.columns:
            summary_stats = summary_stats[summary_stats['is_held'] == True].copy() # Use .copy() after filtering
            log.info(f"Applied 'Show Held Only' filter. Kept {len(summary_stats)} of {original_count} securities.")
        else:
             log.warning("Cannot apply 'Show Held Only' filter because 'is_held' column is missing.")

    # --- Generate Filter Options (from data *after* holding filter) ---
    filter_options = {}
    if not summary_stats.empty:
         # Use static_cols identified earlier, ensure they exist in the filtered summary_stats
        potential_filter_cols = [col for col in static_cols if col in summary_stats.columns and col != actual_id_col]
        log.debug(f"Potential filter columns: {potential_filter_cols}")
        for col in potential_filter_cols:
            unique_vals = summary_stats[col].dropna().unique()
            try:
                # Attempt numeric sort first, then string sort
                sorted_vals = sorted(unique_vals, key=lambda x: (isinstance(x, (int, float)), str(x).lower()))
            except TypeError:
                sorted_vals = sorted(unique_vals, key=str) # Fallback to string sort
            if sorted_vals: # Only add if there are values
                filter_options[col] = sorted_vals
        filter_options = dict(sorted(filter_options.items())) # Sort filters alphabetically by column name
        log.info(f"Filter options generated: {list(filter_options.keys())}")
    else:
        log.info("Skipping filter option generation as data is empty after holding filter.")


    # --- Apply Static Column Filters ---
    filtered_data = summary_stats.copy() # Start with potentially filtered-by-holding data
    if active_filters:
        log.info(f"Applying static column filters: {active_filters}")
        for col, value in active_filters.items():
            if col in filtered_data.columns and value:
                 try:
                    # Ensure comparison is done as string for robustness
                     filtered_data = filtered_data[filtered_data[col].astype(str).str.fullmatch(str(value), case=False, na=False)].copy() # Use .copy()
                 except Exception as e:
                     log.warning(f"Could not apply filter for column '{col}' value '{value}'. Error: {e}")
            else:
                 log.warning(f"Filter column '{col}' not in data or value is empty. Skipping filter.")
        log.info(f"Data shape after static filtering: {filtered_data.shape}")


    # --- Handle No Data After Filters ---
    if filtered_data.empty:
         message = f"No {display_name} comparison data available matching the current filters."
         if not summary_stats.empty: # Means filters caused the empty result
             message = f"No {display_name} comparison data matches the selected filters."
             if not show_sold and 'is_held' in summary_stats.columns and not summary_stats[summary_stats['is_held']].empty:
                  message += " Try enabling 'Show Sold Securities'."
         elif original_count > 0 and not show_sold: # Holding filter caused empty result
             message = "No *currently held* securities found for this comparison. Try enabling 'Show Sold Securities'."
         else: # Original data was likely empty
             message = f"No data found for {display_name} comparison in files '{file1}' and '{file2}'."

         log.warning(message)
         return render_template('comparison_summary_base.html',
                                comparison_type=comparison_type, display_name=display_name,
                                table_data=[], columns_to_display=[], id_column_name=actual_id_col,
                                filter_options=filter_options, active_filters=active_filters, pagination=None,
                                current_sort_by=sort_by, current_sort_order=sort_order,
                                show_sold=show_sold,
                                message=message)

    # --- Apply Sorting ---
    if sort_by in filtered_data.columns:
        log.info(f"Sorting by '{sort_by}' ({'Ascending' if ascending else 'Descending'})")
        na_position = 'last'
        try:
            # Check if column is numeric, handling potential errors
            is_numeric = pd.api.types.is_numeric_dtype(filtered_data[sort_by])
            if is_numeric:
                 # Convert to numeric just before sorting to handle potential strings
                 filtered_data[sort_by] = pd.to_numeric(filtered_data[sort_by], errors='coerce')
                 filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
            else:
                # Sort non-numeric columns case-insensitively as strings
                 filtered_data = filtered_data.sort_values(by=sort_by, ascending=ascending, na_position=na_position,
                                                          key=lambda col: col.astype(str).str.lower())
        except Exception as e:
            log.error(f"Error during sorting by '{sort_by}': {e}. Applying default ID sort.")
            sort_by = actual_id_col
            ascending = True
            filtered_data = filtered_data.sort_values(by=actual_id_col, ascending=True, na_position='last') # Default sort
    else:
        log.warning(f"Sort column '{sort_by}' not found. Using default ID sort.")
        sort_by = actual_id_col
        ascending = True
        filtered_data = filtered_data.sort_values(by=actual_id_col, ascending=True, na_position='last')

    # --- Pagination ---
    total_items = len(filtered_data)
    safe_per_page = max(1, PER_PAGE_COMPARISON)
    total_pages = math.ceil(total_items / safe_per_page)
    page = max(1, min(page, total_pages)) # Ensure page is valid
    start_index = (page - 1) * safe_per_page
    end_index = start_index + safe_per_page
    paginated_data = filtered_data.iloc[start_index:end_index]
    log.info(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Displaying items {start_index}-{end_index-1}")

    page_window = 2
    start_page_display = max(1, page - page_window)
    end_page_display = min(total_pages, page + page_window)

    # --- Prepare for Template ---
    # Define core stats columns + dynamic static columns + ID column
    core_stats_cols = [
        'Level_Correlation', 'Change_Correlation',
        'Mean_Abs_Diff', 'Max_Abs_Diff',
        'Same_Date_Range', 'is_held' # Add is_held for potential display/styling
        # Maybe add 'Total_Points', 'NaN_Count_Orig', 'NaN_Count_New' if useful
    ]
    # Ensure columns exist in the final paginated data
    columns_to_display = [actual_id_col] + \
                         [col for col in static_cols if col != actual_id_col and col in paginated_data.columns] + \
                         [col for col in core_stats_cols if col in paginated_data.columns]

    table_data_dict = paginated_data.to_dict(orient='records')

    # Create pagination context object
    pagination_context = {
        'page': page, 'per_page': safe_per_page, 'total_items': total_items,
        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
        'prev_num': page - 1, 'next_num': page + 1,
        'start_page_display': start_page_display, 'end_page_display': end_page_display,
        # Function to generate URLs, preserving all current query parameters
        'url_for_page': lambda p: url_for('generic_comparison_bp.summary',
                                          comparison_type=comparison_type, page=p,
                                          # Convert request.args MultiDict to regular dict, excluding 'page'
                                          **{k: v for k, v in request.args.items() if k != 'page'})
    }

    log.info(f"--- Successfully Prepared Data for Generic Comparison Summary Template ({comparison_type}) ---")
    return render_template('comparison_summary_base.html', # Use the new base template
                           comparison_type=comparison_type,
                           display_name=display_name,
                           table_data=table_data_dict,
                           columns_to_display=columns_to_display,
                           id_column_name=actual_id_col, # Pass the actual ID column name
                           filter_options=filter_options,
                           active_filters=active_filters,
                           current_sort_by=sort_by,
                           current_sort_order=sort_order,
                           pagination=pagination_context,
                           show_sold=show_sold,
                           message=None) # No message if data is present


@generic_comparison_bp.route('/<comparison_type>/details/<path:security_id>')
def details(comparison_type, security_id):
    """Displays the generic comparison details page with charts and stats."""
    log = current_app.logger
    # Decode the security_id which might contain URL-encoded characters (like '/')
    decoded_security_id = unquote(security_id)
    log.info(f"--- Starting Generic Comparison Detail Request: Type = {comparison_type}, Security ID = {decoded_security_id} (Original: {security_id}) ---")

    # --- Validate comparison_type and get config ---
    comp_config = COMPARISON_CONFIG.get(comparison_type)
    if not comp_config:
        log.error(f"Invalid comparison_type requested for details: {comparison_type}")
        abort(404, description=f"Comparison type '{comparison_type}' not found.")

    display_name = comp_config['display_name']
    file1 = comp_config['file1']
    file2 = comp_config['file2']
    value_label = comp_config.get('value_label', display_name) # Get specific label or use display name

    # --- Load Data ---
    data_folder = current_app.config['DATA_FOLDER']
    # Load all data first, then filter. This ensures we use the same data as the summary page.
    merged_data, static_data, common_static_cols, actual_id_col = load_generic_comparison_data(data_folder, file1, file2)

    if actual_id_col is None or merged_data.empty:
        log.warning(f"Failed to load base data for comparison type '{comparison_type}' details view.")
        flash(f"Could not load base data for {display_name} comparison.", "warning")
        return render_template('comparison_details_base.html', # Use new base template
                               comparison_type=comparison_type, display_name=display_name,
                               security_id=decoded_security_id, security_name=decoded_security_id,
                               chart_data=None, stats=None, id_column_name='Security', # Default
                               message=f"Could not load data for {display_name} comparison.")

    log.info(f"Actual ID column for details '{comparison_type}': '{actual_id_col}'")

    # --- Filter for the specific security ---
    # Ensure type consistency for filtering if necessary (string comparison is safer)
    try:
        if merged_data[actual_id_col].dtype != type(decoded_security_id):
             log.info(f"Converting ID column '{actual_id_col}' to string for filtering.")
             security_data = merged_data[merged_data[actual_id_col].astype(str) == str(decoded_security_id)].copy()
        else:
             security_data = merged_data[merged_data[actual_id_col] == decoded_security_id].copy()
    except Exception as e:
        log.error(f"Error filtering security data for ID '{decoded_security_id}': {e}")
        security_data = pd.DataFrame() # Ensure empty DF if error

    if security_data.empty:
        log.warning(f"No data found for Security ID '{decoded_security_id}' in {comparison_type} comparison.")
        return render_template('comparison_details_base.html',
                               comparison_type=comparison_type, display_name=display_name,
                               security_id=decoded_security_id, security_name=decoded_security_id,
                               chart_data=None, stats=None, id_column_name=actual_id_col,
                               message=f"{display_name} data not found for Security ID: {decoded_security_id}")

    # --- Get Static Data for this Security ---
    # Filter the separate static_data DataFrame
    sec_static_data_filtered = static_data[static_data[actual_id_col] == decoded_security_id]
    sec_static_dict = sec_static_data_filtered.iloc[0].to_dict() if not sec_static_data_filtered.empty else {}

    # --- Recalculate Stats for Just This Security ---
    # Pass the single-security data to the stats function
    stats_df = calculate_generic_comparison_stats(security_data.copy(), sec_static_data_filtered, id_col=actual_id_col)
    security_stats = stats_df.iloc[0].where(pd.notnull(stats_df.iloc[0]), None).to_dict() if not stats_df.empty else {}
    
    # Combine calculated stats with static data for display
    # Calculated stats take precedence if names overlap
    display_stats = {**sec_static_dict, **security_stats} 

    # --- Prepare Chart Data ---
    security_data = security_data.sort_values(by='Date') # Ensure sorted by date
    security_data['Date_Str'] = security_data['Date'].dt.strftime('%Y-%m-%d')

    # Handle NaN -> None conversion for JSON compatibility
    data_orig = security_data['Value_Orig'].where(pd.notna(security_data['Value_Orig']), None).tolist()
    data_new = security_data['Value_New'].where(pd.notna(security_data['Value_New']), None).tolist()

    chart_data = {
        'labels': security_data['Date_Str'].tolist(),
        'datasets': [
            {
                'label': f'Original {value_label}', # Use specific value label
                'data': data_orig,
                'borderColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)],
                'tension': 0.1,
                'fill': False
            },
            {
                'label': f'New {value_label}', # Use specific value label
                'data': data_new,
                'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)],
                'tension': 0.1,
                'fill': False
            }
        ]
    }

    # Determine the display name (use 'Security Name' if available, else the ID)
    security_name_display = display_stats.get('Security Name', decoded_security_id)

    log.info(f"--- Successfully Prepared Data for Generic Comparison Details Template ({comparison_type}, {decoded_security_id}) ---")
    return render_template('comparison_details_base.html', # Use new base template
                           comparison_type=comparison_type,
                           display_name=display_name,
                           value_label=value_label, # Pass the value label for chart titles etc.
                           security_id=decoded_security_id,
                           security_name=security_name_display,
                           chart_data=chart_data, # Pass as JSONifiable dict
                           stats=display_stats, # Pass combined stats + static data
                           id_column_name=actual_id_col) 