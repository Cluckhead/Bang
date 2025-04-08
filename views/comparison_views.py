# views/comparison_views.py
# This module defines the Flask Blueprint for comparing two security spread datasets.
# It includes routes for a summary view listing securities with comparison metrics
# and a detail view showing overlayed time-series charts and statistics for a single security.

from flask import Blueprint, render_template, request, current_app, jsonify
import pandas as pd
import os
import logging

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
    """Displays the comparison summary page with filtering and sorting."""
    try:
        # Capture the actual ID column name returned by the load function
        merged_data, static_data, static_cols, actual_id_col = load_comparison_data()
        
        if actual_id_col is None:
            log.error("Failed to get ID column name during data loading. Cannot proceed.")
            return "Error loading comparison data: Could not determine ID column.", 500

        # Pass the actual ID column name to the stats calculation function
        summary_stats = calculate_comparison_stats(merged_data, static_data, id_col=actual_id_col)

        if summary_stats.empty and not merged_data.empty:
             log.warning("Calculation resulted in empty stats DataFrame, but merged data was present.")
        
        # --- Filtering ---
        # Get active filters from query parameters (e.g., ?filter_Metric=Govt&filter_Currency=USD)
        active_filters = {k.replace('filter_', ''): v 
                          for k, v in request.args.items() 
                          if k.startswith('filter_') and v} # Only keep non-empty filters
        
        # Apply filters if any are active
        filtered_stats = summary_stats.copy()
        if active_filters:
            log.info(f"Applying filters: {active_filters}")
            for col, value in active_filters.items():
                if col in filtered_stats.columns:
                    # Ensure we handle potential type mismatches (e.g., filtering numeric columns)
                    try:
                        # Attempt to convert filter value to column type if numeric, otherwise use string comparison
                        if pd.api.types.is_numeric_dtype(filtered_stats[col]):
                             # Handle potential conversion errors if value is not numeric
                            try:
                                value_converted = pd.to_numeric(value)
                                filtered_stats = filtered_stats[filtered_stats[col] == value_converted]
                            except ValueError:
                                log.warning(f"Could not convert filter value '{value}' to numeric for column '{col}'. Skipping filter.")
                                # Optionally keep all rows if conversion fails, or filter for string match?
                                # For now, we skip this specific filter if conversion fails.
                        else:
                             # String comparison (case-insensitive)
                             filtered_stats = filtered_stats[filtered_stats[col].astype(str).str.contains(value, case=False, na=False)]
                    except Exception as filter_err:
                        log.error(f"Error applying filter for column '{col}' with value '{value}': {filter_err}")
                else:
                    log.warning(f"Filter column '{col}' not found in summary statistics.")
            log.info(f"Stats shape after filtering: {filtered_stats.shape}")

        # --- Sorting ---
        # Get sort parameters from query (default to Change_Correlation descending)
        sort_by = request.args.get('sort_by', 'Change_Correlation')
        sort_order = request.args.get('sort_order', 'desc')
        ascending = sort_order == 'asc'

        # Validate sort_by column
        if sort_by not in filtered_stats.columns:
            log.warning(f"Invalid sort column '{sort_by}'. Defaulting to 'Change_Correlation'.")
            sort_by = 'Change_Correlation'
            # Ensure default column exists, otherwise use ID col
            if sort_by not in filtered_stats.columns and actual_id_col in filtered_stats.columns:
                 sort_by = actual_id_col


        # Apply sorting if the column exists
        if sort_by in filtered_stats.columns:
             log.info(f"Sorting by '{sort_by}' ({'ascending' if ascending else 'descending'})")
             # Handle NaNs: put them last regardless of sort order
             na_position = 'last' 
             sorted_stats = filtered_stats.sort_values(by=sort_by, ascending=ascending, na_position=na_position)
        else:
             log.warning(f"Sort column '{sort_by}' not found after filtering. Skipping sort.")
             sorted_stats = filtered_stats # Keep the filtered but unsorted data

        # --- Prepare Data for Template ---
        
        # Generate filter options FROM THE ORIGINAL UNFILTERED DATA static columns
        filter_options = {}
        if not summary_stats.empty:
             # Use static_cols identified during loading for filter options
             for col in static_cols:
                 if col in summary_stats.columns and col != actual_id_col: # Exclude ID col from filters typically
                     # Get unique, non-null, sorted values
                     options = sorted([str(v) for v in summary_stats[col].dropna().unique()])
                     if options: # Only add filter if there are options
                         filter_options[col] = options

        # Convert NaNs to None for template rendering
        sorted_stats = sorted_stats.where(pd.notnull(sorted_stats), None)
        
        # Prepare data for template
        table_data = sorted_stats.to_dict(orient='records')
        
        # Determine visible columns (adjust as needed)
        # Start with ID, Name (if different), core stats, then static cols
        visible_columns = [actual_id_col]
        if 'Security Name' in sorted_stats.columns and actual_id_col != 'Security Name':
             visible_columns.append('Security Name')
        visible_columns.extend([
            'Level_Correlation', 'Change_Correlation', 'Mean_Abs_Diff', 
            'Max_Abs_Diff', 'Same_Date_Range', 'NaN_Count_Orig', 
            'NaN_Count_New', 'Total_Points'
        ])
        # Add static columns that are NOT the ID or Name (if shown separately)
        for col in static_cols:
             if col not in visible_columns:
                  visible_columns.append(col)
        
        # Filter visible_columns to only include those actually present in the final df
        visible_columns = [col for col in visible_columns if col in sorted_stats.columns]


        log.info(f"Rendering comparison summary with {len(table_data)} rows.")
        return render_template('comparison_page.html',
                               table_data=table_data,
                               # Pass the ordered list of columns to display
                               columns_to_display=visible_columns, 
                               filter_options=filter_options,
                               active_filters=active_filters, # Pass current filters back to template
                               id_column_name=actual_id_col, # Pass actual ID col name
                               current_sort_by=sort_by,
                               current_sort_order=sort_order)

    except Exception as e:
        log.exception("Error generating comparison summary page.")
        # Render an error page or return an error message
        return f"An error occurred: {e}", 500


@comparison_bp.route('/comparison/details/<security_id>')
def details(security_id):
    """Displays the comparison details page for a single security."""
    try:
        # Reload or filter the merged data for the specific security
        # This might be inefficient - consider caching or passing data if possible
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