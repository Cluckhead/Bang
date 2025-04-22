# Purpose: Handles loading, preprocessing, and analysis of yield curve data (curves.csv).
# The `load_curve_data` function expects the absolute path to the data folder to be provided.

# Stdlib imports
import os
import re
from datetime import timedelta

# Third-party imports
import pandas as pd
import numpy as np

# Local imports
# Removed: from config import DATA_FOLDER
import logging # Import logging

# Get the logger instance. Assumes Flask app has configured logging.
logger = logging.getLogger(__name__)

# Constants for term conversion
TERM_MULTIPLIERS = {
    'D': 1,
    'W': 7,
    'M': 30,  # Approximate
    'Y': 365 # Approximate
}

def _term_to_days(term_str):
    """Converts a term string (e.g., '7D', '1M', '2Y') to an approximate number of days."""
    if not isinstance(term_str, str):
        return None # Handle non-string inputs
    term_str = term_str.upper()
    match = re.match(r"(\d+)([DWMY])", term_str)
    if match:
        num, unit = match.groups()
        multiplier = TERM_MULTIPLIERS.get(unit)
        if multiplier:
            try:
                return int(num) * multiplier
            except ValueError:
                 logger.warning(f"Could not convert number part '{num}' in term '{term_str}' to integer.")
                 return None
    try:
        # Handle simple integer strings representing days (fallback)
        return int(term_str)
    except ValueError:
        logger.warning(f"Could not parse term '{term_str}' to days.")
        return None # Indicate failure to parse

def load_curve_data(data_folder_path: str):
    """Loads and preprocesses the curve data from 'curves.csv' within the given folder.

    Args:
        data_folder_path (str): The absolute path to the folder containing 'curves.csv'.
                                The caller is responsible for providing the correct path,
                                typically obtained from `current_app.config['DATA_FOLDER']`.

    Returns:
        pd.DataFrame: Processed curve data indexed by [Currency, Date, Term],
                      or an empty DataFrame if loading/processing fails.
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to load_curve_data.")
        return pd.DataFrame()

    file_path = os.path.join(data_folder_path, 'curves.csv')
    logger.info(f"Attempting to load curve data from: {file_path}")

    if not os.path.exists(file_path):
        logger.error(f"Curve data file not found at {file_path}")
        return pd.DataFrame() # Return empty DataFrame

    try:
        # Load without automatic date parsing initially
        df = pd.read_csv(file_path)
        logger.info(f"Successfully loaded {len(df)} rows from {file_path}")

        # Explicitly parse the 'Date' column - robust to different formats
        if 'Date' in df.columns:
            # Specify the exact format to handle YYYY-MM-DDTHH:MM:SS
            df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%dT%H:%M:%S', errors='coerce')
            # Drop rows where date parsing failed
            original_rows_date = len(df)
            df.dropna(subset=['Date'], inplace=True)
            rows_after_date = len(df)
            if original_rows_date > rows_after_date:
                logger.warning(f"Dropped {original_rows_date - rows_after_date} rows due to unparseable 'Date'.")
        else:
            logger.error(f"Critical: 'Date' column not found in {file_path}")
            return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error reading curve data CSV '{file_path}': {e}", exc_info=True)
        return pd.DataFrame()

    # Rename columns for consistency if necessary (adjust based on actual CSV)
    rename_map = {'Currency Code': 'Currency', 'Daily Value': 'Value'}
    df.rename(columns=rename_map, inplace=True)
    logger.debug(f"Renamed columns: {rename_map}")


    # Convert Term to days for sorting and plotting
    df['TermDays'] = df['Term'].apply(_term_to_days)
    logger.debug("Applied _term_to_days conversion.")


    # Convert Value to numeric first
    original_rows = len(df)
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    rows_after_numeric = len(df.dropna(subset=['Value']))
    if original_rows > rows_after_numeric:
         logger.warning(f"Dropped {original_rows - rows_after_numeric} rows due to non-numeric 'Value'.")
    df.dropna(subset=['Value'], inplace=True)

    # Drop rows where term conversion failed
    original_rows = len(df)
    rows_after_term = len(df.dropna(subset=['TermDays']))
    if original_rows > rows_after_term:
         logger.warning(f"Dropped {original_rows - rows_after_term} rows due to unparseable 'Term'.")
    df.dropna(subset=['TermDays'], inplace=True)


    if df.empty:
         logger.warning("DataFrame is empty after initial processing and dropping NaNs.")
         return df # Return empty if all rows were dropped

    # Set index and sort
    try:
        df.sort_values(by=['Currency', 'Date', 'TermDays'], inplace=True)
        # Use MultiIndex for efficient lookups
        df.set_index(['Currency', 'Date', 'Term'], inplace=True)
        logger.info(f"Curve data processed. Final shape: {df.shape}")
    except KeyError as e:
         logger.error(f"Missing expected column for sorting/indexing: {e}. Columns present: {df.columns.tolist()}")
         return pd.DataFrame() # Return empty on structure error
    except Exception as e:
         logger.error(f"Unexpected error during sorting/indexing: {e}", exc_info=True)
         return pd.DataFrame()


    return df

def get_latest_curve_date(df):
    """Gets the most recent date in the DataFrame's index."""
    if df.empty or 'Date' not in df.index.names:
        logger.warning("Cannot get latest date: DataFrame is empty or 'Date' is not in the index.")
        return None
    try:
        latest_date = df.index.get_level_values('Date').max()
        logger.debug(f"Latest date found: {latest_date}")
        return latest_date
    except Exception as e:
         logger.error(f"Error getting latest date from index: {e}", exc_info=True)
         return None


