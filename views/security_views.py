"""
Blueprint for security-related routes (e.g., summary page and individual details).
"""
from flask import Blueprint, render_template, jsonify, send_from_directory, url_for, current_app
import os
import pandas as pd
import numpy as np
import traceback
from urllib.parse import unquote
from datetime import datetime
from flask import request # Import request
import math
import json

# Import necessary functions/constants from other modules
from config import COLOR_PALETTE # Keep palette
from security_processing import load_and_process_security_data, calculate_security_latest_metrics
# Import the exclusion loading function
from views.exclusion_views import load_exclusions # Only import load_exclusions

# Define the blueprint
security_bp = Blueprint('security', __name__, url_prefix='/security')

PER_PAGE = 50 # Define how many items per page

def get_active_exclusions(data_folder_path: str):
    """Loads exclusions and returns a set of SecurityIDs that are currently active."""
    # Pass the data folder path to the load_exclusions function
    exclusions = load_exclusions(data_folder_path)
    active_exclusions = set()
    today = datetime.now().date()

    for ex in exclusions:
        try:
            add_date = ex['AddDate'].date() if pd.notna(ex['AddDate']) else None
            end_date = ex['EndDate'].date() if pd.notna(ex['EndDate']) else None
            security_id = str(ex['SecurityID']) # Ensure it's string for comparison

            if add_date and add_date <= today:
                if end_date is None or end_date >= today:
                    active_exclusions.add(security_id)
        except Exception as e:
            print(f"Error processing exclusion record {ex}: {e}") # Use logging in production

    print(f"Found {len(active_exclusions)} active exclusions: {active_exclusions}")
    return active_exclusions

