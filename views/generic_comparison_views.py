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
import os # Added for path joining
from flask import Blueprint, render_template, request, current_app, url_for, flash, abort
from urllib.parse import unquote, urlencode # For handling security IDs with special chars
from .comparison_helpers import (
    load_generic_comparison_data,
    calculate_generic_comparison_stats,
    get_holdings_for_security,
    load_fund_codes_from_csv
)

# Import shared utilities and processing functions
try:
    from utils import load_weights_and_held_status, parse_fund_list # Import parse_fund_list for fund filter logic
    from security_processing import load_and_process_security_data # Keep using this standard loader
    from config import COMPARISON_CONFIG, COLOR_PALETTE # Import the new config
except ImportError as e:
    logging.error(f"Error importing modules in generic_comparison_views: {e}")
    # Fallback imports if running standalone or structure differs (adjust path as needed)
    from ..utils import load_weights_and_held_status, parse_fund_list
    from ..security_processing import load_and_process_security_data
    from ..config import COMPARISON_CONFIG, COLOR_PALETTE

# Define the Blueprint
generic_comparison_bp = Blueprint('generic_comparison_bp', __name__,
                                  template_folder='../templates',
                                  static_folder='../static')

PER_PAGE_COMPARISON = 50 # Items per page for summary view

# --- Refactored Helper Functions ---

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


