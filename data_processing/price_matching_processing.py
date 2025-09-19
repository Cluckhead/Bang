#!/usr/bin/env python
# price_matching_processing.py
# This module compares prices between the most recent BondAnalyticsResults_Full_* file 
# and sec_Price.csv, calculating percentage match where both files have data for the same security.
# Maps securities using External Security ID (BondAnalyticsResults) to ISIN (sec_Price.csv).

import os
import pandas as pd
import numpy as np
import glob
from datetime import datetime
import logging
import csv
from core.io_lock import append_rows_locked
from core import config

try:
    from core.config import DATA_FOLDER, ID_COLUMN
    if not DATA_FOLDER:
        raise ImportError("DATA_FOLDER not set")
except Exception:
    # Fall back to settings.yaml then default
    try:
        from core.settings_loader import get_app_config  # type: ignore
        app_cfg = get_app_config() or {}
        dfolder = app_cfg.get('data_folder') or 'Data'
        DATA_FOLDER = dfolder if os.path.isabs(dfolder) else os.path.join(os.path.dirname(__file__), dfolder)
    except Exception:
        DATA_FOLDER = "Data"
    try:
        from core.config import ID_COLUMN  # type: ignore
    except Exception:
        ID_COLUMN = "ISIN"

# Logging is now handled centrally by the Flask app factory in app.py
logger = logging.getLogger(__name__)

# Constants
FLOAT_TOLERANCE = 1e-6
BOND_ANALYTICS_FOLDER = "Minny/Resources"
BOND_ANALYTICS_PATTERN = "BondAnalyticsResults_Full_*.csv"
SEC_PRICE_FILE = "sec_Price.csv"
HISTORICAL_RESULTS_FILE = "price_matching_history.csv"

def get_most_recent_bond_analytics_file(bond_analytics_folder=BOND_ANALYTICS_FOLDER):
    """
    Find the most recent BondAnalyticsResults_Full_* file based on the date in the filename.
    Returns tuple of (file_path, date_string) or (None, None) if no files found.
    """
    try:
        pattern = os.path.join(bond_analytics_folder, BOND_ANALYTICS_PATTERN)
        files = glob.glob(pattern)
        
        if not files:
            logger.warning(f"No BondAnalyticsResults files found in {bond_analytics_folder}")
            return None, None
        
        # Extract dates from filenames and find most recent
        file_dates = []
        for file_path in files:
            filename = os.path.basename(file_path)
            # Extract date from filename: BondAnalyticsResults_Full_YYYYMMDD_HHMMSS.csv
            try:
                date_part = filename.split('_')[2]  # Get YYYYMMDD part
                date_obj = datetime.strptime(date_part, '%Y%m%d')
                file_dates.append((file_path, date_obj, date_part))
            except (IndexError, ValueError) as e:
                logger.warning(f"Could not parse date from filename {filename}: {e}")
                continue
        
        if not file_dates:
            logger.warning("No valid date patterns found in BondAnalyticsResults filenames")
            return None, None
        
        # Sort by date and get most recent
        file_dates.sort(key=lambda x: x[1], reverse=True)
        most_recent_file, most_recent_date, date_string = file_dates[0]
        
        logger.info(f"Found most recent BondAnalyticsResults file: {most_recent_file} (date: {date_string})")
        return most_recent_file, date_string
        
    except Exception as e:
        logger.error(f"Error finding most recent BondAnalyticsResults file: {e}", exc_info=True)
        return None, None

def get_price_from_sec_price_for_date(row, target_date, date_columns):
    """
    Get the price from sec_Price.csv for a specific date.
    target_date should be in YYYY-MM-DD format to match column names.
    Returns the price for that date or None if not found/invalid.
    """
    if target_date in date_columns:
        value = row[target_date]
        if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
    return None

def get_latest_price_from_sec_price(row, date_columns):
    """
    Get the latest non-null price from sec_Price.csv date columns for a given row.
    Returns the latest price or None if no valid price found.
    """
    # Iterate through date columns in reverse order (most recent first)
    for col in reversed(date_columns):
        value = row[col]
        if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
            try:
                return float(value)
            except (ValueError, TypeError):
                continue
    return None

def compare_prices(price1, price2, tolerance=FLOAT_TOLERANCE):
    """
    Compare two prices within a tolerance.
    Returns True if prices match within tolerance, False otherwise.
    """
    if price1 is None or price2 is None:
        return False
    
    try:
        p1 = float(price1)
        p2 = float(price2)
        return abs(p1 - p2) <= tolerance
    except (ValueError, TypeError):
        return False

