# security_processing.py
# This file contains functions for loading and processing security-level data 
# from files where time series data is stored in columns.

import pandas as pd
import os
import numpy as np
import re # For checking date-like column headers

DATA_FOLDER = 'Data'

def _is_date_like(column_name):
    """Check if a column name looks like a date (e.g., DD/MM/YYYY)."""
    # Simple regex, adjust if date formats vary significantly
    # Corrected regex: Use single backslashes in raw strings
    return bool(re.match(r'^\d{2}/\d{2}/\d{4}$', column_name))

def load_and_process_security_data(filename):
    """Loads security data, identifies static/date columns, and melts to long format.

    Args:
        filename (str): The name of the CSV file (e.g., 'sec_Spread.csv').

    Returns:
        tuple: (pandas.DataFrame, list[str])
               - Processed DataFrame in long format with MultiIndex (Date, Security ID).
               - List of identified static column names (excluding Security ID).
        Returns (None, []) if an error occurs.
    """
    filepath = os.path.join(DATA_FOLDER, filename)
    print(f"Attempting to load security data from: {filepath}")

    try:
        # Read just the header to identify column types
        header_df = pd.read_csv(filepath, nrows=0, on_bad_lines='skip', encoding='utf-8')
        all_cols = header_df.columns.tolist()

        if not all_cols:
            raise ValueError("CSV file appears to be empty or header is missing.")

        # Assume first column is the Security ID
        id_col = all_cols[0]
        
        # Identify static and date columns dynamically
        static_cols = []
        date_cols = []
        for col in all_cols[1:]: # Skip the ID column
            if _is_date_like(col):
                date_cols.append(col)
            else:
                static_cols.append(col.strip()) # Store stripped static col names

        if not date_cols:
            raise ValueError("No date-like columns found (expected format DD/MM/YYYY).")
        if not id_col:
             raise ValueError("Could not identify the Security ID column (expected first column).")

        print(f"Identified ID Col: {id_col}")
        print(f"Identified Static Cols: {static_cols}")
        # print(f"Identified Date Cols: {date_cols[:5]}...\") # Avoid excessive logging

        # Read the full data
        df_wide = pd.read_csv(filepath, encoding='utf-8')
        df_wide.columns = df_wide.columns.str.strip() # Strip whitespace from all columns
        
        # Ensure ID column name is also stripped if needed for melting
        id_col = id_col.strip() 
        
        # Ensure static columns used for id_vars exist after stripping
        id_vars = [id_col] + [col for col in static_cols if col in df_wide.columns]
        value_vars = [col for col in date_cols if col in df_wide.columns] # Ensure date columns exist

        if not value_vars:
             raise ValueError("Date columns identified in header not found in data frame after loading.")
        
        # Melt the DataFrame
        df_long = pd.melt(df_wide,
                          id_vars=id_vars,
                          value_vars=value_vars,
                          var_name='Date_Str',
                          value_name='Value')

        # Process Date and Value columns
        df_long['Date'] = pd.to_datetime(df_long['Date_Str'], format='%d/%m/%Y', errors='coerce')
        df_long['Value'] = pd.to_numeric(df_long['Value'], errors='coerce')

        # Drop rows where date conversion failed or value is missing after conversion
        df_long.dropna(subset=['Date', 'Value', id_col], inplace=True)
        
        if df_long.empty:
             print("Warning: DataFrame is empty after melting, date conversion, and NaN drop.")
             # Return None, [] might be better than empty df, list? Let's stick to df for consistency downstream
             return pd.DataFrame(), static_cols 

        # Set MultiIndex
        df_long.set_index(['Date', id_col], inplace=True)
        df_long.sort_index(inplace=True)
        
        # Drop the original string date column
        df_long.drop(columns=['Date_Str'], inplace=True)

        print(f"Successfully loaded and processed {filename}. Shape: {df_long.shape}")
        return df_long, static_cols

    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return None, []
    except ValueError as ve:
        print(f"Error processing header or columns in {filename}: {ve}")
        return None, []
    except Exception as e:
        print(f"An unexpected error occurred loading/processing {filename}: {e}")
        import traceback
        traceback.print_exc()
        return None, []


