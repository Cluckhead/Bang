# views/comparison_helpers.py
# Purpose: Provides reusable helper functions for loading, merging, and analyzing comparison data
# (e.g., spread, duration) for the Simple Data Checker app. These helpers are used by comparison view modules
# to support summary and detail pages, including statistics calculation, holdings lookup, and fund code loading.
# This module is Flask-agnostic and uses standard logging.

import pandas as pd
import math
import logging
import os

from utils import load_weights_and_held_status, parse_fund_list
from security_processing import load_and_process_security_data


def load_generic_comparison_data(data_folder_path: str, file1: str, file2: str):
    """
    Loads, processes, and merges data from two specified security data files.
    Args:
        data_folder_path (str): The absolute path to the data folder.
        file1 (str): Filename for the first dataset (e.g., 'original').
        file2 (str): Filename for the second dataset (e.g., 'new' or 'comparison').
    Returns:
        tuple: (merged_df, static_data, common_static_cols, id_col_name)
               Returns (pd.DataFrame(), pd.DataFrame(), [], None) on error or if files are empty.
    """
    log = logging.getLogger(__name__)
    log.info(f"--- Entering load_generic_comparison_data: {file1}, {file2} ---")

    if not data_folder_path:
        log.error("No data_folder_path provided to load_generic_comparison_data.")
        return pd.DataFrame(), pd.DataFrame(), [], None

    try:
        df1, static_cols1 = load_and_process_security_data(file1, data_folder_path)
        df2, static_cols2 = load_and_process_security_data(file2, data_folder_path)

        if df1.empty or df2.empty:
            log.warning(
                f"One or both dataframes are empty after loading. File1 ({file1}) empty: {df1.empty}, File2 ({file2}) empty: {df2.empty}"
            )
            return pd.DataFrame(), pd.DataFrame(), [], None

        if df1.index.nlevels != 2 or df2.index.nlevels != 2:
            log.error(
                f"One or both dataframes ({file1}, {file2}) do not have the expected 2 index levels after loading."
            )
            return pd.DataFrame(), pd.DataFrame(), [], None

        date_level_name, id_level_name = df1.index.names
        log.info(
            f"Data index levels identified for {file1}/{file2}: Date='{date_level_name}', ID='{id_level_name}'"
        )

        df1 = df1.reset_index()
        df2 = df2.reset_index()
        log.debug(f"Columns after reset for {file1}: {df1.columns.tolist()}")
        log.debug(f"Columns after reset for {file2}: {df2.columns.tolist()}")

        required_cols = [id_level_name, date_level_name, "Value"]
        missing_cols_df1 = [col for col in required_cols if col not in df1.columns]
        missing_cols_df2 = [col for col in required_cols if col not in df2.columns]

        if missing_cols_df1 or missing_cols_df2:
            log.error(
                f"Missing required columns after index reset. Df1 ({file1}) missing: {missing_cols_df1}, Df2 ({file2}) missing: {missing_cols_df2}"
            )
            return pd.DataFrame(), pd.DataFrame(), [], None

        common_static_cols = list(set(static_cols1) & set(static_cols2))
        if id_level_name in common_static_cols:
            common_static_cols.remove(id_level_name)
        if "Value" in common_static_cols:
            common_static_cols.remove("Value")
        log.debug(f"Common static columns identified: {common_static_cols}")

        try:
            df1_merge = df1[
                [id_level_name, date_level_name, "Value"] + common_static_cols
            ].rename(columns={"Value": "Value_Orig"})
            df2_merge = df2[[id_level_name, date_level_name, "Value"]].rename(
                columns={"Value": "Value_New"}
            )
        except KeyError as e:
            log.error(
                f"KeyError during merge preparation using names '{id_level_name}', '{date_level_name}': {e}. Df1 cols: {df1.columns.tolist()}, Df2 cols: {df2.columns.tolist()}"
            )
            return pd.DataFrame(), pd.DataFrame(), [], None

        merged_df = pd.merge(
            df1_merge, df2_merge, on=[id_level_name, date_level_name], how="outer"
        )
        merged_df = merged_df.sort_values(by=[id_level_name, date_level_name])
        merged_df["Change_Orig"] = merged_df.groupby(id_level_name)["Value_Orig"].diff()
        merged_df["Change_New"] = merged_df.groupby(id_level_name)["Value_New"].diff()

        if common_static_cols:
            static_data = (
                merged_df.groupby(id_level_name)[common_static_cols]
                .last()
                .reset_index()
            )
        else:
            static_data = pd.DataFrame(
                {id_level_name: merged_df[id_level_name].unique()}
            )
            log.info("No common static columns found between the two files.")

        log.info(
            f"Successfully merged data for {file1}/{file2}. Shape: {merged_df.shape}"
        )
        log.info(
            f"--- Exiting load_generic_comparison_data. Merged shape: {merged_df.shape}. ID col: {id_level_name} ---"
        )
        return merged_df, static_data, common_static_cols, id_level_name

    except FileNotFoundError as e:
        log.error(f"File not found during comparison data load: {e}")
        return pd.DataFrame(), pd.DataFrame(), [], None
    except Exception as e:
        log.error(
            f"Error loading or processing generic comparison data ({file1}, {file2}): {e}",
            exc_info=True,
        )
        return pd.DataFrame(), pd.DataFrame(), [], None


