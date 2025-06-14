# views/generic_comparison_helpers.py
# This file contains helper functions for the generic comparison views blueprint.
# It includes functions for calculating statistics, loading holdings data, fund codes,
# applying filters, sorting, and pagination to comparison summary data.

import pandas as pd
import math
import logging
import os
from typing import Optional, List, Tuple, Dict
from flask import current_app, url_for, request
from urllib.parse import urlencode
import config

# Import shared utilities and processing functions
try:
    from utils import (
        load_fund_groups,
        parse_fund_list,
        load_weights_and_held_status,
    )  # Added load_weights
    from security_processing import load_and_process_security_data
    from preprocessing import read_and_sort_dates
except ImportError as e:
    logging.error(f"Error importing modules in generic_comparison_helpers: {e}")
    from ..utils import (
        load_fund_groups,
        parse_fund_list,
        load_weights_and_held_status,
    )  # Added load_weights
    from ..security_processing import load_and_process_security_data
    from ..preprocessing import read_and_sort_dates

# === Stats Calculation Helper ===============================================


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
    log = logging.getLogger(__name__)
    if merged_df.empty:
        log.warning("calculate_generic_comparison_stats received an empty merged_df.")
        return pd.DataFrame()
    if id_col not in merged_df.columns:
        log.error(
            f"Specified id_col '{id_col}' not found in merged_df columns for stats calculation: {merged_df.columns.tolist()}"
        )
        return pd.DataFrame()

    log.info(
        f"Calculating generic comparison statistics using ID column: '{id_col}'..."
    )
    stats_list = []

    for sec_id, group in merged_df.groupby(id_col):
        sec_stats = {id_col: sec_id}

        # Ensure Date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(group["Date"]):
            group["Date"] = pd.to_datetime(group["Date"], errors="coerce")

        # Ensure Value columns are numeric and replace zeros with NaN
        from data_utils import convert_to_numeric_robustly
        group["Value_Orig"] = convert_to_numeric_robustly(group["Value_Orig"])
        group["Value_New"] = convert_to_numeric_robustly(group["Value_New"])

        # Filter for overall date range (where at least one value exists)
        group_valid_overall = group.dropna(
            subset=["Value_Orig", "Value_New"], how="all"
        )
        overall_min_date = group_valid_overall["Date"].min()
        overall_max_date = group_valid_overall["Date"].max()

        # Filter for valid comparison points (where BOTH values exist)
        valid_comparison = group.dropna(subset=["Value_Orig", "Value_New"])

        # 1. Correlation of Levels
        if len(valid_comparison) >= 2:
            level_corr = valid_comparison["Value_Orig"].corr(
                valid_comparison["Value_New"]
            )
            sec_stats["Level_Correlation"] = (
                level_corr if pd.notna(level_corr) else None
            )
        else:
            sec_stats["Level_Correlation"] = None

        # 2. Max / Min (using original group)
        sec_stats["Max_Orig"] = group["Value_Orig"].max()
        sec_stats["Min_Orig"] = group["Value_Orig"].min()
        sec_stats["Max_New"] = group["Value_New"].max()
        sec_stats["Min_New"] = group["Value_New"].min()

        # 3. Date Range Comparison
        min_date_orig_idx = group["Value_Orig"].first_valid_index()
        max_date_orig_idx = group["Value_Orig"].last_valid_index()
        min_date_new_idx = group["Value_New"].first_valid_index()
        max_date_new_idx = group["Value_New"].last_valid_index()

        sec_stats["Start_Date_Orig"] = (
            group.loc[min_date_orig_idx, "Date"]
            if min_date_orig_idx is not None
            else None
        )
        sec_stats["End_Date_Orig"] = (
            group.loc[max_date_orig_idx, "Date"]
            if max_date_orig_idx is not None
            else None
        )
        sec_stats["Start_Date_New"] = (
            group.loc[min_date_new_idx, "Date"]
            if min_date_new_idx is not None
            else None
        )
        sec_stats["End_Date_New"] = (
            group.loc[max_date_new_idx, "Date"]
            if max_date_new_idx is not None
            else None
        )

        same_start = (
            pd.notna(sec_stats["Start_Date_Orig"])
            and pd.notna(sec_stats["Start_Date_New"])
            and pd.Timestamp(sec_stats["Start_Date_Orig"])
            == pd.Timestamp(sec_stats["Start_Date_New"])
        )
        same_end = (
            pd.notna(sec_stats["End_Date_Orig"])
            and pd.notna(sec_stats["End_Date_New"])
            and pd.Timestamp(sec_stats["End_Date_Orig"])
            == pd.Timestamp(sec_stats["End_Date_New"])
        )
        sec_stats["Same_Date_Range"] = same_start and same_end

        # Add overall date range for info
        sec_stats["Overall_Start_Date"] = overall_min_date
        sec_stats["Overall_End_Date"] = overall_max_date

        # 4. Correlation of Daily Changes
        if len(valid_comparison) >= 1:  # Need at least 1 point to calculate diff
            valid_comparison = valid_comparison.copy()  # Avoid SettingWithCopyWarning
            valid_comparison["Change_Orig_Corr"] = valid_comparison["Value_Orig"].diff()
            valid_comparison["Change_New_Corr"] = valid_comparison["Value_New"].diff()

            # Drop NaNs created by the diff() itself and any pre-existing NaNs in changes
            valid_changes = valid_comparison.dropna(
                subset=["Change_Orig_Corr", "Change_New_Corr"]
            )

            if len(valid_changes) >= 2:  # Need 2 pairs of *changes* for correlation
                change_corr = valid_changes["Change_Orig_Corr"].corr(
                    valid_changes["Change_New_Corr"]
                )
                sec_stats["Change_Correlation"] = (
                    change_corr if pd.notna(change_corr) else None
                )
            else:
                sec_stats["Change_Correlation"] = None
                log.debug(
                    f"Cannot calculate Change_Correlation for {sec_id}. Need >= 2 valid change pairs, found {len(valid_changes)}."
                )
        else:
            sec_stats["Change_Correlation"] = None
            log.debug(
                f"Cannot calculate Change_Correlation for {sec_id}. Need >= 1 valid comparison point to calculate diffs, found {len(valid_comparison)}."
            )

        # 5. Difference Statistics (use valid_comparison df)
        if not valid_comparison.empty:
            valid_comparison["Abs_Diff"] = (
                valid_comparison["Value_Orig"] - valid_comparison["Value_New"]
            ).abs()
            sec_stats["Mean_Abs_Diff"] = valid_comparison["Abs_Diff"].mean()
            sec_stats["Max_Abs_Diff"] = valid_comparison["Abs_Diff"].max()
        else:
            sec_stats["Mean_Abs_Diff"] = None
            sec_stats["Max_Abs_Diff"] = None

        # Count NaNs (use original group)
        sec_stats["NaN_Count_Orig"] = group["Value_Orig"].isna().sum()
        sec_stats["NaN_Count_New"] = group["Value_New"].isna().sum()
        sec_stats["Total_Points"] = len(group)

        stats_list.append(sec_stats)

    if not stats_list:
        log.warning("No statistics were generated.")
        return pd.DataFrame()

    summary_df = pd.DataFrame(stats_list)

    # Merge static data back (ensure ID columns match)
    if (
        not static_data.empty
        and id_col in static_data.columns
        and id_col in summary_df.columns
    ):
        # Ensure consistent types before merge if possible
        try:
            if static_data[id_col].dtype != summary_df[id_col].dtype:
                log.warning(
                    f"Attempting merge with different dtypes for ID column '{id_col}': Static ({static_data[id_col].dtype}), Summary ({summary_df[id_col].dtype}). Converting static to summary type."
                )
                static_data[id_col] = static_data[id_col].astype(
                    summary_df[id_col].dtype
                )
        except Exception as e:
            log.warning(
                f"Could not ensure matching dtypes for merge key '{id_col}': {e}"
            )

        summary_df = pd.merge(summary_df, static_data, on=id_col, how="left")
        log.info(
            f"Successfully merged static data back. Summary shape: {summary_df.shape}"
        )
    elif not static_data.empty:
        log.warning(
            f"Could not merge static data. ID column '{id_col}' missing from static_data ({id_col in static_data.columns}) or summary_df ({id_col in summary_df.columns})."
        )

    log.info(
        f"--- Exiting calculate_generic_comparison_stats. Output shape: {summary_df.shape} ---"
    )
    return summary_df