def run_price_matching_check(
    data_folder=DATA_FOLDER,
    bond_analytics_folder=BOND_ANALYTICS_FOLDER,
    save_historical=True,
    specific_file_path=None,
    target_date=None
):
    """
    Run price matching check between BondAnalyticsResults file and sec_Price.csv.
    If specific_file_path is provided, uses that file instead of finding most recent.
    If target_date is provided (YYYY-MM-DD format), gets prices for that specific date from sec_Price.csv.
    Returns dictionary with results suitable for dashboard_kpis.json.
    """
    try:
        # Determine which BondAnalyticsResults file to use
        if specific_file_path and os.path.exists(specific_file_path):
            bond_file_path = specific_file_path
            # Extract date from filename
            filename = os.path.basename(specific_file_path)
            try:
                date_string = filename.split('_')[2]  # Get YYYYMMDD part
            except IndexError:
                date_string = "Unknown"
            logger.info(f"Using specific BondAnalyticsResults file: {bond_file_path}")
        else:
            # Find most recent BondAnalyticsResults file
            bond_file_path, date_string = get_most_recent_bond_analytics_file(bond_analytics_folder)
            if not bond_file_path:
                return {
                    "error": "No BondAnalyticsResults files found",
                    "match_percentage": 0,
                    "total_comparisons": 0,
                    "matches": 0,
                    "latest_date": "Unknown"
                }
        
        # Load BondAnalyticsResults file
        logger.info(f"Loading BondAnalyticsResults file: {bond_file_path}")
        bond_df = pd.read_csv(bond_file_path)
        
        if 'External Security ID' not in bond_df.columns or 'Price' not in bond_df.columns:
            error_msg = "Required columns (External Security ID, Price) not found in BondAnalyticsResults file"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "match_percentage": 0,
                "total_comparisons": 0,
                "matches": 0,
                "latest_date": date_string or "Unknown"
            }
        
        # Load sec_Price.csv file
        sec_price_path = os.path.join(data_folder, SEC_PRICE_FILE)
        if not os.path.exists(sec_price_path):
            error_msg = f"sec_Price.csv not found at {sec_price_path}"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "match_percentage": 0,
                "total_comparisons": 0,
                "matches": 0,
                "latest_date": date_string or "Unknown"
            }
        
        logger.info(f"Loading sec_Price.csv file: {sec_price_path}")
        sec_price_df = pd.read_csv(sec_price_path)
        
        if ID_COLUMN not in sec_price_df.columns:
            error_msg = f"ISIN column not found in sec_Price.csv"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "match_percentage": 0,
                "total_comparisons": 0,
                "matches": 0,
                "latest_date": date_string or "Unknown"
            }
        
        # Identify date columns in sec_Price.csv (skip metadata columns)
        meta_columns = sec_price_df.columns[:len(config.METADATA_COLS)] if hasattr(config, 'METADATA_COLS') else sec_price_df.columns[:6]
        date_columns = [col for col in sec_price_df.columns if col not in meta_columns]
        
        logger.info(f"Found {len(date_columns)} date columns in sec_Price.csv")
        
        # If target_date is provided, convert YYYYMMDD to YYYY-MM-DD format for column matching
        sec_price_date_column = None
        if target_date:
            if len(target_date) == 8:  # YYYYMMDD format
                try:
                    formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
                    if formatted_date in date_columns:
                        sec_price_date_column = formatted_date
                        logger.info(f"Using specific date column: {sec_price_date_column}")
                    else:
                        logger.warning(f"Date column {formatted_date} not found in sec_Price.csv")
                except Exception as e:
                    logger.warning(f"Could not format target_date {target_date}: {e}")
            elif target_date in date_columns:  # Already in YYYY-MM-DD format
                sec_price_date_column = target_date
                logger.info(f"Using specific date column: {sec_price_date_column}")
        
        # Create mapping of ISIN to price from sec_Price.csv
        sec_price_map = {}
        for _, row in sec_price_df.iterrows():
            isin = str(row[ID_COLUMN]).strip()
            
            if sec_price_date_column:
                # Get price for specific date
                price = get_price_from_sec_price_for_date(row, sec_price_date_column, date_columns)
            else:
                # Get latest available price
                price = get_latest_price_from_sec_price(row, date_columns)
            
            if price is not None:
                sec_price_map[isin] = price
        
        price_source = f"specific date ({sec_price_date_column})" if sec_price_date_column else "latest available"
        logger.info(f"Found {len(sec_price_map)} securities with valid prices in sec_Price.csv using {price_source}")
        
        # Compare prices
        total_comparisons = 0
        matches = 0
        comparison_details = []
        
        for _, bond_row in bond_df.iterrows():
            external_id = str(bond_row['External Security ID']).strip()
            bond_price = bond_row['Price']
            
            # Skip if no valid price in BondAnalyticsResults
            if pd.isna(bond_price):
                continue
            
            try:
                bond_price_float = float(bond_price)
            except (ValueError, TypeError):
                continue
            
            # Check if we have this security in sec_Price.csv
            if external_id in sec_price_map:
                sec_price_float = sec_price_map[external_id]
                total_comparisons += 1
                
                # Compare prices
                is_match = compare_prices(bond_price_float, sec_price_float)
                if is_match:
                    matches += 1
                
                comparison_details.append({
                    'isin': external_id,
                    'bond_price': bond_price_float,
                    'sec_price': sec_price_float,
                    'match': is_match,
                    'difference': abs(bond_price_float - sec_price_float)
                })
        
        # Calculate match percentage
        match_percentage = (matches / total_comparisons * 100) if total_comparisons > 0 else 0
        
        logger.info(f"Price matching results: {matches}/{total_comparisons} matches ({match_percentage:.1f}%)")
        
        # Save historical results if requested
        if save_historical:
            save_historical_results(
                date_string, 
                match_percentage, 
                total_comparisons, 
                matches,
                len(sec_price_map),
                data_folder
            )
        
        # Return results in dashboard format
        return {
            "match_percentage": round(match_percentage, 1),
            "total_comparisons": total_comparisons,
            "matches": matches,
            "total_sec_price_securities": len(sec_price_map),
            "latest_date": date_string or "Unknown",
            "bond_analytics_file": os.path.basename(bond_file_path) if bond_file_path else "Unknown",
            "price_source": price_source,
            "comparison_details": comparison_details[:10]  # Keep only first 10 for dashboard
        }
        
    except Exception as e:
        logger.error(f"Error in price matching check: {e}", exc_info=True)
        return {
            "error": str(e),
            "match_percentage": 0,
            "total_comparisons": 0,
            "matches": 0,
            "latest_date": "Unknown"
        }