def check_curve_inconsistencies(df):
    """
    Checks for inconsistencies in yield curves compared to the previous day.
    Returns a dictionary summarizing potential issues for the latest date.
    """
    if df.empty:
        logger.warning("Skipping inconsistency check: Input DataFrame is empty.")
        return {}

    latest_date = get_latest_curve_date(df)
    if not latest_date:
        logger.warning("Skipping inconsistency check: Could not determine latest date.")
        return {}

    logger.info(f"Checking inconsistencies for latest date: {latest_date.strftime('%Y-%m-%d')}")

    # Find the previous available date
    try:
        all_dates = df.index.get_level_values('Date').unique()
        available_dates = sorted(all_dates, reverse=True)
        previous_date = None
        if len(available_dates) > 1:
            # Use get_loc for robust index finding
            latest_date_pos = available_dates.get_loc(latest_date)
            if latest_date_pos + 1 < len(available_dates):
                previous_date = available_dates[latest_date_pos + 1]
                logger.info(f"Previous date found for comparison: {previous_date.strftime('%Y-%m-%d')}")
            else:
                logger.info("Latest date is the only date available. Cannot compare change profile.")
        else:
            logger.info("Only one date available. Cannot compare change profile.")
    except Exception as e:
        logger.error(f"Error determining previous date: {e}", exc_info=True)
        previous_date = None

    summary = {}
    currencies = df.index.get_level_values('Currency').unique()
    logger.debug(f"Checking currencies: {currencies.tolist()}")

    for currency in currencies:
        try:
            # --- Get Latest Curve Data (Safer Filtering) ---
            logger.debug(f"Attempting to filter latest data for {currency} on {latest_date.strftime('%Y-%m-%d')}")
            latest_mask = (df.index.get_level_values('Currency') == currency) & \
                          (df.index.get_level_values('Date') == latest_date)
            latest_curve_filtered = df[latest_mask]

            if latest_curve_filtered.empty:
                logger.warning(f"No latest data found for {currency} on {latest_date.strftime('%Y-%m-%d')} using boolean mask.")
                summary.setdefault(currency, []).append("Missing latest data")
                continue

            latest_curve = latest_curve_filtered.reset_index().sort_values('TermDays')
            logger.debug(f"Successfully filtered latest data for {currency}. Shape: {latest_curve.shape}")

            # --- Basic Check 1: Monotonicity ---
            diffs = latest_curve['Value'].diff()
            large_drops = diffs[diffs < -0.5]
            if not large_drops.empty:
                terms = latest_curve.loc[large_drops.index, 'Term'].tolist()
                issue_msg = f"Potential non-monotonic drop(s) < -0.5 between terms near: {terms} on {latest_date.strftime('%Y-%m-%d')}"
                summary.setdefault(currency, []).append(issue_msg)
                logger.warning(f"{currency}: {issue_msg}")

            # --- Check 2: Compare change shape with previous day ---
            if previous_date:
                logger.debug(f"Attempting to filter previous data for {currency} on {previous_date.strftime('%Y-%m-%d')}")
                prev_mask = (df.index.get_level_values('Currency') == currency) & \
                            (df.index.get_level_values('Date') == previous_date)
                previous_curve_filtered = df[prev_mask]

                if previous_curve_filtered.empty:
                    logger.warning(f"No previous day data ({previous_date.strftime('%Y-%m-%d')}) found for {currency} using boolean mask.")
                    summary.setdefault(currency, []).append("Missing previous data for comparison")
                else:
                    previous_curve = previous_curve_filtered.reset_index().sort_values('TermDays')
                    logger.debug(f"Successfully filtered previous data for {currency}. Shape: {previous_curve.shape}")

                    merged = pd.merge(
                        latest_curve[['Term', 'TermDays', 'Value']],
                        previous_curve[['Term', 'TermDays', 'Value']],
                        on='TermDays',
                        suffixes=('_latest', '_prev'),
                        how='inner'
                    )

                    if merged.empty:
                        logger.warning(f"No common terms found between dates for {currency}.")
                    else:
                        merged['ValueChange'] = merged['Value_latest'] - merged['Value_prev']
                        merged.sort_values('TermDays', inplace=True)
                        merged['ChangeDiff'] = merged['ValueChange'].diff()

                        change_diff_std = merged['ChangeDiff'].std()
                        change_diff_mean = merged['ChangeDiff'].mean()
                        threshold_std = np.nan_to_num(change_diff_mean + 3 * change_diff_std)
                        threshold_abs = 0.2
                        final_threshold = max(abs(threshold_std), threshold_abs)
                        anomalous_jumps = merged[abs(merged['ChangeDiff'].fillna(0)) > final_threshold]

                        if not anomalous_jumps.empty:
                            anomalous_terms = anomalous_jumps['Term_latest'].tolist()
                            issue_msg = f"Anomalous change profile jump vs {previous_date.strftime('%Y-%m-%d')} near terms: {anomalous_terms}"
                            summary.setdefault(currency, []).append(issue_msg)
                            logger.warning(f"{currency}: {issue_msg}")

            if currency not in summary:
                summary[currency] = ["OK"]
                logger.info(f"{currency}: Checks passed.")

        except pd.errors.InvalidIndexError as e:
            logger.error(f"InvalidIndexError processing curve for {currency}: {e}", exc_info=True)
            summary.setdefault(currency, []).append(f"Processing error (InvalidIndexError)")
        except KeyError as e:
            logger.error(f"KeyError processing curve for {currency}: {e}", exc_info=True)
            summary.setdefault(currency, []).append(f"Processing error (KeyError)")
        except Exception as e:
            logger.error(f"Unexpected error processing curve for {currency}: {e}", exc_info=True)
            summary.setdefault(currency, []).append(f"Processing error: {type(e).__name__}")

    logger.info("Finished inconsistency checks.")
    return summary