# === Holdings Helper ========================================================


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
    log = logging.getLogger(__name__)
    holdings_file = os.path.join(data_folder, "w_secs.csv")
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
        id_col_holding = config.ISIN_COL  # Assuming this is the standard ID in w_secs
        fund_col_holding = config.FUNDS_COL

        if (
            id_col_holding not in df_holdings.columns
            or fund_col_holding not in df_holdings.columns
        ):
            log.error(
                f"Missing required columns '{id_col_holding}' or '{fund_col_holding}' in {holdings_file}"
            )
            return (
                holdings_data,
                chart_dates,
                f"Missing required columns in {holdings_file}.",
            )

        # Normalize security ID for comparison (e.g., convert to string)
        df_holdings[id_col_holding] = df_holdings[id_col_holding].astype(str)
        security_id_str = str(security_id)

        # Filter for the specific security
        sec_holdings = df_holdings[
            df_holdings[id_col_holding] == security_id_str
        ].copy()

        if sec_holdings.empty:
            log.info(f"Security ID '{security_id_str}' not found in {holdings_file}")
            # Not necessarily an error, just means no holdings data
            return holdings_data, chart_dates, None

        log.info(
            f"Found {len(sec_holdings)} rows for security '{security_id_str}' in w_secs.csv."
        )

        # Prepare chart dates (convert to expected format if needed, assuming 'YYYY-MM-DD')
        # The chart_dates from chart_data['labels'] should already be 'YYYY-MM-DD' strings
        holdings_cols = df_holdings.columns.tolist()

        # Try to match chart dates with columns in w_secs.csv, allowing for format variations
        w_secs_date_map = (
            {}
        )  # Map chart_date ('YYYY-MM-DD') to actual column name in w_secs

        # Attempt to parse w_secs columns as dates
        parsed_cols = {}
        for col in holdings_cols:
            try:
                # Try common formats, prioritise DD/MM/YYYY then YYYY-MM-DD
                parsed_date = pd.to_datetime(col, format="%d/%m/%Y", errors="raise")
                parsed_cols[parsed_date.strftime("%Y-%m-%d")] = col
                continue  # Move to next column if parsed
            except (ValueError, TypeError):
                pass  # Ignore if parsing fails with first format
            try:
                parsed_date = pd.to_datetime(col, format="%Y-%m-%d", errors="raise")
                parsed_cols[parsed_date.strftime("%Y-%m-%d")] = col
                continue
            except (ValueError, TypeError):
                pass  # Ignore other non-date-like columns silently

        log.debug(f"Parsed w_secs columns: {parsed_cols}")

        matched_dates_in_w_secs = []
        unmatched_chart_dates = []

        for chart_date_str in chart_dates:  # Should be 'YYYY-MM-DD'
            if chart_date_str in parsed_cols:
                w_secs_col_name = parsed_cols[chart_date_str]
                w_secs_date_map[chart_date_str] = w_secs_col_name
                matched_dates_in_w_secs.append(w_secs_col_name)
            else:
                # Check if the raw chart_date_str matches any w_secs column directly (less robust)
                if chart_date_str in holdings_cols:
                    w_secs_date_map[chart_date_str] = chart_date_str
                    matched_dates_in_w_secs.append(chart_date_str)
                    log.warning(
                        f"Direct string match used for date: {chart_date_str}. Consider standardizing date formats."
                    )
                else:
                    unmatched_chart_dates.append(chart_date_str)
                    w_secs_date_map[chart_date_str] = None  # Mark as not found

        if unmatched_chart_dates:
            log.warning(
                f"Could not find matching columns in w_secs.csv for chart dates: {unmatched_chart_dates}. These dates will show as 'Not Held'."
            )
            # We don't set error_message here, just log a warning and proceed

        if not matched_dates_in_w_secs:
            log.warning(
                f"No chart dates ({chart_dates}) found as columns in w_secs.csv. Cannot determine holdings."
            )
            return (
                holdings_data,
                chart_dates,
                "No chart dates found in holdings file columns.",
            )

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
                is_held = False  # Default to not held
                if w_secs_col and w_secs_col in fund_row.index:
                    # Check if the value for that date is not null/NaN/empty string AND greater than 0
                    value = fund_row[w_secs_col]
                    # Try converting to numeric, coercing errors to NaN
                    numeric_value = pd.to_numeric(value, errors="coerce")
                    # Check if it's a valid number and greater than 0
                    if pd.notna(numeric_value) and numeric_value > 0:
                        is_held = True
                # else: date not found in w_secs columns or fund_row, or value is NaN/zero/empty, remains False

                held_list.append(is_held)

            holdings_data[fund_code] = held_list

        log.info(
            f"Processed holdings for funds: {list(holdings_data.keys())} for security {security_id_str}"
        )

    except pd.errors.EmptyDataError:
        log.warning(f"Holdings file {holdings_file} is empty.")
        error_message = "Holdings file is empty."
    except KeyError as e:
        log.error(
            f"KeyError processing holdings file {holdings_file} for security {security_id_str}: {e}",
            exc_info=True,
        )
        error_message = f"Missing expected column in holdings file: {e}"
    except Exception as e:
        log.error(
            f"Error processing holdings for security {security_id_str}: {e}",
            exc_info=True,
        )
        error_message = f"An unexpected error occurred processing holdings: {e}"

    return holdings_data, chart_dates, error_message


