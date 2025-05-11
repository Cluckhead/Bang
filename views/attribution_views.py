# Purpose: Defines the Attribution summary, charts, radar, and security-level views for the Simple Data Checker app.
# This blueprint provides pages that load per-fund attribution files (att_factors_<FUNDCODE>.csv) and display residuals
# and factor breakdowns for Benchmark and Portfolio, with both Prod and S&P columns. If the file for a fund does not exist,
# a user-friendly message is shown. Default fund is the first available alphabetically. See comments in each endpoint.
#
# Features:
# - Attribution summary, radar, and security-level views
# - Handles L0, L1, and L2 factor breakdowns for both Portfolio and Benchmark
# - Loads and merges static security info from w_secs.csv
# - Supports filtering by fund, date, characteristic, and more
# - Used by Flask Blueprint 'attribution_bp'
#
# Each endpoint is heavily commented for clarity. See function docstrings for details.

from flask import (
    Blueprint,
    render_template,
    current_app,
    request,
    jsonify,
    url_for,
    Response,
)
import pandas as pd
import os
import json
from utils import _is_date_like
from .attribution_processing import (
    sum_l2s_block,
    sum_l1s_block,
    compute_residual_block,
    calc_residual,
    norm,
)
import typing
from typing import Any, Dict, List, Optional
import config
from .security_helpers import load_filter_and_extract

attribution_bp = Blueprint("attribution_bp", __name__, url_prefix="/attribution")

# Load attribution column config from YAML (prefixes, factors, etc.)
ATTR_COLS = config.ATTRIBUTION_COLUMNS_CONFIG

# ------------------------------------------------------------
# Helper functions for JSON serialization of pandas/numpy types
# These are defined at module level so they are available to all
# views without risk of scope issues.
# ------------------------------------------------------------

def to_native(val):
    """Convert numpy/pandas scalar types to native Python types for JSON serialization."""
    try:
        import numpy as np  # Local import to avoid mandatory dependency at module load
        if isinstance(val, (np.generic,)):
            return val.item()
    except ImportError:
        pass  # numpy not installed, ignore
    if hasattr(val, "item"):
        return val.item()
    return val


def convert_dict(obj):
    """Recursively convert dict/list structures to JSON-safe native Python types.

    In addition to converting numpy / pandas scalar types, we also make sure that
    any NaN or infinite values are replaced with ``None`` so that the resulting
    JSON is valid (JavaScript's ``JSON.parse`` does **not** accept NaN/Infinity).
    """

    # Containers – recurse first
    if isinstance(obj, dict):
        return {k: convert_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_dict(v) for v in obj]

    # Scalar – convert numpy / pandas scalars to native Python types first
    native_val = to_native(obj)

    # Replace NaN / ±Inf with None so that ``json.dumps`` emits ``null``
    import math
    if isinstance(native_val, (float, int)) and not math.isfinite(native_val):
        return None

    return native_val

# ------------- END helper functions -------------------------

# Utility: Get available funds from FundList.csv (preferred) or w_secs.csv fallback
def get_available_funds(data_folder: str) -> list:
    """
    Returns a sorted list of available fund codes by scanning the data_folder for 'att_factors_<FUNDCODE>.csv' files.
    """
    # This function scans the specified data directory to find all attribution factor files.
    # It assumes a naming convention of 'att_factors_FUNDCODE.csv'.
    # The 'FUNDCODE' part is extracted and returned as a unique, sorted list.
    # This ensures that the fund dropdown in the UI only shows funds for which data actually exists.
    fund_codes = set()
    try:
        for filename in os.listdir(data_folder):
            if filename.startswith("att_factors_") and filename.endswith(".csv"):
                # Extract fund code: "att_factors_" is 12 chars, ".csv" is 4 chars
                fund_code = filename[12:-4]
                if fund_code: # Ensure fund_code is not empty
                    fund_codes.add(fund_code)
    except FileNotFoundError:
        # If the data_folder doesn't exist, return an empty list.
        # This can happen during initial setup or if the configuration is wrong.
        current_app.logger.warning(f"Data folder not found: {data_folder} when trying to list available funds.")
        return []
    except Exception as e:
        # Log other potential errors during file listing or processing.
        current_app.logger.error(f"Error scanning for fund files in {data_folder}: {e}")
        return []
    return sorted(list(fund_codes))