@security_bp.route('/summary')
def securities_page():
    """Renders a page summarizing potential issues in security-level data, with server-side pagination, filtering, and sorting."""
    print("\n--- Starting Security Data Processing (Paginated) ---")

    # Retrieve the configured absolute data folder path
    data_folder = current_app.config['DATA_FOLDER']
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # --- Get Request Parameters ---
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search_term', '', type=str).strip()
    sort_by = request.args.get('sort_by', None, type=str)
    # Default sort: Abs Change Z-Score Descending
    sort_order = request.args.get('sort_order', 'desc', type=str).lower() 
    # Ensure sort_order is either 'asc' or 'desc'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    # Collect active filters from request args (e.g., ?filter_Country=USA&filter_Sector=Tech)
    active_filters = {
        key.replace('filter_', ''): value 
        for key, value in request.args.items() 
        if key.startswith('filter_') and value # Ensure value is not empty
    }
    print(f"Request Params: Page={page}, Search='{search_term}', SortBy='{sort_by}', SortOrder='{sort_order}', Filters={active_filters}")

    # --- Load Base Data ---
    spread_filename = "sec_Spread.csv"
    # Construct absolute path
    data_filepath = os.path.join(data_folder, spread_filename)
    filter_options = {} # To store all possible options for filter dropdowns
    
    if not os.path.exists(data_filepath):
        print(f"Error: The required file '{spread_filename}' not found.")
        return render_template('securities_page.html', message=f"Error: Required data file '{spread_filename}' not found.", securities_data=[], pagination=None)

    try:
        print(f"Loading and processing file: {spread_filename}")
        # Pass the absolute data folder path
        df_long, static_cols = load_and_process_security_data(spread_filename, data_folder)

        if df_long is None or df_long.empty:
            print(f"Skipping {spread_filename} due to load/process errors or empty data.")
            return render_template('securities_page.html', message=f"Error loading or processing '{spread_filename}'.", securities_data=[], pagination=None)
        
        print("Calculating latest metrics...")
        combined_metrics_df = calculate_security_latest_metrics(df_long, static_cols)

        if combined_metrics_df.empty:
            print(f"No metrics calculated for {spread_filename}.")
            return render_template('securities_page.html', message=f"Could not calculate metrics from '{spread_filename}'.", securities_data=[], pagination=None)
        
        # Define ID column name
        id_col_name = 'ISIN' # <<< Use ISIN as the identifier

        # Check if the chosen ID column exists in the index or columns
        if id_col_name in combined_metrics_df.index.names:
            combined_metrics_df.index.name = id_col_name # Ensure index name is set if using index
            combined_metrics_df.reset_index(inplace=True)
        elif id_col_name in combined_metrics_df.columns:
            pass # ID is already a column
        else:
            # Fallback or error if ISIN isn't found
            old_id_col = combined_metrics_df.index.name or 'Security ID'
            print(f"Warning: ID column '{id_col_name}' not found. Falling back to '{old_id_col}'.")
            if old_id_col in combined_metrics_df.index.names:
                 combined_metrics_df.index.name = old_id_col
                 combined_metrics_df.reset_index(inplace=True)
                 id_col_name = old_id_col # Use the fallback name
            elif old_id_col in combined_metrics_df.columns:
                 id_col_name = old_id_col
            else:
                 print(f"Error: Cannot find a usable ID column ('{id_col_name}' or fallback '{old_id_col}') in {spread_filename}.")
                 return render_template('securities_page.html', message=f"Error: Cannot identify securities in {spread_filename}.", securities_data=[], pagination=None)

        # Store the original unfiltered dataframe's columns 
        original_columns = combined_metrics_df.columns.tolist()
        # combined_metrics_df.reset_index(inplace=True) # Reset index to make ID a regular column - ALREADY DONE OR ID IS A COLUMN

        # --- Collect Filter Options (from the full dataset BEFORE filtering) ---
        print("Collecting filter options...")
        # Ensure ID column is not treated as a filterable static column
        current_static_in_df = [col for col in static_cols if col in combined_metrics_df.columns and col != id_col_name]
        for col in current_static_in_df:
            unique_vals = combined_metrics_df[col].unique().tolist()
            unique_vals = [item.item() if isinstance(item, np.generic) else item for item in unique_vals]
            unique_vals = sorted([val for val in unique_vals if pd.notna(val) and val != '']) # Remove NaN/empty and sort
            if unique_vals: # Only add if there are valid options
                 filter_options[col] = unique_vals
        
        # Sort filter options dictionary by key for consistent display order
        final_filter_options = dict(sorted(filter_options.items()))


        # --- Apply Filtering Steps Sequentially ---
        print("Applying filters...")
        # 1. Search Term Filter (on ID column - now ISIN)
        if search_term:
            combined_metrics_df = combined_metrics_df[combined_metrics_df[id_col_name].astype(str).str.contains(search_term, case=False, na=False)]
            print(f"Applied search term '{search_term}'. Rows remaining: {len(combined_metrics_df)}")

        # 2. Active Exclusions Filter (should still work if exclusions use SecurityID/Name, adapt if needed)
        try:
            # Pass the absolute data folder path to get active exclusions
            active_exclusion_ids = get_active_exclusions(data_folder)
            # Assuming exclusions use Security Name/ID for now. If they use ISIN, this is correct.
            # If they use Security Name, we need to filter on that column instead.
            exclusion_col_to_check = id_col_name # Assumes exclusions use ISIN
            # If exclusions.csv uses Security Name, use this instead:
            # exclusion_col_to_check = 'Security Name' if 'Security Name' in combined_metrics_df.columns else id_col_name 
            
            if active_exclusion_ids:
                 combined_metrics_df = combined_metrics_df[~combined_metrics_df[exclusion_col_to_check].astype(str).isin(active_exclusion_ids)]
                 print(f"Applied {len(active_exclusion_ids)} exclusions based on '{exclusion_col_to_check}'. Rows remaining: {len(combined_metrics_df)}")
        except Exception as e:
            print(f"Warning: Error loading or applying exclusions: {e}")

        # 3. Dynamic Filters (from request args)
        if active_filters:
            for col, value in active_filters.items():
                if col in combined_metrics_df.columns:
                    # Ensure consistent type for comparison, handle NaNs
                    combined_metrics_df = combined_metrics_df[combined_metrics_df[col].astype(str) == str(value)]
                    print(f"Applied filter '{col}={value}'. Rows remaining: {len(combined_metrics_df)}")
                else:
                     print(f"Warning: Filter column '{col}' not found in DataFrame.")

        # --- Handle Empty DataFrame After Filtering ---
        if combined_metrics_df.empty:
            print("No data matches the specified filters.")
            message = "No securities found matching the current criteria."
            if search_term:
                message += f" Search term: '{search_term}'."
            if active_filters:
                 message += f" Active filters: {active_filters}."
            return render_template('securities_page.html',
                                   message=message,
                                   securities_data=[],
                                   filter_options=final_filter_options,
                                   column_order=[],
                                   id_col_name=id_col_name,
                                   search_term=search_term,
                                   active_filters=active_filters,
                                   pagination=None,
                                   current_sort_by=sort_by,
                                   current_sort_order=sort_order)

        # --- Apply Sorting ---
        print(f"Applying sort: By='{sort_by}', Order='{sort_order}'")
        
        # Default sort column if not provided or invalid
        effective_sort_by = sort_by
        is_default_sort = False
        if sort_by not in combined_metrics_df.columns:
             # Default to sorting by absolute Z-score if 'sort_by' is invalid or not provided
             if 'Change Z-Score' in combined_metrics_df.columns:
                 print(f"'{sort_by}' not valid or not provided. Defaulting sort to 'Abs Change Z-Score' {sort_order}")
                 # Calculate Abs Z-Score temporarily for sorting
                 combined_metrics_df['_abs_z_score_'] = combined_metrics_df['Change Z-Score'].fillna(0).abs()
                 effective_sort_by = '_abs_z_score_'
                 # Default Z-score sort is always descending unless explicitly requested otherwise for Z-score itself
                 if sort_by != 'Change Z-Score': 
                      sort_order = 'desc' 
                 is_default_sort = True
             else:
                  print("Warning: Cannot apply default sort, 'Change Z-Score' missing.")
                  effective_sort_by = id_col_name # Fallback sort
                  sort_order = 'asc'
        
        ascending_order = (sort_order == 'asc')
        
        try:
            # Use na_position='last' to handle NaNs consistently
            combined_metrics_df.sort_values(by=effective_sort_by, ascending=ascending_order, inplace=True, na_position='last', key=lambda col: col.astype(str).str.lower() if col.dtype == 'object' else col)
            print(f"Sorted by '{effective_sort_by}', {sort_order}.")
        except Exception as e:
             print(f"Error during sorting by {effective_sort_by}: {e}. Falling back to sorting by ID.")
             combined_metrics_df.sort_values(by=id_col_name, ascending=True, inplace=True, na_position='last')
             sort_by = id_col_name # Update sort_by to reflect fallback
             sort_order = 'asc'

        # Remove temporary sort column if added
        if is_default_sort and '_abs_z_score_' in combined_metrics_df.columns:
            combined_metrics_df.drop(columns=['_abs_z_score_'], inplace=True)
            # Set sort_by for template correctly if default was used
            sort_by = 'Change Z-Score' # Reflect the conceptual sort column


        # --- Pagination ---
        total_items = len(combined_metrics_df)
        # Ensure PER_PAGE is positive to avoid division by zero or negative pages
        safe_per_page = max(1, PER_PAGE)
        total_pages = math.ceil(total_items / safe_per_page)
        total_pages = max(1, total_pages) # Ensure at least 1 page, even if total_items is 0
        page = max(1, min(page, total_pages)) # Ensure page is within valid range [1, total_pages]
        start_index = (page - 1) * safe_per_page
        end_index = start_index + safe_per_page
        
        print(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Per page={safe_per_page}")
        
        # Calculate page numbers to display in pagination controls (e.g., show 2 pages before and after current)
        page_window = 2 # Number of pages to show before/after current page
        start_page_display = max(1, page - page_window)
        end_page_display = min(total_pages, page + page_window)
        
        paginated_df = combined_metrics_df.iloc[start_index:end_index]

        # --- Prepare Data for Template ---
        securities_data_list = paginated_df.round(3).to_dict(orient='records')
        # Replace NaN with None for JSON compatibility / template rendering
        for row in securities_data_list:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None

        # Define column order (ID first, then Static, then Metrics)
        # Ensure ISIN (id_col_name) is not in ordered_static_cols
        ordered_static_cols = sorted([col for col in static_cols if col in paginated_df.columns and col != id_col_name])
        metric_cols_ordered = ['Latest Value', 'Change', 'Change Z-Score', 'Mean', 'Max', 'Min']
        # Ensure only existing columns are included and ID col is first
        final_col_order = [id_col_name] + \
                          [col for col in ordered_static_cols if col in paginated_df.columns] + \
                          [col for col in metric_cols_ordered if col in paginated_df.columns]
        
        # Ensure all original columns are considered if they aren't static or metric
        # Make sure not to add id_col_name again
        other_cols = [col for col in paginated_df.columns if col not in final_col_order]
        final_col_order.extend(other_cols) # Add any remaining columns

        print(f"Final column order for display: {final_col_order}")


        # Create pagination context for the template
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
            'url_for_page': lambda p: url_for('security.securities_page', 
                                              page=p, 
                                              search_term=search_term, 
                                              sort_by=sort_by, 
                                              sort_order=sort_order, 
                                              **{f'filter_{k}': v for k, v in active_filters.items()}) 
        }


    except Exception as e:
        print(f"!!! Unexpected error during security page processing: {e}")
        traceback.print_exc()
        return render_template('securities_page.html', 
                               message=f"An unexpected error occurred: {e}", 
                               securities_data=[], 
                               pagination=None,
                               filter_options=final_filter_options if 'final_filter_options' in locals() else {},
                               active_filters=active_filters)

    # --- Render Template ---
    return render_template('securities_page.html',
                           securities_data=securities_data_list,
                           filter_options=final_filter_options,
                           column_order=final_col_order,
                           id_col_name=id_col_name,
                           search_term=search_term,
                           active_filters=active_filters, # Pass active filters for form state
                           pagination=pagination_context, # Pass pagination object
                           current_sort_by=sort_by,
                           current_sort_order=sort_order,
                           message=None) # Clear any previous error message if successful

