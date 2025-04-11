"""
Blueprint for security-related routes (e.g., summary page and individual details).
"""
from flask import Blueprint, render_template, jsonify, send_from_directory, url_for
import os
import pandas as pd
import numpy as np
import traceback
from urllib.parse import unquote
from datetime import datetime
from flask import request # Import request
import math

# Import necessary functions/constants from other modules
from config import DATA_FOLDER, COLOR_PALETTE
from security_processing import load_and_process_security_data, calculate_security_latest_metrics
# Import the exclusion loading function
from views.exclusion_views import load_exclusions, get_data_path

# Define the blueprint
security_bp = Blueprint('security', __name__, url_prefix='/security')

PER_PAGE = 50 # Define how many items per page

def get_active_exclusions():
    """Loads exclusions and returns a set of SecurityIDs that are currently active."""
    exclusions = load_exclusions() # This returns a list of dicts
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
    data_filepath = os.path.join(DATA_FOLDER, spread_filename)
    filter_options = {} # To store all possible options for filter dropdowns
    
    if not os.path.exists(data_filepath):
        print(f"Error: The required file '{spread_filename}' not found.")
        return render_template('securities_page.html', message=f"Error: Required data file '{spread_filename}' not found.", securities_data=[], pagination=None)

    try:
        print(f"Loading and processing file: {spread_filename}")
        df_long, static_cols = load_and_process_security_data(spread_filename)

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
                 print(f"Error: Cannot find a usable ID column ('{id_col_name}' or fallback '{old_id_col}').")
                 return render_template('securities_page.html', message=f"Error: Cannot identify securities.", securities_data=[], pagination=None)

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
            # TODO: Verify if exclusions use ISIN or Security Name
            active_exclusion_ids = get_active_exclusions()
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
    """Renders the details page for a specific security, showing historical charts."""
    # Decode the security_id from the URL path, which might contain encoded characters
    decoded_security_id = unquote(security_id)
    print(f"\n--- Requesting Security Details: Metric='{metric_name}', Decoded ID='{decoded_security_id}' ---")

    # --- Define ID Column Name (consistent with summary page) --- 
    id_col = 'ISIN' 

    # --- Data Files to Load --- 
    # We need the base metric file, plus potentially Price and Duration
    base_metric_filename = f"sec_{metric_name}.csv"
    price_filename = "sec_Price.csv"
    duration_filename = "sec_Duration.csv"
    # Add new filenames
    spread_duration_filename = "sec_Spread duration.csv"
    spread_filename = "sec_Spread.csv"
    sp_spread_duration_filename = "sec_Spread durationSP.csv" 
    sp_duration_filename = "sec_DurationSP.csv" 
    sp_spread_filename = "sec_SpreadSP.csv"

    chart_data = {
        'labels': [],
        'primary_datasets': [], # For Base Metric + Price
        'duration_dataset': None,
        'sp_duration_dataset': None, # New
        'spread_duration_dataset': None, # New
        'sp_spread_duration_dataset': None, # New
        'spread_dataset': None, # New
        'sp_spread_dataset': None, # New
        'static_info': None,
        'latest_date': None,
        'metric_name': metric_name,
        'security_id': decoded_security_id
    }

    try:
        # --- Load Base Metric Data --- 
        print(f"Loading base metric file: {base_metric_filename}")
        # df_long now has columns: Date, ISIN, Security Name, other_static, Value
        df_long, static_cols = load_and_process_security_data(base_metric_filename)

        if df_long is None or df_long.empty:
            print(f"Error: Failed to load or process base metric data '{base_metric_filename}'.")
            return render_template('security_details_page.html', 
                                   security_id=decoded_security_id, 
                                   metric_name=metric_name, 
                                   chart_data_json='{}', 
                                   static_info=None,
                                   latest_date='N/A',
                                   message=f"Error loading base data for {metric_name}.")

        # --- Filter by Security ID (ISIN) --- 
        print(f"Filtering data for ISIN='{decoded_security_id}'")
        filter_col = 'ISIN' 
        
        if filter_col not in df_long.columns:
            print(f"Error: Required filter column '{filter_col}' not found in the loaded data from {base_metric_filename}. Columns: {df_long.columns.tolist()}")
            return render_template('security_details_page.html', security_id=decoded_security_id, metric_name=metric_name, 
                                    chart_data_json='{}', static_info=None, latest_date='N/A',
                                    message=f"Error: Identifier column '{filter_col}' not found in data.")

        # Filter the base dataframe
        security_data_filtered = df_long[df_long[filter_col].astype(str) == decoded_security_id].copy()

        if security_data_filtered.empty:
            print(f"No data found for {filter_col}='{decoded_security_id}' in {base_metric_filename}.")
            return render_template('security_details_page.html', 
                                   security_id=decoded_security_id, 
                                   metric_name=metric_name, 
                                   chart_data_json='{}',
                                   static_info=None,
                                   latest_date='N/A',
                                   message=f"No data found for {filter_col}: {decoded_security_id}.")

        # --- Set Date Index for Plotting/Reindexing --- 
        print(f"Found {len(security_data_filtered)} data points for {decoded_security_id}. Setting Date index.")
        if 'Date' not in security_data_filtered.columns:
             print("Error: 'Date' column missing after filtering base data.")
             # Handle error...
        security_data = security_data_filtered.set_index('Date').sort_index()

        # --- Get Static Info (from filtered data before indexing) --- 
        static_info = {}
        first_row_series = security_data_filtered.iloc[0] 
        for col in static_cols:
            if col in security_data_filtered.columns: # Check against the columns
                static_info[col] = first_row_series[col]
        # Also add Security Name if it exists and isn't already in static_cols
        if 'Security Name' in security_data_filtered.columns and 'Security Name' not in static_cols:
             static_info['Security Name'] = first_row_series['Security Name']
        chart_data['static_info'] = static_info
        
        # --- Get Labels & Latest Date (from Date index) --- 
        chart_data['labels'] = security_data.index.strftime('%Y-%m-%d').tolist()
        chart_data['latest_date'] = chart_data['labels'][-1] if chart_data['labels'] else 'N/A'

        # --- Prepare Base Metric Dataset --- 
        if 'Value' in security_data.columns:
             metric_values = security_data['Value'].round(3).fillna(np.nan).tolist()
             chart_data['primary_datasets'].append({
                 'label': metric_name,
                 'data': metric_values,
                 'borderColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)],
                 'backgroundColor': COLOR_PALETTE[0 % len(COLOR_PALETTE)] + '40',
                 'yAxisID': 'y', # Assign to the primary Y-axis
                 'tension': 0.1
             })
        else:
             print(f"Warning: 'Value' column not found in security_data for metric {metric_name}")

        # --- Load, Filter, Index, Reindex Price Data --- 
        try:
            print(f"Loading price file: {price_filename}")
            df_price_long, _ = load_and_process_security_data(price_filename)
            if df_price_long is not None and not df_price_long.empty and filter_col in df_price_long.columns:
                print(f"Filtering price data for {filter_col}='{decoded_security_id}'")
                price_data_filtered = df_price_long[df_price_long[filter_col].astype(str) == decoded_security_id].copy()
                
                if not price_data_filtered.empty:
                    if 'Date' in price_data_filtered.columns:
                        # Set Date index for Price data
                        price_data = price_data_filtered.set_index('Date').sort_index()
                        # Reindex using the main security_data's Date index
                        price_values = price_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['primary_datasets'].append({
                            'label': 'Price',
                            'data': price_values,
                            'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)],
                            'backgroundColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)] + '40',
                            'yAxisID': 'y1', # Assign to the secondary Y-axis
                            'tension': 0.1,
                            'borderDash': [5, 5] # Optional: dashed line for price
                        })
                        print("Added Price data to primary chart.")
                    else:
                         print("Warning: Price data missing 'Date' column after filtering.")
                else:
                     print(f"No Price data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load price data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"Price file {price_filename} not found.")
        except Exception as e:
            print(f"Error processing price data: {e}")

        # --- Load, Filter, Index, Reindex Duration Data --- 
        try:
            print(f"Loading duration file: {duration_filename}")
            df_duration_long, _ = load_and_process_security_data(duration_filename)
            if df_duration_long is not None and not df_duration_long.empty and filter_col in df_duration_long.columns:
                print(f"Filtering duration data for {filter_col}='{decoded_security_id}'")
                duration_data_filtered = df_duration_long[df_duration_long[filter_col].astype(str) == decoded_security_id].copy()

                if not duration_data_filtered.empty:
                     if 'Date' in duration_data_filtered.columns:
                        # Set Date index for Duration data
                        duration_data = duration_data_filtered.set_index('Date').sort_index()
                        # Reindex using the main security_data's Date index
                        duration_values = duration_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['duration_dataset'] = {
                           'label': 'Duration',
                           'data': duration_values,
                           'borderColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)],
                           'backgroundColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)] + '40',
                           'yAxisID': 'y', # Use standard Y-axis for this separate chart
                           'tension': 0.1
                        }
                        print("Prepared Duration data for separate chart.")
                     else:
                          print("Warning: Duration data missing 'Date' column after filtering.")
                else:
                    print(f"No Duration data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load duration data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"Duration file {duration_filename} not found.")
        except Exception as e:
            print(f"Error processing duration data: {e}")

        # --- Load, Filter, Index, Reindex Spread Duration Data --- 
        try:
            print(f"Loading spread duration file: {spread_duration_filename}")
            df_sd_long, _ = load_and_process_security_data(spread_duration_filename)
            if df_sd_long is not None and not df_sd_long.empty and filter_col in df_sd_long.columns:
                print(f"Filtering spread duration data for {filter_col}='{decoded_security_id}'")
                sd_data_filtered = df_sd_long[df_sd_long[filter_col].astype(str) == decoded_security_id].copy()

                if not sd_data_filtered.empty:
                     if 'Date' in sd_data_filtered.columns:
                        sd_data = sd_data_filtered.set_index('Date').sort_index()
                        # Reindex using the main security_data's Date index
                        sd_values = sd_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['spread_duration_dataset'] = {
                           'label': 'Spread Duration',
                           'data': sd_values,
                           'borderColor': COLOR_PALETTE[3 % len(COLOR_PALETTE)],
                           'backgroundColor': COLOR_PALETTE[3 % len(COLOR_PALETTE)] + '40',
                           'yAxisID': 'y', 
                           'tension': 0.1
                        }
                        print("Prepared Spread Duration data.")
                     else:
                          print("Warning: Spread Duration data missing 'Date' column after filtering.")
                else:
                    print(f"No Spread Duration data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load spread duration data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"Spread duration file {spread_duration_filename} not found.")
        except Exception as e:
            print(f"Error processing spread duration data: {e}")
            
        # --- Load, Filter, Index, Reindex Spread Data --- 
        try:
            print(f"Loading spread file: {spread_filename}")
            df_s_long, _ = load_and_process_security_data(spread_filename)
            if df_s_long is not None and not df_s_long.empty and filter_col in df_s_long.columns:
                print(f"Filtering spread data for {filter_col}='{decoded_security_id}'")
                s_data_filtered = df_s_long[df_s_long[filter_col].astype(str) == decoded_security_id].copy()

                if not s_data_filtered.empty:
                     if 'Date' in s_data_filtered.columns:
                        s_data = s_data_filtered.set_index('Date').sort_index()
                        s_values = s_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['spread_dataset'] = {
                           'label': 'Spread',
                           'data': s_values,
                           'borderColor': COLOR_PALETTE[4 % len(COLOR_PALETTE)],
                           'backgroundColor': COLOR_PALETTE[4 % len(COLOR_PALETTE)] + '40',
                           'yAxisID': 'y', 
                           'tension': 0.1
                        }
                        print("Prepared Spread data.")
                     else:
                          print("Warning: Spread data missing 'Date' column after filtering.")
                else:
                    print(f"No Spread data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load spread data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"Spread file {spread_filename} not found.")
        except Exception as e:
            print(f"Error processing spread data: {e}")

        # --- Load, Filter, Index, Reindex SP Spread Duration Data --- 
        try:
            print(f"Loading SP spread duration file: {sp_spread_duration_filename}")
            df_spsd_long, _ = load_and_process_security_data(sp_spread_duration_filename)
            if df_spsd_long is not None and not df_spsd_long.empty and filter_col in df_spsd_long.columns:
                print(f"Filtering SP spread duration data for {filter_col}='{decoded_security_id}'")
                spsd_data_filtered = df_spsd_long[df_spsd_long[filter_col].astype(str) == decoded_security_id].copy()

                if not spsd_data_filtered.empty:
                     if 'Date' in spsd_data_filtered.columns:
                        spsd_data = spsd_data_filtered.set_index('Date').sort_index()
                        spsd_values = spsd_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['sp_spread_duration_dataset'] = {
                           'label': 'SP Spread Duration',
                           'data': spsd_values,
                           'borderColor': COLOR_PALETTE[5 % len(COLOR_PALETTE)],
                           'backgroundColor': COLOR_PALETTE[5 % len(COLOR_PALETTE)] + '40',
                           'yAxisID': 'y', 
                           'borderDash': [5, 5], # Dashed line for SP
                           'tension': 0.1
                        }
                        print("Prepared SP Spread Duration data.")
                     else:
                          print("Warning: SP Spread Duration data missing 'Date' column after filtering.")
                else:
                    print(f"No SP Spread Duration data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load SP spread duration data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"SP Spread duration file {sp_spread_duration_filename} not found.")
        except Exception as e:
            print(f"Error processing SP spread duration data: {e}")

        # --- Load, Filter, Index, Reindex SP Duration Data --- 
        try:
            print(f"Loading SP duration file: {sp_duration_filename}")
            df_spd_long, _ = load_and_process_security_data(sp_duration_filename)
            if df_spd_long is not None and not df_spd_long.empty and filter_col in df_spd_long.columns:
                print(f"Filtering SP duration data for {filter_col}='{decoded_security_id}'")
                spd_data_filtered = df_spd_long[df_spd_long[filter_col].astype(str) == decoded_security_id].copy()

                if not spd_data_filtered.empty:
                     if 'Date' in spd_data_filtered.columns:
                        spd_data = spd_data_filtered.set_index('Date').sort_index()
                        spd_values = spd_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['sp_duration_dataset'] = {
                           'label': 'SP Duration',
                           'data': spd_values,
                           'borderColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)], # Match base duration color index
                           'backgroundColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)] + '20', # Lighter bg
                           'yAxisID': 'y', 
                           'borderDash': [5, 5], # Dashed line for SP
                           'tension': 0.1
                        }
                        print("Prepared SP Duration data.")
                     else:
                          print("Warning: SP Duration data missing 'Date' column after filtering.")
                else:
                    print(f"No SP Duration data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load SP duration data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"SP Duration file {sp_duration_filename} not found.")
        except Exception as e:
            print(f"Error processing SP duration data: {e}")
            
        # --- Load, Filter, Index, Reindex SP Spread Data --- 
        try:
            print(f"Loading SP spread file: {sp_spread_filename}")
            df_sps_long, _ = load_and_process_security_data(sp_spread_filename)
            if df_sps_long is not None and not df_sps_long.empty and filter_col in df_sps_long.columns:
                print(f"Filtering SP spread data for {filter_col}='{decoded_security_id}'")
                sps_data_filtered = df_sps_long[df_sps_long[filter_col].astype(str) == decoded_security_id].copy()

                if not sps_data_filtered.empty:
                     if 'Date' in sps_data_filtered.columns:
                        sps_data = sps_data_filtered.set_index('Date').sort_index()
                        sps_values = sps_data['Value'].reindex(security_data.index).round(3).fillna(np.nan).tolist()
                        chart_data['sp_spread_dataset'] = {
                           'label': 'SP Spread',
                           'data': sps_values,
                           'borderColor': COLOR_PALETTE[4 % len(COLOR_PALETTE)], # Match base spread color index
                           'backgroundColor': COLOR_PALETTE[4 % len(COLOR_PALETTE)] + '20', # Lighter bg
                           'yAxisID': 'y', 
                           'borderDash': [5, 5], # Dashed line for SP
                           'tension': 0.1
                        }
                        print("Prepared SP Spread data.")
                     else:
                          print("Warning: SP Spread data missing 'Date' column after filtering.")
                else:
                    print(f"No SP Spread data found for {filter_col}='{decoded_security_id}'")
            else:
                 print(f"Failed to load SP spread data or {filter_col} missing.")
        except FileNotFoundError:
             print(f"SP Spread file {sp_spread_filename} not found.")
        except Exception as e:
            print(f"Error processing SP spread data: {e}")


        # --- Render Template --- 
        print(f"Rendering security details page for {decoded_security_id}")
        # Replace NaN with None before JSON serialization
        chart_data_clean = replace_nan_with_none(chart_data)
        return render_template('security_details_page.html',
                               security_id=decoded_security_id,
                               metric_name=metric_name,
                               # Use the cleaned data for JSON
                               chart_data_json=jsonify(chart_data_clean).get_data(as_text=True),
                               static_info=chart_data['static_info'], # Static info likely doesn't have NaNs
                               latest_date=chart_data['latest_date'])

    except FileNotFoundError as e:
        print(f"Error: File not found during processing for {decoded_security_id}. Details: {e}")
        traceback.print_exc()
        return f"Error: Required data file not found for security details. {e}", 404

    except Exception as e:
        print(f"Error processing security details for {decoded_security_id}: {e}")
        traceback.print_exc()
        return f"An error occurred processing security details for {decoded_security_id}: {e}", 500

# Add a route for static asset discovery (like in metric_views)
@security_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(security_bp.root_path, '..', 'static'), filename) 