@attribution_bp.route("/summary")
def attribution_summary() -> Response:
    """
    Loads att_factors_<FUNDCODE>.csv for the selected fund and computes residuals for each day for Benchmark and Portfolio.
    If the file does not exist, shows a user-friendly message. Default fund is the first available alphabetically.
    """
    data_folder = current_app.config["DATA_FOLDER"]
    available_funds = get_available_funds(data_folder)
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    file_path = os.path.join(data_folder, f"att_factors_{selected_fund}.csv")
    if not selected_fund or not os.path.exists(file_path):
        return render_template(
            "attribution_summary.html",
            benchmark_results=[],
            portfolio_results=[],
            available_funds=available_funds,
            selected_fund=selected_fund,
            min_date=None,
            max_date=None,
            start_date=None,
            end_date=None,
            available_characteristics=[],
            selected_characteristic=None,
            selected_level="L0",
            available_characteristic_values=[],
            selected_characteristic_value=None,
            no_data_message="No attribution available.",
        )

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()  # Remove accidental spaces
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Fund"])

    # --- Load w_secs.csv and extract static characteristics ---
    wsecs_path = os.path.join(data_folder, "w_secs.csv")
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [
        col for col in wsecs.columns if col not in ["ISIN"] and not _is_date_like(col)
    ]
    wsecs_static = wsecs.drop_duplicates(subset=["ISIN"])[["ISIN"] + static_cols]

    # --- Characteristic selection ---
    available_characteristics = static_cols
    # Only set selected_characteristic if user selects it; otherwise, default to None (no group by)
    selected_characteristic = request.args.get(
        "characteristic", default=None, type=str
    )
    # If the selected characteristic is not valid, set to None
    if not selected_characteristic or selected_characteristic not in available_characteristics:
        selected_characteristic = None

    # Join att_factors with w_secs static info
    df = df.merge(wsecs_static, on="ISIN", how="left")

    # Get date range for UI
    min_date = df["Date"].min()
    max_date = df["Date"].max()

    # Get filter parameters from query string
    start_date_str = request.args.get("start_date", default=None, type=str)
    end_date_str = request.args.get("end_date", default=None, type=str)
    selected_level = request.args.get("level", default="L0", type=str)
    selected_characteristic_value = request.args.get(
        "characteristic_value", default="", type=str
    )

    # Parse date range
    start_date = (
        pd.to_datetime(start_date_str, errors="coerce") if start_date_str else min_date
    )
    end_date = (
        pd.to_datetime(end_date_str, errors="coerce") if end_date_str else max_date
    )

    # Use L1 and L2 groupings from config
    l1_groups = config.ATTRIBUTION_L1_GROUPS
    l2_all = sum(config.ATTRIBUTION_L2_GROUPS.values(), [])
    # Attribution column prefixes from config
    pfx_bench = ATTR_COLS['prefixes']['bench']
    pfx_prod = ATTR_COLS['prefixes']['prod']
    pfx_sp_bench = ATTR_COLS['prefixes']['sp_bench']
    pfx_sp_prod = ATTR_COLS['prefixes']['sp_prod']
    l0_bench = ATTR_COLS['prefixes']['l0_bench']
    l0_prod = ATTR_COLS['prefixes']['l0_prod']

    # Prepare results: group by Date, Fund, and selected characteristic
    group_cols = ["Date", "Fund"]
    if selected_characteristic:
        group_cols.append(selected_characteristic)
    benchmark_results = []
    portfolio_results = []

    # Compute available values for the selected characteristic
    if selected_characteristic:
        available_characteristic_values = sorted(
            df[selected_characteristic].dropna().unique()
        )
    else:
        available_characteristic_values = []

    for group_keys, group in df.groupby(group_cols):
        if selected_characteristic:
            date, fund, char_val = group_keys
        else:
            date, fund = group_keys
            char_val = None
        if not (start_date <= date <= end_date):
            continue
        if selected_characteristic and selected_characteristic_value:
            if char_val != selected_characteristic_value:
                continue
        # L0: Residuals and Abs Residuals
        if selected_level == "L0" or not selected_level:
            bench_prod_res = group.apply(
                lambda row: calc_residual(
                    row, l0_bench, pfx_bench, l2_all
                ),
                axis=1,
            )
            bench_sp_res = group.apply(
                lambda row: calc_residual(
                    row, l0_bench, pfx_sp_bench, l2_all
                ),
                axis=1,
            )
            port_prod_res = group.apply(
                lambda row: calc_residual(
                    row, l0_prod, pfx_prod, l2_all
                ),
                axis=1,
            )
            port_sp_res = group.apply(
                lambda row: calc_residual(
                    row, l0_prod, pfx_sp_prod, l2_all
                ),
                axis=1,
            )
            bench_prod = bench_prod_res.sum()
            bench_sp = bench_sp_res.sum()
            port_prod = port_prod_res.sum()
            port_sp = port_sp_res.sum()
            bench_prod_abs = bench_prod_res.abs().sum()
            bench_sp_abs = bench_sp_res.abs().sum()
            port_prod_abs = port_prod_res.abs().sum()
            port_sp_abs = port_sp_res.abs().sum()
            row_info_bench = {
                "Date": date,
                "Fund": selected_fund,
                "Residual_Prod": bench_prod,
                "Residual_SP": bench_sp,
                "AbsResidual_Prod": bench_prod_abs,
                "AbsResidual_SP": bench_sp_abs,
            }
            row_info_port = {
                "Date": date,
                "Fund": selected_fund,
                "Residual_Prod": port_prod,
                "Residual_SP": port_sp,
                "AbsResidual_Prod": port_prod_abs,
                "AbsResidual_SP": port_sp_abs,
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)
        # L1: Show L1 Rates, Credit, FX (Prod and S&P)
        elif selected_level == "L1":
            bench_l1_prod = sum_l1s_block(group, pfx_bench, l1_groups)
            bench_l1_sp = sum_l1s_block(group, pfx_sp_bench, l1_groups)
            port_l1_prod = sum_l1s_block(group, pfx_prod, l1_groups)
            port_l1_sp = sum_l1s_block(group, pfx_sp_prod, l1_groups)
            row_info_bench = {
                "Date": date,
                "Fund": selected_fund,
                "L1Rates_Prod": bench_l1_prod[0],
                "L1Rates_SP": bench_l1_sp[0],
                "L1Credit_Prod": bench_l1_prod[1],
                "L1Credit_SP": bench_l1_sp[1],
                "L1FX_Prod": bench_l1_prod[2],
                "L1FX_SP": bench_l1_sp[2],
            }
            row_info_port = {
                "Date": date,
                "Fund": selected_fund,
                "L1Rates_Prod": port_l1_prod[0],
                "L1Rates_SP": port_l1_sp[0],
                "L1Credit_Prod": port_l1_prod[1],
                "L1Credit_SP": port_l1_sp[1],
                "L1FX_Prod": port_l1_prod[2],
                "L1FX_SP": port_l1_sp[2],
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)
        # L2: Show all L2 values (Prod and S&P) side by side
        elif selected_level == "L2":
            l2prod = dict(zip(l2_all, sum_l2s_block(group, pfx_bench, l2_all)))
            l2sp = dict(zip(l2_all, sum_l2s_block(group, pfx_sp_bench, l2_all)))
            l2prod_port = dict(zip(l2_all, sum_l2s_block(group, pfx_prod, l2_all)))
            l2sp_port = dict(zip(l2_all, sum_l2s_block(group, pfx_sp_prod, l2_all)))
            row_info_bench = {
                "Date": date,
                "Fund": selected_fund,
                "L2Prod": l2prod,
                "L2SP": l2sp,
                "L2ProdKeys": l2_all,
            }
            row_info_port = {
                "Date": date,
                "Fund": selected_fund,
                "L2Prod": l2prod_port,
                "L2SP": l2sp_port,
                "L2ProdKeys": l2_all,
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)

    # Sort
    benchmark_results = sorted(
        benchmark_results,
        key=lambda x: (x["Date"], x["Fund"], x.get(selected_characteristic, "")),
    )
    portfolio_results = sorted(
        portfolio_results,
        key=lambda x: (x["Date"], x["Fund"], x.get(selected_characteristic, "")),
    )

    return render_template(
        "attribution_summary.html",
        benchmark_results=benchmark_results,
        portfolio_results=portfolio_results,
        available_funds=available_funds,
        selected_fund=selected_fund,
        min_date=min_date,
        max_date=max_date,
        start_date=start_date,
        end_date=end_date,
        available_characteristics=available_characteristics,
        selected_characteristic=selected_characteristic,
        selected_level=selected_level,
        available_characteristic_values=available_characteristic_values,
        selected_characteristic_value=selected_characteristic_value,
    )


