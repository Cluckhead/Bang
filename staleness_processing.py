#!/usr/bin/env python
# staleness_processing.py
# This module contains the core logic for detecting stale data in securities files.
# It identifies patterns of placeholder values that indicate stale or missing data.
# Only processes files with naming pattern sec_*.csv and sp_sec_*.csv.

import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging
try:
    from config import DATA_FOLDER, ID_COLUMN
except ImportError:
    # Fall back to defaults if config not available
    DATA_FOLDER = "Data"
    ID_COLUMN = "ISIN"

# Logging is now handled centrally by the Flask app factory in app.py
logger = logging.getLogger(__name__)

# Constants
DEFAULT_STALENESS_THRESHOLD_DAYS = 5
DEFAULT_PLACEHOLDER_VALUES = [100]  # Common placeholder values indicating stale data
DEFAULT_CONSECUTIVE_THRESHOLD = 3   # Number of consecutive placeholders to consider stale

def is_placeholder_value(value, placeholder_values=None):
    """
    Check if a value appears to be a placeholder (stale data indicator).
    
    Args:
        value: The value to check
        placeholder_values: List of values considered placeholders (default: [100])
        
    Returns:
        Boolean indicating if the value is likely a placeholder
    """
    if placeholder_values is None:
        placeholder_values = DEFAULT_PLACEHOLDER_VALUES
        
    if pd.isna(value):
        return True
        
    try:
        # Try to convert to numeric for comparison
        numeric_value = float(value)
        for placeholder in placeholder_values:
            # Use approximate equality to handle float precision issues
            placeholder_float = float(placeholder)
            if abs(numeric_value - placeholder_float) < 0.0001:
                return True
    except (ValueError, TypeError):
        # If value can't be converted to numeric, it's not our placeholder
        pass
        
    return False

def get_staleness_summary(data_folder=DATA_FOLDER, exclusions_df=None, threshold_days=DEFAULT_STALENESS_THRESHOLD_DAYS):
    """
    Generate a summary of stale data across all files in the data folder.
    
    Args:
        data_folder: Path to folder containing data files
        exclusions_df: DataFrame of securities to exclude from analysis
        threshold_days: Days threshold for time-based staleness
        
    Returns:
        Dictionary with file names as keys and staleness summaries as values
    """
    summary = {}
    
    try:
        # Process only sec_*.csv and sp_sec_*.csv files in the data folder
        for filename in os.listdir(data_folder):
            if filename.endswith('.csv') and (filename.startswith('sec_') or filename.startswith('sp_sec_')):
                try:
                    file_path = os.path.join(data_folder, filename)
                    
                    # Get stale securities details
                    stale_securities, latest_date, total_count = get_stale_securities_details(
                        filename=filename, 
                        threshold_days=threshold_days, 
                        data_folder=data_folder, 
                        exclusions_df=exclusions_df
                    )
                    
                    # Add to summary
                    stale_count = len(stale_securities)
                    
                    metric_name = filename.replace('.csv', '')
                    summary[filename] = {
                        'metric_name': metric_name,
                        'latest_date': latest_date,
                        'total_count': total_count,
                        'stale_count': stale_count,
                        'stale_percentage': round(stale_count / total_count * 100, 1) if total_count > 0 else 0
                    }
                    logger.debug(f"File {filename}: Found {stale_count} stale out of {total_count} securities")
                    
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {e}", exc_info=True)
                    # Add error info to summary
                    summary[filename] = {
                        'metric_name': filename.replace('.csv', ''),
                        'latest_date': 'Error',
                        'total_count': 'Error',
                        'stale_count': f"Error: {str(e)}",
                        'stale_percentage': 'Error'
                    }
    except Exception as e:
        logger.error(f"Error generating staleness summary: {e}", exc_info=True)
        
    return summary