# --- Helper function to process holdings data ---
def get_holdings_for_security(security_id, chart_dates, data_folder):
    """
    Loads w_secs.csv and determines which funds held the given security on the specified dates.

    Args:
        security_id (str): The ISIN or identifier of the security.
        chart_dates (list): A list of date strings ('YYYY-MM-DD') from the chart.
        data_folder (str): Path to the Data folder.

    Returns:
        dict: A dictionary where keys are fund codes and values are lists of booleans
              indicating hold status for each corresponding chart date.
              Returns an empty dict if the security or file is not found, or on error.
        list: The list of date strings used for the columns, confirms alignment.
        str: An error message, if any.
    """
    log = current_app.logger
    holdings_file = os.path.join(data_folder, 'w_secs.csv')
    holdings_data = {}
    error_message = None

    try:
        if not os.path.exists(holdings_file):
            log.warning(f"Holdings file not found: {holdings_file}")
            return holdings_data, chart_dates, "Holdings file (w_secs.csv) not found."

        # Load the holdings file - assuming ISIN is the first column
        # We need to be careful with date parsing here, as headers might be strings
        df_holdings = pd.read_csv(holdings_file, low_memory=False)
        log.info(f"Loaded w_secs.csv with columns: {df_holdings.columns.tolist()}")

        # Identify potential date columns (heuristic: check format like DD/MM/YYYY or YYYY-MM-DD)
        # and the ID column (assuming 'ISIN') and 'Funds' column
        id_col_holding = 'ISIN' # Assuming this is the standard ID in w_secs
        fund_col_holding = 'Funds'

        if id_col_holding not in df_holdings.columns or fund_col_holding not in df_holdings.columns:
            log.error(f"Missing required columns '{id_col_holding}' or '{fund_col_holding}' in {holdings_file}")
            return holdings_data, chart_dates, f"Missing required columns in {holdings_file}."
            
        # Normalize security ID for comparison (e.g., convert to string)
        df_holdings[id_col_holding] = df_holdings[id_col_holding].astype(str)
        security_id_str = str(security_id)

        # Filter for the specific security
        sec_holdings = df_holdings[df_holdings[id_col_holding] == security_id_str].copy()

        if sec_holdings.empty:
            log.info(f"Security ID '{security_id_str}' not found in {holdings_file}")
            # Not necessarily an error, just means no holdings data
            return holdings_data, chart_dates, None 

        log.info(f"Found {len(sec_holdings)} rows for security '{security_id_str}' in w_secs.csv.")

        # Prepare chart dates (convert to expected format if needed, assuming 'YYYY-MM-DD')
        # The chart_dates from chart_data['labels'] should already be 'YYYY-MM-DD' strings
        holdings_cols = df_holdings.columns.tolist()
        
        # Try to match chart dates with columns in w_secs.csv, allowing for format variations
        w_secs_date_map = {} # Map chart_date ('YYYY-MM-DD') to actual column name in w_secs
        
        # Attempt to parse w_secs columns as dates
        parsed_cols = {}
        for col in holdings_cols:
            try:
                # Try common formats, prioritise DD/MM/YYYY then YYYY-MM-DD
                parsed_date = pd.to_datetime(col, format='%d/%m/%Y', errors='raise')
                parsed_cols[parsed_date.strftime('%Y-%m-%d')] = col
                continue # Move to next column if parsed
            except (ValueError, TypeError):
                 pass # Ignore if parsing fails with first format
            try:
                parsed_date = pd.to_datetime(col, format='%Y-%m-%d', errors='raise')
                parsed_cols[parsed_date.strftime('%Y-%m-%d')] = col
                continue
            except (ValueError, TypeError):
                 pass # Ignore other non-date-like columns silently
                 
        log.debug(f"Parsed w_secs columns: {parsed_cols}")

        matched_dates_in_w_secs = []
        unmatched_chart_dates = []

        for chart_date_str in chart_dates: # Should be 'YYYY-MM-DD'
            if chart_date_str in parsed_cols:
                 w_secs_col_name = parsed_cols[chart_date_str]
                 w_secs_date_map[chart_date_str] = w_secs_col_name
                 matched_dates_in_w_secs.append(w_secs_col_name)
            else:
                 # Check if the raw chart_date_str matches any w_secs column directly (less robust)
                 if chart_date_str in holdings_cols:
                     w_secs_date_map[chart_date_str] = chart_date_str
                     matched_dates_in_w_secs.append(chart_date_str)
                     log.warning(f"Direct string match used for date: {chart_date_str}. Consider standardizing date formats.")
                 else:
                    unmatched_chart_dates.append(chart_date_str)
                    w_secs_date_map[chart_date_str] = None # Mark as not found

        if unmatched_chart_dates:
             log.warning(f"Could not find matching columns in w_secs.csv for chart dates: {unmatched_chart_dates}. These dates will show as 'Not Held'.")
             # We don't set error_message here, just log a warning and proceed

        if not matched_dates_in_w_secs:
             log.warning(f"No chart dates ({chart_dates}) found as columns in w_secs.csv. Cannot determine holdings.")
             return holdings_data, chart_dates, "No chart dates found in holdings file columns."


        # Process holdings for each fund found for this security
        for fund_code, fund_group in sec_holdings.groupby(fund_col_holding):
            if fund_group.empty:
                continue
            
            # There might be multiple rows per fund if the data isn't clean,
            # Aggregate or take the first row? Taking first for simplicity.
            fund_row = fund_group.iloc[0]
            
            held_list = []
            for chart_date_str in chart_dates:
                w_secs_col = w_secs_date_map.get(chart_date_str)
                is_held = False # Default to not held
                if w_secs_col and w_secs_col in fund_row.index:
                    # Check if the value for that date is not null/NaN/empty string AND greater than 0
                    value = fund_row[w_secs_col]
                    # Try converting to numeric, coercing errors to NaN
                    numeric_value = pd.to_numeric(value, errors='coerce')
                    # Check if it's a valid number and greater than 0
                    if pd.notna(numeric_value) and numeric_value > 0:
                        is_held = True
                # else: date not found in w_secs columns or fund_row, or value is NaN/zero/empty, remains False
                
                held_list.append(is_held)
            
            holdings_data[fund_code] = held_list

        log.info(f"Processed holdings for funds: {list(holdings_data.keys())} for security {security_id_str}")

    except pd.errors.EmptyDataError:
        log.warning(f"Holdings file {holdings_file} is empty.")
        error_message = "Holdings file is empty."
    except KeyError as e:
         log.error(f"KeyError processing holdings file {holdings_file} for security {security_id_str}: {e}", exc_info=True)
         error_message = f"Missing expected column in holdings file: {e}"
    except Exception as e:
        log.error(f"Error processing holdings for security {security_id_str}: {e}", exc_info=True)
        error_message = f"An unexpected error occurred processing holdings: {e}"

    return holdings_data, chart_dates, error_message