@attribution_bp.route("/charts")
def attribution_charts() -> Response:
    """
    Attribution Residuals Chart Page: Shows residuals over time for Benchmark and Portfolio (Prod and S&P),
    with filters and grouping as in the summary view. Data is prepared for JS charts.
    """
    data_folder = current_app.config["DATA_FOLDER"]
    available_funds = get_available_funds(data_folder)
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    file_path = os.path.join(data_folder, f"att_factors_{selected_fund}.csv")
    if not selected_fund or not os.path.exists(file_path):
        return render_template(
            "attribution_charts.html",
            chart_data_bench_json="[]",
            chart_data_port_json="[]",
            available_funds=available_funds,
            selected_fund=selected_fund,
            min_date=None,
            max_date=None,
            start_date=None,
            end_date=None,
            available_characteristics=[],
            selected_characteristic=None,
            available_characteristic_values=[],
            selected_characteristic_value=None,
            abs_toggle_default=False,
            no_data_message="No attribution available.",
        )

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Fund"])

    # --- Load w_secs.csv and extract static characteristics ---
    wsecs_path = os.path.join(data_folder, "w_secs.csv")
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [
        col for col in wsecs.columns if col not in ["ISIN"] and not _is_date_like(col)
    ]
    wsecs_static = wsecs.drop_duplicates(subset=["ISIN"])[["ISIN"] + static_cols]

    # --- Characteristic selection ---
    available_characteristics = static_cols
    # Only set selected_characteristic if user selects it; otherwise, default to None (no group by)
    selected_characteristic = request.args.get(
        "characteristic", default=None, type=str
    )
    # If the selected characteristic is not valid, set to None
    if not selected_characteristic or selected_characteristic not in available_characteristics:
        selected_characteristic = None
    selected_characteristic_value = request.args.get(
        "characteristic_value", default="", type=str
    )

    # Join att_factors with w_secs static info
    df = df.merge(wsecs_static, on="ISIN", how="left")

    # Get date range for UI
    min_date = df["Date"].min()
    max_date = df["Date"].max()

    # Get filter parameters from query string
    start_date_str = request.args.get("start_date", default=None, type=str)
    end_date_str = request.args.get("end_date", default=None, type=str)

    # Parse date range
    start_date = (
        pd.to_datetime(start_date_str, errors="coerce") if start_date_str else min_date
    )
    end_date = (
        pd.to_datetime(end_date_str, errors="coerce") if end_date_str else max_date
    )

    # Compute available values for the selected characteristic
    if selected_characteristic:
        available_characteristic_values = sorted(
            df[selected_characteristic].dropna().unique()
        )
    else:
        available_characteristic_values = []

    # Filter by characteristic value if set
    if selected_characteristic and selected_characteristic_value:
        df = df[df[selected_characteristic] == selected_characteristic_value]

    # Filter by date range
    df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]

    # Use L1 and L2 groupings from config
    l1_groups = config.ATTRIBUTION_L1_GROUPS
    l2_all = sum(config.ATTRIBUTION_L2_GROUPS.values(), [])

    # Group by Date (and characteristic if grouping)
    group_cols = ["Date"]
    if selected_characteristic:
        group_cols.append(selected_characteristic)

    # --- Attribution column prefixes from config (fix for NameError) ---
    pfx_bench = ATTR_COLS['prefixes']['bench']
    pfx_prod = ATTR_COLS['prefixes']['prod']
    pfx_sp_bench = ATTR_COLS['prefixes']['sp_bench']
    pfx_sp_prod = ATTR_COLS['prefixes']['sp_prod']
    l0_bench = ATTR_COLS['prefixes']['l0_bench']
    l0_prod = ATTR_COLS['prefixes']['l0_prod']

    # Prepare time series data for charts
    chart_data_bench = []
    chart_data_port = []
    # Sort by date for cumulative
    for group_keys, group in df.groupby(group_cols):
        if selected_characteristic:
            date, char_val = group_keys
        else:
            (date,) = group_keys
            char_val = None
        bench_prod_res = group.apply(
            lambda row: calc_residual(row, l0_bench, pfx_bench, l2_all),
            axis=1,
        )
        bench_sp_res = group.apply(
            lambda row: calc_residual(
                row,
                l0_bench,
                pfx_sp_bench,
                l2_all,
            ),
            axis=1,
        )
        port_prod_res = group.apply(
            lambda row: calc_residual(row, l0_prod, pfx_prod, l2_all),
            axis=1,
        )
        port_sp_res = group.apply(
            lambda row: calc_residual(
                row,
                l0_prod,
                pfx_sp_prod,
                l2_all,
            ),
            axis=1,
        )
        bench_prod = bench_prod_res.sum()
        bench_sp = bench_sp_res.sum()
        port_prod = port_prod_res.sum()
        port_sp = port_sp_res.sum()
        bench_prod_abs = bench_prod_res.abs().sum()
        bench_sp_abs = bench_sp_res.abs().sum()
        port_prod_abs = port_prod_res.abs().sum()
        port_sp_abs = port_sp_res.abs().sum()
        chart_data_bench.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "residual_prod": bench_prod,
                "residual_sp": bench_sp,
                "abs_residual_prod": bench_prod_abs,
                "abs_residual_sp": bench_sp_abs,
            }
        )
        chart_data_port.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "residual_prod": port_prod,
                "residual_sp": port_sp,
                "abs_residual_prod": port_prod_abs,
                "abs_residual_sp": port_sp_abs,
            }
        )
    # Sort by date
    chart_data_bench = sorted(chart_data_bench, key=lambda x: x["date"])
    chart_data_port = sorted(chart_data_port, key=lambda x: x["date"])
    # Add cumulative net residuals
    cum_bench_prod = 0
    cum_bench_sp = 0
    cum_port_prod = 0
    cum_port_sp = 0
    for d in chart_data_bench:
        cum_bench_prod += d["residual_prod"]
        cum_bench_sp += d["residual_sp"]
        d["cum_residual_prod"] = cum_bench_prod
        d["cum_residual_sp"] = cum_bench_sp
    for d in chart_data_port:
        cum_port_prod += d["residual_prod"]
        cum_port_sp += d["residual_sp"]
        d["cum_residual_prod"] = cum_port_prod
        d["cum_residual_sp"] = cum_port_sp

    # Pass as JSON for JS charts
    chart_data_bench_json = json.dumps(chart_data_bench)
    chart_data_port_json = json.dumps(chart_data_port)

    return render_template(
        "attribution_charts.html",
        chart_data_bench_json=chart_data_bench_json,
        chart_data_port_json=chart_data_port_json,
        available_funds=available_funds,
        selected_fund=selected_fund,
        min_date=min_date,
        max_date=max_date,
        start_date=start_date,
        end_date=end_date,
        available_characteristics=available_characteristics,
        selected_characteristic=selected_characteristic,
        available_characteristic_values=available_characteristic_values,
        selected_characteristic_value=selected_characteristic_value,
        abs_toggle_default=False,
    )


