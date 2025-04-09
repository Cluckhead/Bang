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
        
        # Store the original unfiltered dataframe's columns and index name
        original_columns = combined_metrics_df.columns.tolist()
        id_col_name = combined_metrics_df.index.name or 'Security ID' # Get index name before reset
        combined_metrics_df.reset_index(inplace=True) # Reset index to make ID a regular column

        # --- Collect Filter Options (from the full dataset BEFORE filtering) ---
        print("Collecting filter options...")
        current_static_in_df = [col for col in static_cols if col in combined_metrics_df.columns]
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
        # 1. Search Term Filter (on ID column)
        if search_term:
            combined_metrics_df = combined_metrics_df[combined_metrics_df[id_col_name].astype(str).str.contains(search_term, case=False, na=False)]
            print(f"Applied search term '{search_term}'. Rows remaining: {len(combined_metrics_df)}")

        # 2. Active Exclusions Filter
        try:
            active_exclusion_ids = get_active_exclusions()
            if active_exclusion_ids:
                 combined_metrics_df = combined_metrics_df[~combined_metrics_df[id_col_name].astype(str).isin(active_exclusion_ids)]
                 print(f"Applied {len(active_exclusion_ids)} exclusions. Rows remaining: {len(combined_metrics_df)}")
        except Exception as e:
            print(f"Warning: Error loading or applying exclusions: {e}")
            # Continue without exclusions if loading fails

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
        total_pages = math.ceil(total_items / PER_PAGE)
        page = max(1, min(page, total_pages)) # Ensure page is within valid range
        start_index = (page - 1) * PER_PAGE
        end_index = start_index + PER_PAGE
        
        print(f"Pagination: Total items={total_items}, Total pages={total_pages}, Current page={page}, Per page={PER_PAGE}")
        
        paginated_df = combined_metrics_df.iloc[start_index:end_index]

        # --- Prepare Data for Template ---
        securities_data_list = paginated_df.round(3).to_dict(orient='records')
        # Replace NaN with None for JSON compatibility / template rendering
        for row in securities_data_list:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None

        # Define column order (ID first, then Static, then Metrics)
        ordered_static_cols = sorted([col for col in static_cols if col in paginated_df.columns])
        metric_cols_ordered = ['Latest Value', 'Change', 'Change Z-Score', 'Mean', 'Max', 'Min']
        # Ensure only existing columns are included and ID col is first
        final_col_order = [id_col_name] + \
                          [col for col in ordered_static_cols if col in paginated_df.columns] + \
                          [col for col in metric_cols_ordered if col in paginated_df.columns]
        
        # Ensure all original columns are considered if they aren't static or metric
        other_cols = [col for col in paginated_df.columns if col not in final_col_order and col != id_col_name]
        final_col_order.extend(other_cols) # Add any remaining columns

        print(f"Final column order for display: {final_col_order}")


        # Create pagination context for the template
        pagination_context = {
            'page': page,
            'per_page': PER_PAGE,
            'total_pages': total_pages,
            'total_items': total_items,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1,
            'next_num': page + 1,
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

@security_bp.route('/details/<metric_name>/<path:security_id>') # Corresponds to /security/details/..., use path converter
def security_details_page(metric_name, security_id):
    """Renders a page showing the time series chart for a specific security from a specific metric file."""
    # Decode the security_id using standard library
    decoded_security_id = unquote(security_id)
    
    filename = f"sec_{metric_name}.csv"
    price_filename = "sec_Price.csv" # Define price filename
    duration_filename = "sec_Duration.csv" # Define duration filename
    print(f"--- Requesting Security Details --- Metric: {metric_name}, Security ID (Encoded): {security_id}, Security ID (Decoded): {decoded_security_id}, File: {filename}")

    try:
        # 1. Load and process the specific security data file (for the primary metric)
        df_long, static_cols = load_and_process_security_data(filename)

        if df_long is None or df_long.empty:
            return f"Error: Could not load or process data for file '{filename}'", 404

        # Check if the requested security ID exists in the data using the DECODED ID
        actual_id_col_name = df_long.index.names[1]
        if decoded_security_id not in df_long.index.get_level_values(actual_id_col_name):
             return f"Error: Security ID '{decoded_security_id}' not found in file '{filename}'.", 404

        # 2. Extract historical data for the specific security using the DECODED ID
        security_data = df_long.xs(decoded_security_id, level=actual_id_col_name).sort_index().copy()

        # Filter to include only business days (Mon-Fri)
        if isinstance(security_data.index, pd.DatetimeIndex):
            security_data = security_data[security_data.index.dayofweek < 5]
        else:
            print(f"Warning: Index for primary metric data ({metric_name}) for {decoded_security_id} is not DatetimeIndex, skipping business day filter.")

        if security_data.empty:
            # Check if empty *after* filtering too
            return f"Error: No historical data found for Security ID '{decoded_security_id}' in file '{filename}' (or only weekend data).", 404

        # Extract static dimension values for display
        static_info = {}
        if not security_data.empty:
            first_row = security_data.iloc[0]
            for col in static_cols:
                if col in first_row.index:
                    static_info[col] = first_row[col]

        # 3. Load Price and Duration data (if files exist)
        price_data = pd.DataFrame()
        duration_data = pd.DataFrame()

        # Load Price Data
        try:
            price_df_long, _ = load_and_process_security_data(price_filename)
            if price_df_long is not None and not price_df_long.empty:
                price_id_col = price_df_long.index.names[1]
                if decoded_security_id in price_df_long.index.get_level_values(price_id_col):
                    price_data = price_df_long.xs(decoded_security_id, level=price_id_col)[['Value']].sort_index().copy()
                    price_data.rename(columns={'Value': 'Price'}, inplace=True)
                    # Filter price data to business days
                    if isinstance(price_data.index, pd.DatetimeIndex):
                        price_data = price_data[price_data.index.dayofweek < 5]
                    else:
                        print(f"Warning: Index for price data for {decoded_security_id} is not DatetimeIndex, skipping business day filter.")

        except FileNotFoundError:
            print(f"Price file '{price_filename}' not found. Price chart will not be available.")
        except Exception as e:
            print(f"Error loading price data for {decoded_security_id}: {e}")
            traceback.print_exc()

        # Load Duration Data
        try:
            duration_df_long, _ = load_and_process_security_data(duration_filename)
            if duration_df_long is not None and not duration_df_long.empty:
                duration_id_col = duration_df_long.index.names[1]
                if decoded_security_id in duration_df_long.index.get_level_values(duration_id_col):
                    duration_data = duration_df_long.xs(decoded_security_id, level=duration_id_col)[['Value']].sort_index().copy()
                    duration_data.rename(columns={'Value': 'Duration'}, inplace=True)
                    # Filter duration data to business days
                    if isinstance(duration_data.index, pd.DatetimeIndex):
                        duration_data = duration_data[duration_data.index.dayofweek < 5]
                    else:
                        print(f"Warning: Index for duration data for {decoded_security_id} is not DatetimeIndex, skipping business day filter.")

        except FileNotFoundError:
            print(f"Duration file '{duration_filename}' not found. Duration chart will not be available.")
        except Exception as e:
            print(f"Error loading duration data for {decoded_security_id}: {e}")
            traceback.print_exc()

        # 4. Prepare data for the primary chart
        labels = security_data.index.strftime('%Y-%m-%d').tolist()
        # Initialize datasets list for the primary chart
        primary_datasets = [{
            'label': f'{decoded_security_id} - {metric_name} Value', # Use decoded ID in label
            'data': security_data['Value'].round(3).fillna(np.nan).tolist(),
            'borderColor': COLOR_PALETTE[0], # Use first color
            'backgroundColor': COLOR_PALETTE[0] + '40',
            'tension': 0.1,
            'yAxisID': 'y' # Assign primary metric to the default 'y' axis
        }]

        # Initialize chart_data_for_js with primary data
        chart_data_for_js = {
            'labels': labels,
            'primary_datasets': primary_datasets, # Use a specific key for primary chart datasets
            'duration_dataset': None # Initialize duration dataset as None
        }

        latest_date_overall = security_data.index.max()

        # --- Attempt to load and add Price data to the primary chart ---
        try:
            print(f"Attempting to load price data from {price_filename} for {decoded_security_id}...")
            price_df_long, _ = load_and_process_security_data(price_filename) # Ignore static cols from price file

            if price_df_long is not None and not price_df_long.empty:
                price_actual_id_col = price_df_long.index.names[1] # Get ID column name from price file
                if decoded_security_id in price_df_long.index.get_level_values(price_actual_id_col):
                    price_data = price_df_long.xs(decoded_security_id, level=price_actual_id_col).sort_index().copy()
                    # Reindex price data to align dates with the main metric data
                    price_data = price_data.reindex(security_data.index)

                    if not price_data.empty:
                        price_dataset = {
                            'label': f'{decoded_security_id} - Price',
                            'data': price_data['Value'].round(3).fillna(np.nan).tolist(),
                            'borderColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)], # Use second color
                            'backgroundColor': COLOR_PALETTE[1 % len(COLOR_PALETTE)] + '40',
                            'tension': 0.1,
                            'yAxisID': 'y1' # Assign price data to the second y-axis
                        }
                        # Append price dataset to the primary_datasets list
                        chart_data_for_js['primary_datasets'].append(price_dataset)
                        print("Successfully added Price data overlay to primary chart.")
                    else:
                         print(f"Warning: Price data found for {decoded_security_id}, but was empty after aligning dates.")
                else:
                     print(f"Warning: Security ID {decoded_security_id} not found in {price_filename}.")
            else:
                 print(f"Warning: Could not load or process {price_filename}.")
        except FileNotFoundError:
            print(f"Warning: Price data file '{price_filename}' not found. Skipping price overlay.")
        except Exception as e_price:
            print(f"Warning: Error processing price data for {decoded_security_id} from {price_filename}: {e_price}")
            traceback.print_exc() # Log the price processing error but continue

        # --- Attempt to load and add Duration data for the second chart ---
        try:
            print(f"Attempting to load duration data from {duration_filename} for {decoded_security_id}...")
            duration_df_long, _ = load_and_process_security_data(duration_filename) # Ignore static cols

            if duration_df_long is not None and not duration_df_long.empty:
                duration_actual_id_col = duration_df_long.index.names[1] # Get ID column name
                if decoded_security_id in duration_df_long.index.get_level_values(duration_actual_id_col):
                    duration_data = duration_df_long.xs(decoded_security_id, level=duration_actual_id_col).sort_index().copy()
                    # Reindex duration data to align dates with the main metric data
                    duration_data = duration_data.reindex(security_data.index)

                    if not duration_data.empty:
                        duration_dataset = {
                            'label': f'{decoded_security_id} - Duration', # Use decoded ID
                            'data': duration_data['Value'].round(3).fillna(np.nan).tolist(),
                            'borderColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)], # Use third color
                            'backgroundColor': COLOR_PALETTE[2 % len(COLOR_PALETTE)] + '40',
                            'tension': 0.1
                            # No yAxisID needed if it's a separate chart with its own scale
                        }
                        # Assign duration dataset to its specific key
                        chart_data_for_js['duration_dataset'] = duration_dataset
                        print("Successfully prepared Duration data for separate chart.")
                    else:
                         print(f"Warning: Duration data found for {decoded_security_id}, but was empty after aligning dates.")
                else:
                     print(f"Warning: Security ID {decoded_security_id} not found in {duration_filename}.")
            else:
                 print(f"Warning: Could not load or process {duration_filename}.")
        except FileNotFoundError:
            print(f"Warning: Duration data file '{duration_filename}' not found. Skipping duration chart.")
        except Exception as e_duration:
            print(f"Warning: Error processing duration data for {decoded_security_id} from {duration_filename}: {e_duration}")
            traceback.print_exc() # Log the duration processing error but continue

        # 4. Render the template
        return render_template('security_details_page.html',
                               metric_name=metric_name,
                               security_id=decoded_security_id,
                               static_info=static_info,
                               chart_data_json=jsonify(chart_data_for_js).get_data(as_text=True),
                               latest_date=latest_date_overall.strftime('%d/%m/%Y'))

    except FileNotFoundError:
        return f"Error: Data file '{filename}' not found.", 404
    except ValueError as ve:
        print(f"Value Error processing security details for {metric_name}/{decoded_security_id}: {ve}")
        return f"Error processing details for {decoded_security_id}: {ve}", 400
    except Exception as e:
        print(f"Error processing security details for {metric_name}/{decoded_security_id}: {e}")
        traceback.print_exc()
        return f"An error occurred processing details for {decoded_security_id}: {e}", 500 

# Add a route for static asset discovery (like in metric_views)
@security_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(security_bp.root_path, '..', 'static'), filename) 