# --- Helper Function to Replace NaN --- 
def replace_nan_with_none(obj):
    """Recursively replaces np.nan with None in a nested structure (dicts, lists)."""
    if isinstance(obj, dict):
        return {k: replace_nan_with_none(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_nan_with_none(elem) for elem in obj]
    # Check specifically for pandas/numpy NaN values
    elif pd.isna(obj) and isinstance(obj, (float, np.floating)):
        return None
    else:
        return obj

@security_bp.route('/security/details/<metric_name>/<path:security_id>')
def security_details(metric_name, security_id):
    """Renders a details page for a specific security, showing historical charts."""
    
    # --- Decode the security ID ---
    decoded_security_id = unquote(security_id)
    print(f"--- Requesting Security Details: Metric='{metric_name}', Decoded ID='{decoded_security_id}' ---")

    data_folder = current_app.config['DATA_FOLDER']
    chart_data = {'labels': [], 'primary_datasets': [], 'duration_dataset': None, 'sp_duration_dataset': None, 'spread_duration_dataset': None, 'sp_spread_duration_dataset': None, 'spread_dataset': None, 'sp_spread_dataset': None }
    latest_date_str = "N/A"
    static_info_dict = {}
    all_dates = set() # Collect all dates across datasets

    # Helper function to load, process, and filter security data
    def load_filter_and_extract(filename, security_id_to_filter, id_column_name='Security Name'): # <-- Change default ID column
        filepath = os.path.join(data_folder, filename)
        print(f"Loading file: {filename}")
        if not os.path.exists(filepath):
            print(f"Warning: File not found - {filename}")
            return None, None, set()
        
        try:
            df_long, static_cols = load_and_process_security_data(filename, data_folder)
            if df_long is None or df_long.empty:
                print(f"Warning: No data loaded or processed for {filename}")
                return None, None, set()

            # --- Use the specified ID column for filtering ---
            if id_column_name in df_long.columns:
                # Filter using the decoded security ID and the correct column
                filtered_df = df_long[df_long[id_column_name] == security_id_to_filter].copy()
                if filtered_df.empty:
                   print(f"Warning: No data found for {id_column_name}='{security_id_to_filter}' in {filename} (column filter)")
                   # Fallback: Attempt filtering by index if column filter failed
                   if df_long.index.name == id_column_name or id_column_name in df_long.index.names:
                        print(f"--> Attempting index filter for '{id_column_name}'...")
                        try:
                           # Use .loc which can handle single/multi-index
                           filtered_df = df_long.loc[[security_id_to_filter]].copy()
                           if filtered_df.empty:
                               print(f"--> Also no data found in index for '{security_id_to_filter}'")
                               return None, static_cols, set()
                           else:
                               print(f"--> Found data in index for '{security_id_to_filter}'")
                        except KeyError:
                             print(f"--> KeyError when looking for '{security_id_to_filter}' in index.")
                             return None, static_cols, set()
                        except Exception as idx_e:
                            print(f"--> Unexpected error during index filtering: {idx_e}")
                            return None, static_cols, set()
                   else:
                        print(f"--> Column filter failed, and ID '{id_column_name}' not found in index names: {df_long.index.names}")
                        return None, static_cols, set()
                # If we got here, filtered_df might be populated (either from column or index filter)
                
            elif df_long.index.name == id_column_name or id_column_name in df_long.index.names:
                 # ID column not in columns, but IS in index - filter directly by index
                 print(f"Filtering {filename} directly by index '{id_column_name}' for '{security_id_to_filter}'")
                 try:
                     filtered_df = df_long.loc[[security_id_to_filter]].copy()
                     if filtered_df.empty:
                         print(f"--> No data found in index for '{security_id_to_filter}'")
                         return None, static_cols, set()
                 except KeyError:
                     print(f"--> KeyError when looking for '{security_id_to_filter}' in index.")
                     return None, static_cols, set()
                 except Exception as idx_e:
                    print(f"--> Unexpected error during direct index filtering: {idx_e}")
                    return None, static_cols, set()
            else:
                 # Handle case where the expected ID column isn't in columns OR index
                 print(f"Error: Required filter column/index '{id_column_name}' not found in the loaded data from {filename}. Columns: {df_long.columns.tolist()}, Index: {df_long.index.names}")
                 return None, static_cols, set()
            
            # --- Check if filtering resulted in data ---
            if filtered_df is None or filtered_df.empty:
                print(f"No data found for '{security_id_to_filter}' after all filter attempts in {filename}.")
                return None, static_cols, set()

            # --- Ensure 'Date' is a column --- 
            # Crucial step: If 'Date' ended up in the index, reset it.
            if 'Date' not in filtered_df.columns and 'Date' in filtered_df.index.names:
                print(f"'Date' found in index, resetting index for {filename}...")
                filtered_df.reset_index(inplace=True)
            
            # --- Validate 'Date' column presence and convert --- 
            if 'Date' not in filtered_df.columns:
                 print(f"Error: 'Date' column STILL missing after filtering and index reset attempt for {filename}. Columns: {filtered_df.columns}")
                 return None, static_cols, set()
                     
            try:
                filtered_df['Date'] = pd.to_datetime(filtered_df['Date'])
                filtered_df.sort_values('Date', inplace=True)
            except Exception as date_e:
                print(f"Error converting 'Date' column to datetime or sorting for {filename}: {date_e}")
                traceback.print_exc()
                return None, static_cols, set()

            # Extract dates from this specific security's data
            current_dates = set(filtered_df['Date'])
            
            print(f"Successfully filtered {filename} for {id_column_name}='{security_id_to_filter}'. Found {len(filtered_df)} rows.")
            return filtered_df, static_cols, current_dates

        except Exception as e:
            print(f"Error loading/processing/filtering file {filename} for ID {security_id_to_filter}: {e}")
            traceback.print_exc() # Print full traceback for debugging
            return None, None, set()
            
    # --- Load and Process Base Metric Data ---
    base_metric_filename = f"sec_{metric_name}.csv"
    # Use the helper function with the DECODED ID and 'Security Name'
    df_metric_long, static_cols_metric, metric_dates = load_filter_and_extract(
        base_metric_filename, decoded_security_id, 'Security Name' 
    )
    if df_metric_long is not None and not df_metric_long.empty:
        all_dates.update(metric_dates)
        # Extract static info from the first loaded file (assume it's consistent)
        if static_cols_metric:
             latest_metric_row = df_metric_long.iloc[-1]
             static_info_dict = {col: latest_metric_row[col] for col in static_cols_metric if col in latest_metric_row and pd.notna(latest_metric_row[col])}
             print(f"Extracted static info: {static_info_dict}")
        else:
             print("No static columns identified in base metric file.")
             
    # --- Load and Process Price Data ---
    df_price_long, _, price_dates = load_filter_and_extract(
        "sec_Price.csv", decoded_security_id, 'Security Name'
    )
    if df_price_long is not None: all_dates.update(price_dates)
        
    # --- Load and Process Duration Data (Primary and SP) ---
    df_duration_long, _, duration_dates = load_filter_and_extract(
        "sec_Duration.csv", decoded_security_id, 'Security Name' 
    )
    if df_duration_long is not None: all_dates.update(duration_dates)

    df_sp_duration_long, _, sp_duration_dates = load_filter_and_extract(
        "sec_DurationSP.csv", decoded_security_id, 'Security Name' 
    )
    if df_sp_duration_long is not None: all_dates.update(sp_duration_dates)
        
    # --- Load and Process Spread Duration Data (Primary and SP) ---
    df_spread_dur_long, _, spread_dur_dates = load_filter_and_extract(
        "sec_Spread duration.csv", decoded_security_id, 'Security Name' 
    )
    if df_spread_dur_long is not None: all_dates.update(spread_dur_dates)

    df_sp_spread_dur_long, _, sp_spread_dur_dates = load_filter_and_extract(
        "sec_Spread durationSP.csv", decoded_security_id, 'Security Name' 
    )
    if df_sp_spread_dur_long is not None: all_dates.update(sp_spread_dur_dates)

    # --- Load and Process Spread Data (Primary and SP) ---
    df_spread_long, _, spread_dates = load_filter_and_extract(
        "sec_Spread.csv", decoded_security_id, 'Security Name'
    )
    if df_spread_long is not None: all_dates.update(spread_dates)
    
    df_sp_spread_long, _, sp_spread_dates = load_filter_and_extract(
        "sec_SpreadSP.csv", decoded_security_id, 'Security Name'
    )
    if df_sp_spread_long is not None: all_dates.update(sp_spread_dates)

    # --- Prepare Chart Data ---
    if not all_dates:
        print("No dates found across any datasets. Cannot generate chart labels.")
        # Render template with a message indicating no data
        return render_template('security_details_page.html',
                               security_id=decoded_security_id, # Show decoded ID
                               metric_name=metric_name,
                               chart_data_json='{}', # Empty data
                               latest_date="N/A",
                               static_info=static_info_dict, # Pass potentially empty dict
                               error_message=f"No historical data found for security '{decoded_security_id}'.")

    # Create sorted list of unique dates across all datasets
    sorted_dates = sorted(list(all_dates))
    chart_data['labels'] = [d.strftime('%Y-%m-%d') for d in sorted_dates]
    latest_date_str = chart_data['labels'][-1] if chart_data['labels'] else "N/A"
    
    # Create a reference DataFrame with all dates for merging
    date_ref_df = pd.DataFrame({'Date': sorted_dates})

    # Helper function to prepare dataset for Chart.js
    def prepare_dataset(df, value_col, label, color, y_axis_id='y'):
        if df is None or df.empty:
            print(f"Cannot prepare dataset for '{label}': DataFrame is None or empty.")
             # Return structure with null data matching the length of labels
            return {
                'label': label,
                'data': [None] * len(chart_data['labels']), # Use None for missing points
                'borderColor': color,
                'backgroundColor': color + '80', # Optional: add transparency
                'fill': False,
                'tension': 0.1,
                'pointRadius': 2,
                'pointHoverRadius': 5,
                'yAxisID': y_axis_id,
                'spanGaps': True # Let Chart.js connect lines over nulls
            }
            
        # Ensure value column is numeric, coercing errors
        df[value_col] = pd.to_numeric(df[value_col], errors='coerce')

        # Merge with the full date range, using pd.NA for missing numeric values
        merged_df = pd.merge(date_ref_df, df[['Date', value_col]], on='Date', how='left')
        
        # Replace pandas NA/NaN with None for JSON compatibility
        # data_values = merged_df[value_col].replace({pd.NA: None, np.nan: None}).tolist()
        # Replace only NaN with None, keep numeric types where possible
        # Ensure the column is float first to handle potential integers mixed with NaN
        data_values = merged_df[value_col].astype(float).replace({np.nan: None}).tolist()


        return {
            'label': label,
            'data': data_values,
            'borderColor': color,
            'backgroundColor': color + '80',
            'fill': False,
            'tension': 0.1,
            'pointRadius': 2,
            'pointHoverRadius': 5,
            'yAxisID': y_axis_id,
            'spanGaps': True
        }

    # Primary Chart Datasets (Metric + Price)
    if df_metric_long is not None:
        chart_data['primary_datasets'].append(
            prepare_dataset(df_metric_long, 'Value', metric_name, COLOR_PALETTE[0], 'y')
        )
    else: # Add placeholder if metric data failed to load
        chart_data['primary_datasets'].append(
            prepare_dataset(None, 'Value', metric_name, COLOR_PALETTE[0], 'y')
        )
        
    if df_price_long is not None:
        chart_data['primary_datasets'].append(
            prepare_dataset(df_price_long, 'Value', 'Price', COLOR_PALETTE[1], 'y1') # Use secondary axis
        )
    else: # Add placeholder if price data failed to load
         chart_data['primary_datasets'].append(
            prepare_dataset(None, 'Value', 'Price', COLOR_PALETTE[1], 'y1')
        )

    # Duration Chart Datasets
    chart_data['duration_dataset'] = prepare_dataset(df_duration_long, 'Value', 'Duration', COLOR_PALETTE[2])
    chart_data['sp_duration_dataset'] = prepare_dataset(df_sp_duration_long, 'Value', 'SP Duration', COLOR_PALETTE[3])

    # Spread Duration Chart Datasets
    chart_data['spread_duration_dataset'] = prepare_dataset(df_spread_dur_long, 'Value', 'Spread Duration', COLOR_PALETTE[4])
    chart_data['sp_spread_duration_dataset'] = prepare_dataset(df_sp_spread_dur_long, 'Value', 'SP Spread Duration', COLOR_PALETTE[5])

    # Spread Chart Datasets
    chart_data['spread_dataset'] = prepare_dataset(df_spread_long, 'Value', 'Spread', COLOR_PALETTE[6])
    chart_data['sp_spread_dataset'] = prepare_dataset(df_sp_spread_long, 'Value', 'SP Spread', COLOR_PALETTE[7])

    # Convert the entire chart_data dictionary to JSON safely
    chart_data_json = json.dumps(chart_data, default=replace_nan_with_none, indent=4) # Use helper for NaN->null


    print(f"Rendering security details page for {decoded_security_id}")
    # Pass the decoded ID to the template
    return render_template('security_details_page.html',
                           security_id=decoded_security_id, 
                           metric_name=metric_name,
                           chart_data_json=chart_data_json,
                           latest_date=latest_date_str,
                           static_info=static_info_dict)


@security_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(security_bp.root_path, '..', 'static'), filename) 