@attribution_bp.route("/radar")
def attribution_radar() -> Response:
    """
    Attribution Radar Chart Page: Aggregates L1 or L2 factors (plus residual) for Portfolio and Benchmark
    for a single fund, over a selected date range and characteristic. Data is prepared for radar charts.
    """
    data_folder = current_app.config["DATA_FOLDER"]
    available_funds = get_available_funds(data_folder)
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    file_path = os.path.join(data_folder, f"att_factors_{selected_fund}.csv")
    if not selected_fund or not os.path.exists(file_path):
        return render_template(
            "attribution_radar.html",
            radar_data_json="[]",
            available_funds=available_funds,
            selected_fund=selected_fund,
            min_date=None,
            max_date=None,
            start_date=None,
            end_date=None,
            available_characteristics=[],
            selected_characteristic=None,
            available_characteristic_values=[],
            selected_characteristic_value=None,
            selected_level="L2",
            no_data_message="No attribution available.",
        )

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Fund"])

    # --- Load w_secs.csv and extract static characteristics ---
    wsecs_path = os.path.join(data_folder, "w_secs.csv")
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [
        col for col in wsecs.columns if col not in ["ISIN"] and not _is_date_like(col)
    ]
    wsecs_static = wsecs.drop_duplicates(subset=["ISIN"])[["ISIN"] + static_cols]

    # --- Characteristic selection ---
    available_characteristics = static_cols
    # Only set selected_characteristic if user selects it; otherwise, default to None (no group by)
    selected_characteristic = request.args.get(
        "characteristic", default=None, type=str
    )
    # If the selected characteristic is not valid, set to None
    if not selected_characteristic or selected_characteristic not in available_characteristics:
        selected_characteristic = None
    selected_characteristic_value = request.args.get(
        "characteristic_value", default="", type=str
    )

    # Join att_factors with w_secs static info
    df = df.merge(wsecs_static, on="ISIN", how="left")

    # Get date range for UI
    min_date = df["Date"].min()
    max_date = df["Date"].max()

    # Get filter parameters from query string
    start_date_str = request.args.get("start_date", default=None, type=str)
    end_date_str = request.args.get("end_date", default=None, type=str)
    selected_level = request.args.get("level", default="L2", type=str)  # Default to L2

    # Parse date range
    start_date = (
        pd.to_datetime(start_date_str, errors="coerce") if start_date_str else min_date
    )
    end_date = (
        pd.to_datetime(end_date_str, errors="coerce") if end_date_str else max_date
    )

    # Compute available values for the selected characteristic
    if selected_characteristic:
        available_characteristic_values = sorted(
            df[selected_characteristic].dropna().unique()
        )
    else:
        available_characteristic_values = []

    # Filter by characteristic value if set
    if selected_characteristic and selected_characteristic_value:
        df = df[df[selected_characteristic] == selected_characteristic_value]

    # Filter by date range
    df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]

    # Use L1 and L2 groupings from config
    l1_groups = config.ATTRIBUTION_L1_GROUPS
    l2_all = sum(config.ATTRIBUTION_L2_GROUPS.values(), [])

    # --- Aggregation for Radar Chart ---
    # sum_l2s_block, sum_l1s_block, and compute_residual_block are now imported from attribution_processing

    # Prepare radar data for Portfolio and Benchmark, Prod and S&P
    radar_labels = []
    port_prod = []
    port_sp = []
    bench_prod = []
    bench_sp = []
    residual_labels = ["Residual"]

    pfx_bench = ATTR_COLS['prefixes']['bench']
    pfx_prod = ATTR_COLS['prefixes']['prod']
    pfx_sp_bench = ATTR_COLS['prefixes']['sp_bench']
    pfx_sp_prod = ATTR_COLS['prefixes']['sp_prod']
    l0_bench = ATTR_COLS['prefixes']['l0_bench']
    l0_prod = ATTR_COLS['prefixes']['l0_prod']


    if selected_level == "L1":
        # --- L1 Aggregation ---
        radar_labels = list(l1_groups.keys()) + residual_labels
        # Portfolio
        # Use l1_groups (dict of L1 groupings) as required by sum_l1s_block, not l2_all (which is a flat list)
        port_l1_prod = sum_l1s_block(df, pfx_prod, l1_groups)
        port_l1_sp = sum_l1s_block(df, pfx_sp_prod, l1_groups)
        port_resid_prod = compute_residual_block(
            df, l0_prod, pfx_prod, l2_all
        )
        port_resid_sp = compute_residual_block(
            df, l0_prod, pfx_sp_prod, l2_all
        )
        port_prod = port_l1_prod + [port_resid_prod]
        port_sp = port_l1_sp + [port_resid_sp]
        # Benchmark
        bench_l1_prod = sum_l1s_block(df, pfx_bench, l1_groups)
        bench_l1_sp = sum_l1s_block(df, pfx_sp_bench, l1_groups)
        bench_resid_prod = compute_residual_block(
            df, l0_bench, pfx_bench, l2_all
        )
        bench_resid_sp = compute_residual_block(
            df, l0_bench, pfx_sp_bench, l2_all
        )
        bench_prod = bench_l1_prod + [bench_resid_prod]
        bench_sp = bench_l1_sp + [bench_resid_sp]
    else:  # L2 (default)
        radar_labels = l2_all + residual_labels
        # Portfolio
        port_l2_prod = sum_l2s_block(df, pfx_prod, l2_all)
        port_l2_sp = sum_l2s_block(df, pfx_sp_prod, l2_all)
        port_resid_prod = compute_residual_block(
            df, l0_prod, pfx_prod, l2_all
        )
        port_resid_sp = compute_residual_block(
            df, l0_prod, pfx_sp_prod, l2_all
        )
        port_prod = port_l2_prod + [port_resid_prod]
        port_sp = port_l2_sp + [port_resid_sp]
        # Benchmark
        bench_l2_prod = sum_l2s_block(df, pfx_bench, l2_all)
        bench_l2_sp = sum_l2s_block(df, pfx_sp_bench, l2_all)
        bench_resid_prod = compute_residual_block(
            df, l0_bench, pfx_bench, l2_all
        )
        bench_resid_sp = compute_residual_block(
            df, l0_bench, pfx_sp_bench, l2_all
        )
        bench_prod = bench_l2_prod + [bench_resid_prod]
        bench_sp = bench_l2_sp + [bench_resid_sp]

    # Prepare output for Chart.js radar chart
    radar_data = {
        "labels": radar_labels,
        "portfolio": {"prod": port_prod, "sp": port_sp},
        "benchmark": {"prod": bench_prod, "sp": bench_sp},
    }

    return render_template(
        "attribution_radar.html",
        radar_data_json=json.dumps(radar_data),
        available_funds=available_funds,
        selected_fund=selected_fund,
        min_date=min_date,
        max_date=max_date,
        start_date=start_date,
        end_date=end_date,
        available_characteristics=available_characteristics,
        selected_characteristic=selected_characteristic,
        available_characteristic_values=available_characteristic_values,
        selected_characteristic_value=selected_characteristic_value,
        selected_level=selected_level,
    )