# === Fund Loading Helper =====================================================


def load_fund_codes_from_csv(data_folder: str) -> list:
    """
    Loads the list of fund codes from FundList.csv in the given data folder.
    Returns a sorted list of fund codes (strings). Returns empty list on error.
    """
    fund_list_path = os.path.join(data_folder, "FundList.csv")
    if not os.path.exists(fund_list_path):
        logging.getLogger(__name__).warning(
            f"FundList.csv not found at {fund_list_path}"
        )
        return []
    try:
        df = pd.read_csv(fund_list_path)
        if config.FUND_CODE_COL in df.columns:
            fund_codes = sorted(
                df[config.FUND_CODE_COL].dropna().astype(str).unique().tolist()
            )
            return fund_codes
        else:
            logging.getLogger(__name__).warning(
                f"'{config.FUND_CODE_COL}' column not found in FundList.csv at {fund_list_path}"
            )
            return []
    except Exception as e:
        logging.getLogger(__name__).error(f"Error loading FundList.csv: {e}")
        return []


# === Filtering Helper ========================================================


def _apply_summary_filters(
    df: pd.DataFrame,
    selected_fund_group: Optional[str],
    show_sold: bool,
    active_filters: dict,
    data_folder: str,
    actual_id_col: str,
    static_cols: List[str],
) -> pd.DataFrame:
    """Apply fund-group, holding-status, and static column filters to the summary DataFrame.

    Args:
        df: The summary DataFrame to be filtered.
        selected_fund_group: Name of the fund group selected by the user (or None).
        show_sold: If False, only include rows where `is_held` is True.
        active_filters: Dict mapping column name → filter value (strings from query).
        data_folder: Path to data folder (used for fund group loading).
        actual_id_col: Name of the security ID column.
        static_cols: List of static column names discovered earlier.

    Returns:
        Filtered DataFrame (copy).
    """
    log = logging.getLogger(__name__)
    filtered = df.copy()

    # --- Fund group filtering -------------------------------------------------
    fund_groups_dict = load_fund_groups(data_folder)
    if selected_fund_group and selected_fund_group in fund_groups_dict:
        allowed_funds = set(fund_groups_dict[selected_fund_group])
        if config.FUNDS_COL in filtered.columns:
            filtered = filtered[
                filtered[config.FUNDS_COL].apply(
                    lambda x: (
                        any(f in allowed_funds for f in parse_fund_list(x))
                        if pd.notna(x)
                        else False
                    )
                )
            ].copy()
        else:
            fund_col_candidates = [
                col
                for col in ["Fund", config.FUND_CODE_COL, config.CODE_COL]
                if col in filtered.columns
            ]
            if fund_col_candidates:
                fc = fund_col_candidates[0]
                filtered = filtered[filtered[fc].isin(allowed_funds)].copy()

    # --- Holding status filter ----------------------------------------------
    if not show_sold and "is_held" in filtered.columns:
        before = len(filtered)
        filtered = filtered[filtered["is_held"] == True].copy()
        log.info("Holding filter applied – kept %s/%s rows", len(filtered), before)

    # --- Static column filters ----------------------------------------------
    if active_filters:
        log.info("Applying static column filters via helper: %s", active_filters)
        for col, value in active_filters.items():
            if col in filtered.columns and value:
                try:
                    if col == "Funds":
                        filtered = filtered[
                            filtered[col].apply(
                                lambda x: (
                                    value in parse_fund_list(x)
                                    if pd.notna(x)
                                    else False
                                )
                            )
                        ].copy()
                    else:
                        filtered = filtered[
                            filtered[col]
                            .astype(str)
                            .str.fullmatch(str(value), case=False, na=False)
                        ].copy()
                except Exception as e:
                    log.warning("Static filter error for %s=%s: %s", col, value, e)

    return filtered