def calculate_security_latest_metrics(df, static_cols):
    """Calculates latest metrics for each security based on its 'Value' column.

    Args:
        df (pd.DataFrame): Processed long-format DataFrame with MultiIndex (Date, Security ID).
        static_cols (list[str]): List of static column names present in the DataFrame.

    Returns:
        pandas.DataFrame: DataFrame indexed by Security ID, including static columns and
                          calculated metrics (Latest Value, Change, Mean, Max, Min, Change Z-Score).
                          Returns an empty DataFrame if input is empty or processing fails.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    try:
        latest_date = df.index.get_level_values('Date').max()
        security_ids = df.index.get_level_values(df.index.names[1]).unique() # Get ID level name dynamically

        all_metrics_list = []

        for sec_id in security_ids:
            try:
                sec_data_hist = df.xs(sec_id, level=df.index.names[1]).sort_index()
                
                if sec_data_hist.empty: continue

                sec_metrics = {}
                
                # Add static columns first
                # Take the first row's values assuming they are constant per security
                static_data = sec_data_hist.iloc[0] 
                for static_col in static_cols:
                    if static_col in static_data.index:
                         sec_metrics[static_col] = static_data[static_col]
                    else:
                         sec_metrics[static_col] = np.nan # Should not happen if df is correct

                # Calculate metrics for the 'Value' column
                value_hist = sec_data_hist['Value']
                value_change_hist = value_hist.diff()

                # Base historical stats (level)
                sec_metrics['Mean'] = value_hist.mean()
                sec_metrics['Max'] = value_hist.max()
                sec_metrics['Min'] = value_hist.min()

                # Stats for change
                change_mean = value_change_hist.mean()
                change_std = value_change_hist.std()

                # Latest values
                if latest_date in sec_data_hist.index:
                    latest_row = sec_data_hist.loc[latest_date]
                    latest_value = latest_row['Value']
                    # Ensure the index includes the latest date before accessing change
                    latest_change = value_change_hist.loc[latest_date] if latest_date in value_change_hist.index else np.nan

                    sec_metrics['Latest Value'] = latest_value
                    sec_metrics['Change'] = latest_change

                    # Calculate Change Z-Score
                    change_z_score = np.nan
                    if change_std is not None and change_std != 0 and pd.notna(change_std) and pd.notna(latest_change):
                        change_z_score = (latest_change - change_mean) / change_std
                    
                    sec_metrics['Change Z-Score'] = change_z_score

                else:
                    # Security missing the latest date
                    sec_metrics['Latest Value'] = np.nan
                    sec_metrics['Change'] = np.nan
                    sec_metrics['Change Z-Score'] = np.nan
                
                # Add the security ID itself for potential merging/joining later if needed
                # Although it will become the index
                sec_metrics[df.index.names[1]] = sec_id 
                
                all_metrics_list.append(sec_metrics)
            
            except Exception as inner_e:
                print(f"Error calculating metrics for security {sec_id}: {inner_e}")
                # Optionally add a placeholder row with NaNs? Or just skip. Let's skip.
                continue


        if not all_metrics_list:
            return pd.DataFrame()

        # Create DataFrame and set index
        latest_metrics_df = pd.DataFrame(all_metrics_list)
        id_col_name = df.index.names[1] # Get the actual ID column name used
        if id_col_name in latest_metrics_df.columns:
             latest_metrics_df.set_index(id_col_name, inplace=True)
        else:
             print(f"Warning: Security ID column '{id_col_name}' not found for setting index.")
             # Fallback or error? Let's return as is for now.

        # Sorting will be done after aggregation in app.py
        return latest_metrics_df

    except Exception as e:
        print(f"An unexpected error occurred during security metric calculation: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame() 