def save_historical_results(date_string, match_percentage, total_comparisons, matches, total_sec_price_securities, data_folder):
    """
    Save historical price matching results to CSV file.
    """
    try:
        historical_file = os.path.join(data_folder, HISTORICAL_RESULTS_FILE)
        header = [
            'date', 'match_percentage', 'total_comparisons',
            'matches', 'total_sec_price_securities', 'timestamp'
        ]
        row = [
            date_string,
            round(match_percentage, 1),
            total_comparisons,
            matches,
            total_sec_price_securities,
            datetime.now().isoformat(),
        ]
        append_rows_locked(historical_file, [row], header=header)
        logger.info(f"Historical results saved to {historical_file}")
        
    except Exception as e:
        logger.error(f"Error saving historical results: {e}", exc_info=True)

def get_historical_results(data_folder=DATA_FOLDER):
    """
    Load historical price matching results from CSV file.
    Returns list of dictionaries with historical data.
    """
    try:
        historical_file = os.path.join(data_folder, HISTORICAL_RESULTS_FILE)
        if not os.path.exists(historical_file):
            return []
        
        # Read CSV with explicit dtype for date column to ensure it stays as string
        df = pd.read_csv(historical_file, dtype={'date': str})
        
        # Ensure date column is string format (in case pandas auto-converted)
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str)
        
        return df.to_dict('records')
        
    except Exception as e:
        logger.error(f"Error loading historical results: {e}", exc_info=True)
        return []

def run_manual_check_for_date(target_date, data_folder=DATA_FOLDER, bond_analytics_folder=BOND_ANALYTICS_FOLDER):
    """
    Run price matching check for a specific date.
    target_date should be in YYYYMMDD format.
    """
    try:
        # Find specific file for the date
        filename = f"BondAnalyticsResults_Full_{target_date}_000000.csv"
        file_path = os.path.join(bond_analytics_folder, filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"File not found for date {target_date}: {file_path}")
            return {
                "error": f"BondAnalyticsResults file not found for date {target_date}",
                "match_percentage": 0,
                "total_comparisons": 0,
                "matches": 0,
                "latest_date": target_date
            }
        
        logger.info(f"Running manual check for date {target_date}")
        
        # Run check with specific file and target date
        result = run_price_matching_check(
            data_folder=data_folder, 
            bond_analytics_folder=bond_analytics_folder, 
            save_historical=True,
            specific_file_path=file_path,
            target_date=target_date
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error running manual check for date {target_date}: {e}", exc_info=True)
        return {
            "error": str(e),
            "match_percentage": 0,
            "total_comparisons": 0,
            "matches": 0,
            "latest_date": target_date
        } 