# === Sorting Helper ===========================================================


def _apply_summary_sorting(
    df: pd.DataFrame,
    sort_by: str,
    sort_order: str,
    id_col: str,
) -> Tuple[pd.DataFrame, str, str]:
    """Sort the DataFrame based on a requested column.

    Returns the sorted frame and potentially adjusted sort_by / sort_order that
    were actually applied.
    """
    log = logging.getLogger(__name__)
    ascending = sort_order.lower() == "asc"

    if sort_by not in df.columns:
        log.warning("Sort column '%s' not found. Defaulting to ID sort.", sort_by)
        sort_by = id_col
        ascending = True

    try:
        if pd.api.types.is_numeric_dtype(df[sort_by]):
            from data_utils import convert_to_numeric_robustly
            df[sort_by] = convert_to_numeric_robustly(df[sort_by])
            sorted_df = df.sort_values(
                by=sort_by, ascending=ascending, na_position="last"
            )
        else:
            sorted_df = df.sort_values(
                by=sort_by,
                ascending=ascending,
                na_position="last",
                key=lambda col: col.astype(str).str.lower(),
            )
    except Exception as e:
        log.error("Sorting error on '%s': %s. Falling back to ID sort.", sort_by, e)
        sort_by = id_col
        ascending = True
        sorted_df = df.sort_values(by=id_col, ascending=True, na_position="last")

    new_order = "asc" if ascending else "desc"
    return sorted_df, sort_by, new_order


# === Pagination Helper =======================================================


def _paginate_summary_data(
    df: pd.DataFrame,
    page: int,
    per_page: int,
    page_window: int = 2,
) -> Tuple[pd.DataFrame, Dict]:
    """Paginate the given DataFrame.

    Returns a subset DataFrame and a dictionary with pagination metadata.
    The URL builder logic (`url_for_page`) needs to be added back in the view function,
    as it requires context like `comparison_type` and `request.args`.
    """
    total_items = len(df)
    per_page = max(1, per_page)
    total_pages = math.ceil(total_items / per_page) if total_items else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    paginated_df = df.iloc[start_idx:end_idx]

    start_page_display = max(1, page - page_window)
    end_page_display = min(total_pages, page + page_window)

    context: Dict[str, int | bool] = {
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_num": page - 1,
        "next_num": page + 1,
        "start_page_display": start_page_display,
        "end_page_display": end_page_display,
        # 'url_for_page' needs to be added by the caller (view function)
    }

    return paginated_df, context