if __name__ == '__main__':
    # Example usage when run directly:
    logger.info("Running curve_processing.py directly...")
    logger.info("--- Starting Standalone Execution ---")

    logger.info("Loading curve data...")
    curve_df = load_curve_data()

    if not curve_df.empty:
        logger.info("\nCurve data loaded successfully.")
        latest_dt = get_latest_curve_date(curve_df)
        logger.info(f"\nLatest Date found: {latest_dt.strftime('%Y-%m-%d') if latest_dt else 'N/A'}")

        logger.info("\nChecking for inconsistencies on latest date...")
        inconsistency_summary = check_curve_inconsistencies(curve_df)

        logger.info("\n--- Inconsistency Summary ---")
        if inconsistency_summary:
            for currency, issues in inconsistency_summary.items():
                logger.info(f"  {currency}: {', '.join(issues)}")
        else:
            logger.info("  No inconsistencies detected or data was insufficient for checks.")

        # Example: Get data for a specific currency and date
        if latest_dt:
            test_currency = 'USD'
            try:
                # Use .loc with pd.IndexSlice for clarity
                idx = pd.IndexSlice
                usd_latest = curve_df.loc[idx[test_currency, latest_dt, :]]
                # Reset index to get TermDays as a column for printing
                logger.info(f"\n{test_currency} Curve on latest date ({latest_dt.strftime('%Y-%m-%d')}):\n" + usd_latest.reset_index()[['Term', 'TermDays', 'Value']].sort_values('TermDays').to_string())
            except KeyError:
                logger.warning(f"\n{test_currency} data not found for the latest date.")
            except Exception as e:
                logger.error(f"\nError retrieving {test_currency} data: {e}")

    else:
        logger.error("\nFailed to load or process curve data.")

    logger.info("--- Finished Standalone Execution ---") 