def load_fund_codes_from_csv(data_folder: str) -> list:
    """
    Loads the list of fund codes from FundList.csv in the given data folder.
    Returns a sorted list of fund codes (strings). Returns empty list on error.
    """
    fund_list_path = os.path.join(data_folder, 'FundList.csv')
    if not os.path.exists(fund_list_path):
        current_app.logger.warning(f"FundList.csv not found at {fund_list_path}")
        return []
    try:
        df = pd.read_csv(fund_list_path)
        if 'Fund Code' in df.columns:
            fund_codes = sorted(df['Fund Code'].dropna().astype(str).unique().tolist())
            return fund_codes
        else:
            current_app.logger.warning(f"'Fund Code' column not found in FundList.csv at {fund_list_path}")
            return []
    except Exception as e:
        current_app.logger.error(f"Error loading FundList.csv: {e}")
        return []


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
            # Special handling for 'Funds' column: use FundList.csv for dropdown, not unique values in data
            if col == 'Funds':
                fund_codes = load_fund_codes_from_csv(data_folder)
                filter_options[col] = fund_codes
            else:
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
                # Special handling for Funds filter: match if selected fund is in the parsed list
                if col == 'Funds':
                    # Use parse_fund_list to turn '[IG01,IG02]' into a list, then check if value is in list
                    filtered_data = filtered_data[filtered_data['Funds'].apply(lambda x: value in parse_fund_list(x) if pd.notna(x) else False)].copy()
                else:
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
    """Displays the detail page for a specific security comparison."""
    log = current_app.logger
    
    # The security_id parameter from the route IS the URL-encoded string
    security_id_encoded = security_id 
    try:
        # URL decode the security ID - crucial for IDs with slashes, etc.
        decoded_security_id = unquote(security_id_encoded)
        log.info(f"--- Starting Generic Comparison Detail Request: Type = {comparison_type}, Decoded Security ID = '{decoded_security_id}' (Encoded: '{security_id_encoded}') ---")
    except Exception as e:
        log.error(f"Error decoding security ID '{security_id_encoded}': {e}")
        # If decoding fails, we probably can't proceed meaningfully.
        # Abort with a 400 Bad Request error.
        abort(400, description="Invalid security ID format in URL.")

    # --- Validate comparison_type and get config --- 
    # This part now runs only if decoding succeeded
    comp_config = COMPARISON_CONFIG.get(comparison_type)
    if not comp_config:
        log.error(f"Invalid comparison_type requested: {comparison_type}")
        abort(404, description=f"Comparison type '{comparison_type}' not found.")

    display_name = comp_config['display_name']
    file1 = comp_config['file1']
    file2 = comp_config['file2']
    value_label = comp_config.get('value_label', 'Value') # Use specific label or default
    log.info(f"Config loaded for '{comparison_type}': file1='{file1}', file2='{file2}', value_label='{value_label}'")

    # --- Load Data ---
    data_folder = current_app.config['DATA_FOLDER']
    # We need the merged data and the actual ID column name here
    merged_data, static_data, _, actual_id_col = load_generic_comparison_data(data_folder, file1, file2)

    if actual_id_col is None or merged_data.empty:
        flash(f"Could not load comparison data for type '{comparison_type}'.", "warning")
        log.warning(f"Failed to load comparison data for {comparison_type}, rendering potentially empty detail page.")
        # Render template with message even if data loading failed partially
        return render_template('comparison_details_base.html',
                               comparison_type=comparison_type,
                               display_name=display_name,
                               value_label=value_label,
                               security_id=decoded_security_id,
                               security_name=decoded_security_id, # Default if no static data
                               chart_data=None,
                               stats=None,
                               id_column_name='Security', # Default
                               message=f"Could not load data for comparison '{display_name}'.",
                               holdings_data=None, # Added
                               chart_dates=None    # Added
                               )

    # --- Filter for the Specific Security ---
    log.debug(f"Filtering merged data for security ID '{decoded_security_id}' using column '{actual_id_col}'")
    
    # Robust filtering: convert both to string for comparison
    try:
        merged_data[actual_id_col] = merged_data[actual_id_col].astype(str)
        security_data = merged_data[merged_data[actual_id_col] == str(decoded_security_id)].copy() # Use decoded ID for filtering
    except KeyError:
         log.error(f"ID column '{actual_id_col}' not found in merged_data during filtering.")
         security_data = pd.DataFrame() # Empty DF if column missing
    except Exception as e:
         log.error(f"Error filtering merged_data for security ID '{decoded_security_id}': {e}")
         security_data = pd.DataFrame()


    if security_data.empty:
        log.warning(f"No data found for Security ID '{decoded_security_id}' (using column '{actual_id_col}') in comparison type '{comparison_type}'.")
        return render_template('comparison_details_base.html',
                               comparison_type=comparison_type,
                               display_name=display_name,
                               value_label=value_label,
                               security_id=decoded_security_id,
                               security_name=decoded_security_id, # Attempt to get name below
                               chart_data=None,
                               stats=None,
                               id_column_name=actual_id_col,
                               message=f"No data found for {actual_id_col} '{decoded_security_id}' in {display_name} comparison.",
                               holdings_data=None, # Added
                               chart_dates=None    # Added
                               )

    # --- Calculate Stats for this Security Only ---
    # Use the generic stats function, but just for this security's data
    # Need to get the static data row for *this* security
    security_static_row = pd.DataFrame()
    if not static_data.empty and actual_id_col in static_data.columns:
         try:
             # Convert both to string for reliable matching
             static_data[actual_id_col] = static_data[actual_id_col].astype(str)
             security_static_row = static_data[static_data[actual_id_col] == str(decoded_security_id)]
         except Exception as e:
             log.warning(f"Error getting static data row for '{decoded_security_id}': {e}")

    # Run stats calculation - expects merged_df, static_data, id_col
    # Pass the filtered security_data and its corresponding static row
    stats_df = calculate_generic_comparison_stats(security_data, security_static_row, actual_id_col)

    stats = {}
    security_name = decoded_security_id # Default name is the ID
    if not stats_df.empty:
        stats = stats_df.iloc[0].to_dict()
        # Convert Timestamps to strings for JSON serialization if needed, but stats uses them directly? Check template.
        # Let's keep Timestamps for now, template handles formatting.
        
        # Attempt to get a more descriptive name if available (e.g., 'Security Name')
        potential_name_col = 'Security Name' 
        if potential_name_col in stats and pd.notna(stats[potential_name_col]):
            security_name = stats[potential_name_col]
            log.info(f"Found security name: '{security_name}' for ID '{decoded_security_id}'")
        else:
             log.info(f"Using ID '{decoded_security_id}' as name (Column '{potential_name_col}' not found or is null in stats).")
    else:
        log.warning(f"Could not calculate statistics for security {decoded_security_id}.")


    # --- Prepare Chart Data ---
    chart_data = None
    chart_dates = [] # Initialize chart_dates
    if not security_data.empty:
        # Ensure Date column is datetime and sort
        try:
            security_data['Date'] = pd.to_datetime(security_data['Date'])
            security_data = security_data.sort_values(by='Date')
            chart_dates = security_data['Date'].dt.strftime('%Y-%m-%d').tolist() # Get dates for holdings table
        except Exception as e:
            log.error(f"Error processing dates for chart data for security {decoded_security_id}: {e}")
            flash("Error processing dates for chart.", "danger")
        else:
             # Handle potential NaN values for JSON serialization in chart
             value_orig_cleaned = security_data['Value_Orig'].where(pd.notna(security_data['Value_Orig']), None).tolist()
             value_new_cleaned = security_data['Value_New'].where(pd.notna(security_data['Value_New']), None).tolist()

             chart_data = {
                 'labels': chart_dates, # Use the string-formatted dates
                 'datasets': [
                    {
                        'label': f'Original {value_label}',
                        'data': value_orig_cleaned,
                        'borderColor': COLOR_PALETTE[0],
                        'backgroundColor': COLOR_PALETTE[0] + '80', # Add transparency
                        'fill': False,
                        'tension': 0.1
                    },
                    {
                        'label': f'New {value_label}',
                        'data': value_new_cleaned,
                        'borderColor': COLOR_PALETTE[1],
                        'backgroundColor': COLOR_PALETTE[1] + '80',
                        'fill': False,
                        'tension': 0.1
                    }
                ]
            }
             log.info(f"Prepared chart data for {decoded_security_id} with {len(chart_dates)} dates.")
    else:
        log.warning(f"Security data is empty for {decoded_security_id}, cannot generate chart.")

    # --- Get Holdings Data ---
    holdings_data = {}
    holdings_error = None
    if chart_dates: # Only try to get holdings if we have dates from the chart
        # Pass the *decoded* security ID to the helper function
        holdings_data, _, holdings_error = get_holdings_for_security(decoded_security_id, chart_dates, data_folder)
        if holdings_error:
             flash(f"Note: Could not display fund holdings. {holdings_error}", "warning")
             log.warning(f"Holdings Error for {decoded_security_id}: {holdings_error}")
        if not holdings_data and not holdings_error:
            log.info(f"No holdings information found in w_secs.csv for security {decoded_security_id}.")
            # Optionally flash a message? Or just show an empty table? Showing empty table is fine.
            # flash(f"No fund holdings information found for {decoded_security_id}.", "info")
    else:
         log.warning(f"Skipping holdings check for {decoded_security_id} because chart dates are missing.")


    # --- Render Template ---
    return render_template('comparison_details_base.html',
                           comparison_type=comparison_type,
                           display_name=display_name,
                           value_label=value_label,
                           security_id=decoded_security_id, # Pass decoded ID
                           security_name=security_name, # Pass potentially better name
                           chart_data=chart_data,
                           stats=stats if stats else None, # Pass dict or None
                           id_column_name=actual_id_col,
                           message=None, # No error message if we got this far, warnings flashed
                           holdings_data=holdings_data, # Pass holdings dict
                           chart_dates=chart_dates      # Pass list of dates
                           ) 