def get_stale_securities_details(filename, threshold_days=DEFAULT_STALENESS_THRESHOLD_DAYS, 
                               data_folder=DATA_FOLDER, exclusions_df=None):
    """
    Get detailed information about stale securities in a specific file.
    
    Args:
        filename: Name of the file to analyze
        threshold_days: Days threshold for time-based staleness
        data_folder: Path to folder containing data files
        exclusions_df: DataFrame of securities to exclude from analysis
        
    Returns:
        (list of stale securities, latest date in file, total securities count)
    """
    file_path = os.path.join(data_folder, filename)
    stale_securities = []
    latest_date = None
    total_count = 0
    
    try:
        # Read the file
        df = pd.read_csv(file_path)
        
        # Extract metric name from filename
        metric_name = filename.replace('.csv', '')
        
        # Check if ID column exists
        if ID_COLUMN not in df.columns:
            id_column = df.columns[0]  # Fallback to first column
            logger.info(f"ID column '{ID_COLUMN}' not found in {filename}, using {id_column} instead.")
        else:
            id_column = ID_COLUMN
        
        # Get date columns (columns after the metadata)
        # First 6 columns are typically: ISIN, Name, Funds, Type, Callable, Currency
        meta_columns = df.columns[:6]
        date_columns = df.columns[6:]
        
        # Convert date columns to datetime if they look like dates
        date_objects = []
        for col in date_columns:
            try:
                # Try to parse as DD/MM/YYYY
                date_obj = datetime.strptime(col, '%d/%m/%Y')
                date_objects.append(date_obj)
            except ValueError:
                logger.warning(f"Column {col} in {filename} doesn't appear to be a date.")
                date_objects.append(None)
        
        # Find the latest date in the file
        valid_dates = [d for d in date_objects if d is not None]
        if valid_dates:
            latest_date = max(valid_dates).strftime('%d/%m/%Y')
            latest_date_idx = date_objects.index(max(valid_dates))
        else:
            latest_date = "Unknown"
            latest_date_idx = len(date_columns) - 1  # Default to last column
        
        # Process each security
        excluded_ids = []
        if exclusions_df is not None and not exclusions_df.empty:
            excluded_ids = exclusions_df[exclusions_df['file'] == filename][id_column].tolist()
        
        total_count = 0  # Reset counter for non-excluded securities
        
        for idx, row in df.iterrows():
            security_id = str(row[id_column])
            
            # Skip excluded securities
            if security_id in excluded_ids:
                continue
                
            total_count += 1
            
            # Extract static information (metadata)
            static_info = {}
            for col in meta_columns:
                if col != id_column:
                    static_info[col] = row[col]
            
            # Get date values for this security
            date_values = row[date_columns].values
            
            # Method 1: Check for placeholder value patterns (e.g., repeated 100s)
            consecutive_placeholders = 0
            stale_start_idx = None
            
            for i, val in enumerate(date_values):
                # Check if this value is a placeholder
                if is_placeholder_value(val):
                    consecutive_placeholders += 1
                    if consecutive_placeholders == 1:
                        stale_start_idx = i
                else:
                    consecutive_placeholders = 0
                    stale_start_idx = None
                
                # If we've found enough consecutive placeholders, mark as stale
                if consecutive_placeholders >= DEFAULT_CONSECUTIVE_THRESHOLD:
                    stale_start_date = date_columns[stale_start_idx]
                    
                    # Calculate days stale
                    days_stale = 0
                    if stale_start_idx is not None and stale_start_idx < len(date_objects) and date_objects[stale_start_idx] is not None:
                        last_update_date = date_objects[stale_start_idx]
                        if latest_date_idx < len(date_objects) and date_objects[latest_date_idx] is not None:
                            days_stale = (date_objects[latest_date_idx] - last_update_date).days
                    
                    # Add to stale securities list
                    stale_securities.append({
                        'id': security_id,
                        'metric_name': metric_name,
                        'static_info': static_info,
                        'last_update': stale_start_date,
                        'days_stale': days_stale,
                        'stale_type': 'placeholder_pattern',
                        'consecutive_placeholders': consecutive_placeholders
                    })
                    break
            
            # Method 2: For securities not already marked stale by Method 1,
            # check for time-based staleness (last non-empty value is too old)
            if consecutive_placeholders < DEFAULT_CONSECUTIVE_THRESHOLD:
                # Find the last non-placeholder value
                last_valid_idx = None
                for i in range(len(date_values) - 1, -1, -1):
                    if not is_placeholder_value(date_values[i]):
                        last_valid_idx = i
                        break
                
                # If found a valid value, check if it's stale based on time
                if last_valid_idx is not None and last_valid_idx < latest_date_idx:
                    days_difference = 0
                    if last_valid_idx < len(date_objects) and date_objects[last_valid_idx] is not None:
                        last_update_date = date_objects[last_valid_idx]
                        if latest_date_idx < len(date_objects) and date_objects[latest_date_idx] is not None:
                            days_difference = (date_objects[latest_date_idx] - last_update_date).days
                    
                    if days_difference > threshold_days:
                        stale_securities.append({
                            'id': security_id,
                            'metric_name': metric_name,
                            'static_info': static_info,
                            'last_update': date_columns[last_valid_idx],
                            'days_stale': days_difference,
                            'stale_type': 'time_based',
                            'consecutive_placeholders': 0
                        })
            
        logger.info(f"[{filename} - Details] Found {len(stale_securities)} stale securities.")
    except Exception as e:
        logger.error(f"Error analyzing file {filename}: {e}", exc_info=True)
        raise
    
    return stale_securities, latest_date, total_count 