@attribution_bp.route("/security")
def attribution_security_page() -> Response:
    """
    Attribution Security-Level Page: Shows attribution data for each security (ISIN) for a selected date and fund.
    Supports filtering by date, fund, type, bench/portfolio toggle, MTD aggregation, normalization, and pagination.
    Table columns: Security Name (linked), ISIN, Type, Returns (L0 Total), Original Residual, S&P Residual, Residual Diff, L1 values (Orig & S&P)
    """
    from pandas.tseries.offsets import BDay

    pfx_bench = ATTR_COLS['prefixes']['bench']
    pfx_prod = ATTR_COLS['prefixes']['prod']
    pfx_sp_bench = ATTR_COLS['prefixes']['sp_bench']
    pfx_sp_prod = ATTR_COLS['prefixes']['sp_prod']
    l0_bench = ATTR_COLS['prefixes']['l0_bench']
    l0_prod = ATTR_COLS['prefixes']['l0_prod']


    data_folder = current_app.config["DATA_FOLDER"]
    available_funds = get_available_funds(data_folder)
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    file_path = os.path.join(data_folder, f"att_factors_{selected_fund}.csv")
    if not selected_fund or not os.path.exists(file_path):
        return render_template(
            "attribution_security_page.html",
            rows=[],
            pagination=None,
            available_funds=available_funds,
            selected_fund=selected_fund,
            available_types=[],
            selected_type="",
            selected_date="",
            bench_or_port="port",
            mtd=False,
            normalize=False,
            no_data_message="No attribution available.",
        )

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Fund", "ISIN"])
    wsecs_path = os.path.join(data_folder, "w_secs.csv")
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [
        col for col in wsecs.columns if col not in ["ISIN"] and not _is_date_like(col)
    ]
    wsecs_static = wsecs.drop_duplicates(subset=["ISIN"])[["ISIN"] + static_cols]

    # --- UI Controls ---
    # Date picker: default to previous business day
    max_date = df["Date"].max()
    prev_bday = max_date if max_date is not pd.NaT else pd.Timestamp.today()
    prev_bday = prev_bday if prev_bday.weekday() < 5 else prev_bday - BDay(1)
    selected_date_str = request.args.get(
        "date", default=prev_bday.strftime("%Y-%m-%d"), type=str
    )
    selected_date = pd.to_datetime(selected_date_str, errors="coerce")
    # Fund dropdown: relies on available_funds populated by get_available_funds at the start of the function.
    # selected_fund is determined from request arguments or defaults to the first in available_funds.
    # available_funds = sorted(df["Fund"].dropna().unique()) # This line is removed as available_funds is already correctly populated.
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    # Type filter
    available_types = sorted(wsecs_static["Type"].dropna().unique())
    selected_type = request.args.get("type", default="", type=str)
    # Bench/Portfolio toggle
    bench_or_port = request.args.get(
        "bench_or_port", default="port", type=str
    )  # 'bench' or 'port'
    # MTD toggle
    mtd = request.args.get("mtd", default="off", type=str) == "on"
    # Normalize toggle
    normalize = request.args.get("normalize", default="off", type=str) == "on"
    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 50

    # --- Filter and Join Data ---
    df = df[df["Fund"] == selected_fund]
    if selected_type:
        # Join to get type for filtering
        df = df.merge(wsecs_static[["ISIN", "Type"]], on="ISIN", how="left")
        df = df[df["Type"] == selected_type]
    else:
        df = df.merge(wsecs_static[["ISIN", "Type"]], on="ISIN", how="left")

    # Date filtering/aggregation
    if mtd:
        # Get all dates in month up to selected_date
        if selected_date is pd.NaT:
            selected_date = max_date
        month_start = selected_date.replace(day=1)
        mtd_dates = pd.date_range(month_start, selected_date, freq="B")
        df = df[df["Date"].isin(mtd_dates)]
        # Fill missing days for each ISIN with zeros
        all_isins = df["ISIN"].unique()
        all_dates = mtd_dates
        idx = pd.MultiIndex.from_product([all_isins, all_dates], names=["ISIN", "Date"])
        df = df.set_index(["ISIN", "Date"])
        df = (
            df.reindex(idx, fill_value=0)
            .reset_index()
            .merge(
                df.reset_index(),
                on=["ISIN", "Date"],
                how="left",
                suffixes=("", "_orig"),
            )
        )
        # Use original columns where available, otherwise zeros
        for col in df.columns:
            if col.endswith("_orig"):
                base = col[:-5]
                df[base] = df[col].combine_first(df[base])
        # Aggregate (sum) over month for each ISIN
        group_cols = ["ISIN"]
        # Only sum numeric columns, keep first for non-numeric
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        agg_dict = {col: "sum" for col in numeric_cols if col not in group_cols}
        # For non-numeric columns (like 'Type', 'Security Name'), keep the first value
        for col in ["Type", "Security Name"]:
            if col in df.columns:
                agg_dict[col] = "first"
        df = df.groupby(group_cols).agg(agg_dict).reset_index()
        # Add back static info
        df = df.merge(wsecs_static, on="ISIN", how="left")
    else:
        df = df[df["Date"] == selected_date]

    # --- Normalization ---
    if bench_or_port == "bench":
        weight_col = "Bench Weight"
        l0_col = l0_bench
        l1_prefix = pfx_bench
        l1_sp_prefix = pfx_sp_bench
    else:
        weight_col = "Port Exp Wgt"
        l0_col = l0_prod
        l1_prefix = pfx_prod
        l1_sp_prefix = pfx_sp_prod
    # L1 factor names
    l1_factors = [
        "Rates Carry Daily",
        "Rates Convexity Daily",
        "Rates Curve Daily",
        "Rates Duration Daily",
        "Rates Roll Daily",
        "Credit Spread Change Daily",
        "Credit Convexity Daily",
        "Credit Carry Daily",
        "Credit Defaulted",
        "FX Carry Daily",
        "FX Change Daily",
    ]
    # L1 groupings (must be in this scope)
    l1_groups = config.ATTRIBUTION_L1_GROUPS
    # L2 groupings (must be in this scope)
    l2_all = sum(config.ATTRIBUTION_L2_GROUPS.values(), [])

    # Residual calculation
    def calc_residual(row, l0, l1_prefix, weight_col, normalize):
        """Return residual = L0 - sum(L1 factors). Handles normalization and correct column names."""
        # Always insert space between prefix and factor names to match CSV headers
        l1_sum = sum(
            [norm(row, f"{l1_prefix} {f}", weight_col, normalize) for f in l1_factors]
        )
        l0_val = norm(row, l0, weight_col, normalize)
        return l0_val - l1_sum

    # Normalization
    def norm(row, value_or_col_name, weight_col, normalize):
        """
        Normalizes the value by the weight if requested. Handles weights as percent strings (e.g., '30.00%'), floats (0.3), or numeric strings ('0.3').
        """
        w_val = row.get(weight_col)  # Get the raw weight value

        # Determine the value 'v' to normalize
        if isinstance(value_or_col_name, str):  # If it's a column name
            v = row.get(value_or_col_name, 0)
        else:  # Assume it's the direct value
            v = value_or_col_name if value_or_col_name is not None else 0

        def parse_weight(w):
            if w is None:
                return None
            if isinstance(w, str):
                w = w.strip()
                if w.endswith('%'):
                    try:
                        return float(w[:-1]) / 100.0
                    except ValueError:
                        return None
                try:
                    return float(w)
                except ValueError:
                    return None
            try:
                return float(w)
            except Exception:
                return None

        if normalize:
            w = parse_weight(w_val)
            if w is not None and w != 0:
                return v / w
        return v

    # Prepare table rows
    table_rows = []
    for _, row in df.iterrows():
        returns = norm(row, l0_col, weight_col, normalize)
        orig_resid = calc_residual(row, l0_col, l1_prefix, weight_col, normalize)
        sp_resid = calc_residual(row, l0_col, l1_sp_prefix, weight_col, normalize)
        resid_diff = orig_resid - sp_resid  # Already normalized (or raw) as per toggle
        normalized_orig_resid = orig_resid  # keep variable names for template compatibility
        normalized_sp_resid = sp_resid
        l1_vals = {}
        for l1_name, l2_list in l1_groups.items():
            # Always insert a space between prefix and factor name to match CSV headers
            orig_sum = sum(
                [norm(row, f"{l1_prefix} {l2}", weight_col, normalize) for l2 in l2_list]
            )
            sp_sum = sum(
                [norm(row, f"{l1_sp_prefix} {l2}", weight_col, normalize) for l2 in l2_list]
            )
            l1_vals[l1_name] = (orig_sum, sp_sum)
        table_rows.append(
            {
                "Security Name": row.get("Security Name", ""),
                "ISIN": row["ISIN"],
                "Type": row.get("Type", ""),
                "Returns": returns,
                "Original Residual": normalized_orig_resid,  # Use normalized value
                "S&P Residual": normalized_sp_resid,  # Use normalized value
                "Residual Diff": resid_diff,
                "L1 Values": l1_vals,
            }
        )
    # Sort by abs(Original Residual)
    table_rows = sorted(
        table_rows, key=lambda r: abs(r["Original Residual"]), reverse=True
    )
    # Pagination
    total_items = len(table_rows)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = table_rows[start:end]

    # Pagination object for template
    class Pagination:
        def __init__(self, page, per_page, total_items):
            self.page = page
            self.per_page = per_page
            self.total_items = total_items
            self.total_pages = max(1, (total_items + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = page < self.total_pages
            self.prev_num = page - 1
            self.next_num = page + 1
            self.start_page_display = max(1, page - 2)
            self.end_page_display = min(self.total_pages, page + 2)

        def url_for_page(self, p):
            args = request.args.to_dict()
            args["page"] = p
            return url_for("attribution_bp.attribution_security_page", **args)

    pagination = Pagination(page, per_page, total_items)
    return render_template(
        "attribution_security_page.html",
        rows=page_rows,
        pagination=pagination,
        available_funds=available_funds,
        selected_fund=selected_fund,
        available_types=available_types,
        selected_type=selected_type,
        selected_date=(
            selected_date.strftime("%Y-%m-%d") if selected_date is not pd.NaT else ""
        ),
        bench_or_port=bench_or_port,
        mtd=mtd,
        normalize=normalize,
    )


@attribution_bp.route("/security/timeseries")
def security_attribution_timeseries():
    """
    Individual Security Attribution Time Series Page.
    Shows attribution factor values (L1/L2) over time for a single security (ISIN) and fund.
    - Accepts fund and ISIN as query parameters.
    - Provides dropdown for L1/L2 factor selection (L1s first, then L2s).
    - Net/Abs toggle for values.
    - Shows S&P and Original time series for the selected factor (bar + cumulative line).
    - Underneath, shows Spread (Orig and S&P) for the same security.
    - If data is missing for Portfolio or Benchmark, omits the chart.
    - Links to security details page (Spread).
    """
    import pandas as pd
    from flask import request, render_template, current_app, url_for, redirect
    import os
    import json

    data_folder = current_app.config["DATA_FOLDER"]
    fund = request.args.get("fund", type=str)
    isin = request.args.get("isin", type=str)
    factor = request.args.get("factor", default=None, type=str)
    abs_toggle = request.args.get("abs", default="off", type=str) == "on"

    if not fund or not isin:
        return "Missing fund or ISIN", 400

    # -----------------------------
    # 1. Load per-fund attribution file
    # -----------------------------
    att_path = os.path.join(data_folder, f"att_factors_{fund}.csv")
    if not os.path.exists(att_path):
        return render_template(
            "attribution_security_timeseries.html",
            error="Attribution data not found for this fund.",
            fund=fund,
            isin=isin,
            factor=None,
            abs_toggle=abs_toggle,
            l1_factors=[],
            l2_factors=[],
            chart_bench_json="[]",
            chart_port_json="[]",
            spread_data_json="null",
            link_security_details=None,
        )

    df = pd.read_csv(att_path)
    df.columns = df.columns.str.strip()
    df = df[df["ISIN"] == isin]
    if df.empty:
        return render_template(
            "attribution_security_timeseries.html",
            error="No attribution data found for this ISIN in the selected fund.",
            fund=fund,
            isin=isin,
            factor=None,
            abs_toggle=abs_toggle,
            l1_factors=[],
            l2_factors=[],
            chart_bench_json="[]",
            chart_port_json="[]",
            spread_data_json="null",
            link_security_details=None,
        )

    # Ensure Date is datetime and sort
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")

    # -----------------------------
    # 2. Factor selection lists
    # -----------------------------
    l1_factors_all = [c for c in df.columns if c.startswith("L1 Bench ")]
    # Strip prefix to get nice names
    l1_names = sorted(list({c.replace("L1 Bench ", "") for c in l1_factors_all}))
    l2_factors_all = [c for c in df.columns if c.startswith("L2 Bench ")]
    l2_names = sorted(list({c.replace("L2 Bench ", "") for c in l2_factors_all}))

    # Prepare dropdown list with "Residual" first
    if not factor or factor not in (["Residual"] + l1_names + l2_names):
        factor = "Residual"

    # -----------------------------
    # 3. Helper to extract factor values
    # -----------------------------
    pfx_bench = ATTR_COLS['prefixes']['bench']  # "L1 Bench" etc.
    pfx_port = ATTR_COLS['prefixes']['prod']    # "L1 Port"
    pfx_sp_bench = ATTR_COLS['prefixes']['sp_bench']
    pfx_sp_port = ATTR_COLS['prefixes']['sp_prod']
    l0_bench = ATTR_COLS['prefixes']['l0_bench']
    l0_port = ATTR_COLS['prefixes']['l0_prod']

    l1_group_map = config.ATTRIBUTION_L1_GROUPS  # dict of group->list(l2)

    def get_factor_values(row, category: str, prefix_base: str, prefix_sp: str):
        """Return (orig, sp) value for chosen factor in given row.
        category: 'Residual', L1 name, or L2 name."""
        if category == "Residual":
            # residual = L0 - sum(all L1 factors)
            l1_factor_columns = []
            for l2s in l1_group_map.values():
                for l2 in l2s:
                    l1_factor_columns.append(f"{prefix_base} {l2}")
            l1_sum = sum([row.get(col, 0) for col in l1_factor_columns])
            l0_val = row.get(l0_bench if prefix_base.startswith("L1 Bench") else l0_port, 0)
            orig_val = l0_val - l1_sum
            # SP residual
            l1_sp_cols = [f"{prefix_sp} {l2}" for l2 in sum(l1_group_map.values(), [])]
            l1_sp_sum = sum([row.get(col, 0) for col in l1_sp_cols])
            l0_sp_val = row.get(l0_bench if prefix_sp.startswith("L1 Bench") else l0_port, 0)
            sp_val = l0_sp_val - l1_sp_sum
        else:
            # L1 or L2 value
            if category in l1_group_map:  # L1
                l2_list = l1_group_map[category]
                orig_val = sum([row.get(f"{prefix_base} {l2}", 0) for l2 in l2_list])
                sp_val = sum([row.get(f"{prefix_sp} {l2}", 0) for l2 in l2_list])
            else:  # L2 single
                orig_val = row.get(f"{prefix_base} {category}", 0)
                sp_val = row.get(f"{prefix_sp} {category}", 0)
        if abs_toggle:
            orig_val = abs(orig_val)
            sp_val = abs(sp_val)
        return orig_val, sp_val

    # -----------------------------
    # 4. Build time-series lists
    # -----------------------------
    chart_port = []
    chart_bench = []
    cum_port_orig = cum_port_sp = 0
    cum_bench_orig = cum_bench_sp = 0

    for _, row in df.iterrows():
        port_orig, port_sp = get_factor_values(row, factor, pfx_port, pfx_sp_port)
        bench_orig, bench_sp = get_factor_values(row, factor, pfx_bench, pfx_sp_bench)
        date_str = row["Date"].strftime("%Y-%m-%d")
        cum_port_orig += port_orig
        cum_port_sp   += port_sp
        cum_bench_orig += bench_orig
        cum_bench_sp   += bench_sp
        chart_port.append({
            "date": date_str,
            "orig": port_orig,
            "sp": port_sp,
            "cum_orig": cum_port_orig,
            "cum_sp": cum_port_sp,
        })
        chart_bench.append({
            "date": date_str,
            "orig": bench_orig,
            "sp": bench_sp,
            "cum_orig": cum_bench_orig,
            "cum_sp": cum_bench_sp,
        })

    chart_port_json = json.dumps(convert_dict(chart_port), default=str)
    chart_bench_json = json.dumps(convert_dict(chart_bench), default=str)

    # -----------------------------
    # 5. Load Spread data (Orig + SP) - REFACTORED
    # -----------------------------
    spread_data_json = json.dumps(None) # Default to null if issues occur
    attribution_dates = [item['date'] for item in chart_port] if chart_port else []

    if attribution_dates and isin: # Proceed if we have dates and an ISIN
        spread_series_orig, _, _ = load_filter_and_extract(
            data_folder, "sec_Spread.csv", isin
        )
        spread_series_sp, _, _ = load_filter_and_extract(
            data_folder, "sec_SpreadSP.csv", isin
        )

        orig_vals_aligned = []
        if spread_series_orig is not None and not spread_series_orig.empty:
            # Ensure series index is datetime for reindexing if it's not already
            if not isinstance(spread_series_orig.index, pd.DatetimeIndex):
                try:
                    spread_series_orig.index = pd.to_datetime(spread_series_orig.index)
                except Exception as e:
                    current_app.logger.warning(f"Failed to convert spread_series_orig index to DatetimeIndex: {e}")
                    spread_series_orig = None # Invalidate if conversion fails
            
            if spread_series_orig is not None: # Check again after potential invalidation
                # Convert attribution_dates (strings) to Timestamps for reindexing if necessary
                reindex_dates = pd.to_datetime(attribution_dates, errors='coerce')
                # Filter out NaT from reindex_dates if any conversion failed
                valid_reindex_dates = reindex_dates[~pd.isna(reindex_dates)]
                if not valid_reindex_dates.empty:
                    reindexed_orig = spread_series_orig.reindex(valid_reindex_dates, fill_value=None)
                    orig_vals_aligned = [to_native(val) for val in reindexed_orig.tolist()]
                else:
                    orig_vals_aligned = [None] * len(attribution_dates)
            else:
                 orig_vals_aligned = [None] * len(attribution_dates)
        else:
            orig_vals_aligned = [None] * len(attribution_dates)

        sp_vals_aligned = []
        if spread_series_sp is not None and not spread_series_sp.empty:
            if not isinstance(spread_series_sp.index, pd.DatetimeIndex):
                try:
                    spread_series_sp.index = pd.to_datetime(spread_series_sp.index)
                except Exception as e:
                    current_app.logger.warning(f"Failed to convert spread_series_sp index to DatetimeIndex: {e}")
                    spread_series_sp = None
            
            if spread_series_sp is not None:
                reindex_dates = pd.to_datetime(attribution_dates, errors='coerce')
                valid_reindex_dates = reindex_dates[~pd.isna(reindex_dates)]
                if not valid_reindex_dates.empty:
                    reindexed_sp = spread_series_sp.reindex(valid_reindex_dates, fill_value=None)
                    sp_vals_aligned = [to_native(val) for val in reindexed_sp.tolist()]
                else:
                    sp_vals_aligned = [None] * len(attribution_dates)
            else:
                sp_vals_aligned = [None] * len(attribution_dates)
        else:
            sp_vals_aligned = [None] * len(attribution_dates)
        
        # Ensure the dates in spread_data_json are the string dates from attribution_dates
        spread_data = {
            "dates": attribution_dates, # Use the original string dates for JSON
            "orig": orig_vals_aligned,
            "sp": sp_vals_aligned if sp_vals_aligned else None # Ensure SP is null if no data
        }
        spread_data_json = json.dumps(convert_dict(spread_data), default=str)
    else:
        current_app.logger.warning(f"Spread data not loaded for {isin}: No attribution dates or ISIN missing.")

    # -----------------------------
    # 6. Link to security details page
    # -----------------------------
    link_security_details = url_for('security.security_details', metric_name='Spread', security_id=isin)

    return render_template(
        "attribution_security_timeseries.html",
        fund=fund,
        isin=isin,
        factor=factor,
        abs_toggle=abs_toggle,
        l1_factors=l1_names,
        l2_factors=l2_names,
        chart_port_json=chart_port_json,
        chart_bench_json=chart_bench_json,
        spread_data_json=spread_data_json,
        link_security_details=link_security_details,
        error=None,
    )