def calculate_generic_comparison_stats(merged_df, static_data, id_col):
    """
    Calculates comparison statistics for each security. Generic version adaptable to different comparison types.
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
        if not pd.api.types.is_datetime64_any_dtype(group["Date"]):
            group["Date"] = pd.to_datetime(group["Date"], errors="coerce")
        group["Value_Orig"] = pd.to_numeric(group["Value_Orig"], errors="coerce")
        group["Value_New"] = pd.to_numeric(group["Value_New"], errors="coerce")
        group_valid_overall = group.dropna(
            subset=["Value_Orig", "Value_New"], how="all"
        )
        overall_min_date = group_valid_overall["Date"].min()
        overall_max_date = group_valid_overall["Date"].max()
        valid_comparison = group.dropna(subset=["Value_Orig", "Value_New"])
        if len(valid_comparison) >= 2:
            level_corr = valid_comparison["Value_Orig"].corr(
                valid_comparison["Value_New"]
            )
            sec_stats["Level_Correlation"] = (
                level_corr if pd.notna(level_corr) else None
            )
        else:
            sec_stats["Level_Correlation"] = None
        sec_stats["Max_Orig"] = group["Value_Orig"].max()
        sec_stats["Min_Orig"] = group["Value_Orig"].min()
        sec_stats["Max_New"] = group["Value_New"].max()
        sec_stats["Min_New"] = group["Value_New"].min()
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
        sec_stats["Overall_Start_Date"] = overall_min_date
        sec_stats["Overall_End_Date"] = overall_max_date
        if len(valid_comparison) >= 1:
            valid_comparison = valid_comparison.copy()
            valid_comparison["Change_Orig_Corr"] = valid_comparison["Value_Orig"].diff()
            valid_comparison["Change_New_Corr"] = valid_comparison["Value_New"].diff()
            valid_changes = valid_comparison.dropna(
                subset=["Change_Orig_Corr", "Change_New_Corr"]
            )
            if len(valid_changes) >= 2:
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
        if not valid_comparison.empty:
            valid_comparison["Abs_Diff"] = (
                valid_comparison["Value_Orig"] - valid_comparison["Value_New"]
            ).abs()
            sec_stats["Mean_Abs_Diff"] = valid_comparison["Abs_Diff"].mean()
            sec_stats["Max_Abs_Diff"] = valid_comparison["Abs_Diff"].max()
        else:
            sec_stats["Mean_Abs_Diff"] = None
            sec_stats["Max_Abs_Diff"] = None
        sec_stats["NaN_Count_Orig"] = group["Value_Orig"].isna().sum()
        sec_stats["NaN_Count_New"] = group["Value_New"].isna().sum()
        sec_stats["Total_Points"] = len(group)
        stats_list.append(sec_stats)
    if not stats_list:
        log.warning("No statistics were generated.")
        return pd.DataFrame()
    summary_df = pd.DataFrame(stats_list)
    if (
        not static_data.empty
        and id_col in static_data.columns
        and id_col in summary_df.columns
    ):
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
        df_holdings = pd.read_csv(holdings_file, low_memory=False)
        log.info(f"Loaded w_secs.csv with columns: {df_holdings.columns.tolist()}")
        id_col_holding = "ISIN"
        fund_col_holding = "Funds"
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
        df_holdings[id_col_holding] = df_holdings[id_col_holding].astype(str)
        security_id_str = str(security_id)
        sec_holdings = df_holdings[
            df_holdings[id_col_holding] == security_id_str
        ].copy()
        if sec_holdings.empty:
            log.info(f"Security ID '{security_id_str}' not found in {holdings_file}")
            return holdings_data, chart_dates, None
        log.info(
            f"Found {len(sec_holdings)} rows for security '{security_id_str}' in w_secs.csv."
        )
        holdings_cols = df_holdings.columns.tolist()
        w_secs_date_map = {}
        parsed_cols = {}
        for col in holdings_cols:
            try:
                parsed_date = pd.to_datetime(col, format="%d/%m/%Y", errors="raise")
                parsed_cols[parsed_date.strftime("%Y-%m-%d")] = col
                continue
            except (ValueError, TypeError):
                pass
            try:
                parsed_date = pd.to_datetime(col, format="%Y-%m-%d", errors="raise")
                parsed_cols[parsed_date.strftime("%Y-%m-%d")] = col
                continue
            except (ValueError, TypeError):
                pass
        log.debug(f"Parsed w_secs columns: {parsed_cols}")
        matched_dates_in_w_secs = []
        unmatched_chart_dates = []
        for chart_date_str in chart_dates:
            if chart_date_str in parsed_cols:
                w_secs_col_name = parsed_cols[chart_date_str]
                w_secs_date_map[chart_date_str] = w_secs_col_name
                matched_dates_in_w_secs.append(w_secs_col_name)
            else:
                if chart_date_str in holdings_cols:
                    w_secs_date_map[chart_date_str] = chart_date_str
                    matched_dates_in_w_secs.append(chart_date_str)
                    log.warning(
                        f"Direct string match used for date: {chart_date_str}. Consider standardizing date formats."
                    )
                else:
                    unmatched_chart_dates.append(chart_date_str)
                    w_secs_date_map[chart_date_str] = None
        if unmatched_chart_dates:
            log.warning(
                f"Could not find matching columns in w_secs.csv for chart dates: {unmatched_chart_dates}. These dates will show as 'Not Held'."
            )
        if not matched_dates_in_w_secs:
            log.warning(
                f"No chart dates ({chart_dates}) found as columns in w_secs.csv. Cannot determine holdings."
            )
            return (
                holdings_data,
                chart_dates,
                "No chart dates found in holdings file columns.",
            )
        for fund_code, fund_group in sec_holdings.groupby(fund_col_holding):
            if fund_group.empty:
                continue
            fund_row = fund_group.iloc[0]
            held_list = []
            for chart_date_str in chart_dates:
                w_secs_col = w_secs_date_map.get(chart_date_str)
                is_held = False
                if w_secs_col and w_secs_col in fund_row.index:
                    value = fund_row[w_secs_col]
                    numeric_value = pd.to_numeric(value, errors="coerce")
                    if pd.notna(numeric_value) and numeric_value > 0:
                        is_held = True
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
        if "Fund Code" in df.columns:
            fund_codes = sorted(df["Fund Code"].dropna().astype(str).unique().tolist())
            return fund_codes
        else:
            logging.getLogger(__name__).warning(
                f"'Fund Code' column not found in FundList.csv at {fund_list_path}"
            )
            return []
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error loading FundList.csv at {fund_list_path}: {e}"
        )
        return []
