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

attribution_bp = Blueprint("attribution_bp", __name__, url_prefix="/attribution")


# Utility: Get available funds from FundList.csv (preferred) or w_secs.csv fallback
def get_available_funds(data_folder: str) -> list:
    """
    Returns a sorted list of available fund codes for attribution, using FundList.csv if present, else w_secs.csv.
    """
    fund_list_path = os.path.join(data_folder, "FundList.csv")
    if os.path.exists(fund_list_path):
        df = pd.read_csv(fund_list_path)
        if "Fund Code" in df.columns:
            return sorted(df["Fund Code"].dropna().astype(str).unique())
    # Fallback: w_secs.csv
    wsecs_path = os.path.join(data_folder, "w_secs.csv")
    if os.path.exists(wsecs_path):
        wsecs = pd.read_csv(wsecs_path)
        if "Fund" in wsecs.columns:
            return sorted(wsecs["Fund"].dropna().astype(str).unique())
    return []


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
    selected_characteristic = request.args.get(
        "characteristic", default="Type", type=str
    )
    if selected_characteristic not in available_characteristics:
        selected_characteristic = (
            available_characteristics[0] if available_characteristics else None
        )

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
                    row, "L0 Bench Total Daily", "L2 Bench ", l2_all
                ),
                axis=1,
            )
            bench_sp_res = group.apply(
                lambda row: calc_residual(
                    row, "L0 Bench Total Daily", "SPv3_L2 Bench ", l2_all
                ),
                axis=1,
            )
            port_prod_res = group.apply(
                lambda row: calc_residual(
                    row, "L0 Port Total Daily ", "L2 Port ", l2_all
                ),
                axis=1,
            )
            port_sp_res = group.apply(
                lambda row: calc_residual(
                    row, "L0 Port Total Daily ", "SPv3_L2 Port ", l2_all
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
            bench_l1_prod = sum_l1s_block(group, "L2 Bench ", l1_groups)
            bench_l1_sp = sum_l1s_block(group, "SPv3_L2 Bench ", l1_groups)
            port_l1_prod = sum_l1s_block(group, "L2 Port ", l1_groups)
            port_l1_sp = sum_l1s_block(group, "SPv3_L2 Port ", l1_groups)
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
            l2prod = dict(zip(l2_all, sum_l2s_block(group, "L2 Bench ", l2_all)))
            l2sp = dict(zip(l2_all, sum_l2s_block(group, "SPv3_L2 Bench ", l2_all)))
            l2prod_port = dict(zip(l2_all, sum_l2s_block(group, "L2 Port ", l2_all)))
            l2sp_port = dict(zip(l2_all, sum_l2s_block(group, "SPv3_L2 Port ", l2_all)))
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
    selected_characteristic = request.args.get(
        "characteristic", default="Type", type=str
    )
    if selected_characteristic not in available_characteristics:
        selected_characteristic = (
            available_characteristics[0] if available_characteristics else None
        )
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
            lambda row: calc_residual(row, "L0 Bench Total Daily", "L2 Bench ", l2_all),
            axis=1,
        )
        bench_sp_res = group.apply(
            lambda row: calc_residual(
                row,
                "L0 Bench Total Daily",
                "SPv3_L2 Bench ",
                l2_all,
            ),
            axis=1,
        )
        port_prod_res = group.apply(
            lambda row: calc_residual(row, "L0 Port Total Daily ", "L2 Port ", l2_all),
            axis=1,
        )
        port_sp_res = group.apply(
            lambda row: calc_residual(
                row,
                "L0 Port Total Daily ",
                "SPv3_L2 Port ",
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
    selected_characteristic = request.args.get(
        "characteristic", default="Type", type=str
    )
    if selected_characteristic not in available_characteristics:
        selected_characteristic = (
            available_characteristics[0] if available_characteristics else None
        )
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

    if selected_level == "L1":
        radar_labels = list(l1_groups.keys()) + residual_labels
        # Portfolio
        # Use l1_groups (dict of L1 groupings) as required by sum_l1s_block, not l2_all (which is a flat list)
        port_l1_prod = sum_l1s_block(df, "L2 Port ", l1_groups)
        port_l1_sp = sum_l1s_block(df, "SPv3_L2 Port ", l1_groups)
        port_resid_prod = compute_residual_block(
            df, "L0 Port Total Daily ", "L2 Port ", l2_all
        )
        port_resid_sp = compute_residual_block(
            df, "L0 Port Total Daily ", "SPv3_L2 Port ", l2_all
        )
        port_prod = port_l1_prod + [port_resid_prod]
        port_sp = port_l1_sp + [port_resid_sp]
        # Benchmark
        bench_l1_prod = sum_l1s_block(df, "L2 Bench ", l1_groups)
        bench_l1_sp = sum_l1s_block(df, "SPv3_L2 Bench ", l1_groups)
        bench_resid_prod = compute_residual_block(
            df, "L0 Bench Total Daily", "L2 Bench ", l2_all
        )
        bench_resid_sp = compute_residual_block(
            df, "L0 Bench Total Daily", "SPv3_L2 Bench ", l2_all
        )
        bench_prod = bench_l1_prod + [bench_resid_prod]
        bench_sp = bench_l1_sp + [bench_resid_sp]
    else:  # L2 (default)
        radar_labels = l2_all + residual_labels
        # Portfolio
        port_l2_prod = sum_l2s_block(df, "L2 Port ", l2_all)
        port_l2_sp = sum_l2s_block(df, "SPv3_L2 Port ", l2_all)
        port_resid_prod = compute_residual_block(
            df, "L0 Port Total Daily ", "L2 Port ", l2_all
        )
        port_resid_sp = compute_residual_block(
            df, "L0 Port Total Daily ", "SPv3_L2 Port ", l2_all
        )
        port_prod = port_l2_prod + [port_resid_prod]
        port_sp = port_l2_sp + [port_resid_sp]
        # Benchmark
        bench_l2_prod = sum_l2s_block(df, "L2 Bench ", l2_all)
        bench_l2_sp = sum_l2s_block(df, "SPv3_L2 Bench ", l2_all)
        bench_resid_prod = compute_residual_block(
            df, "L0 Bench Total Daily", "L2 Bench ", l2_all
        )
        bench_resid_sp = compute_residual_block(
            df, "L0 Bench Total Daily", "SPv3_L2 Bench ", l2_all
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
    import numpy as np
    from pandas.tseries.offsets import BDay

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
            bench_or_port="bench",
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
    # Fund dropdown: default to first fund
    available_funds = sorted(df["Fund"].dropna().unique())
    selected_fund = request.args.get(
        "fund", default=available_funds[0] if available_funds else "", type=str
    )
    # Type filter
    available_types = sorted(wsecs_static["Type"].dropna().unique())
    selected_type = request.args.get("type", default="", type=str)
    # Bench/Portfolio toggle
    bench_or_port = request.args.get(
        "bench_or_port", default="bench", type=str
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
        l0_col = "L0 Bench Total Daily"
        l1_prefix = "L2 Bench "
        l1_sp_prefix = "SPv3_L2 Bench "
    else:
        weight_col = "Port Exp Wgt"
        l0_col = "L0 Port Total Daily "
        l1_prefix = "L2 Port "
        l1_sp_prefix = "SPv3_L2 Port "
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
    def calc_residual(row, l0, l1_prefix):
        l1_sum = sum([row.get(f"{l1_prefix}{f}", 0) for f in l1_factors])
        return row.get(l0, 0) - l1_sum

    # Normalization
    def norm(row, value_or_col_name, weight_col):
        w_val = row.get(weight_col)  # Get the raw weight value

        # Determine the value 'v' to normalize
        if isinstance(value_or_col_name, str):  # If it's a column name
            v = row.get(value_or_col_name, 0)
        else:  # Assume it's the direct value
            v = value_or_col_name if value_or_col_name is not None else 0

        # Check normalize flag from outer scope
        if current_app.config.get("ATTRIBUTION_NORMALIZE", False) and w_val is not None:
            try:
                # Attempt to convert weight to float
                w = float(w_val)
                # Perform division only if weight is non-zero
                if w != 0:
                    return v / w
            except (ValueError, TypeError):
                # Handle cases where weight is not a valid number
                pass  # Keep original value v if weight is invalid

        return v  # Return original or calculated value

    # Prepare table rows
    table_rows = []
    for _, row in df.iterrows():
        returns = norm(row, l0_col, weight_col)
        orig_resid = calc_residual(row, l0_col, l1_prefix)
        sp_resid = calc_residual(row, l0_col, l1_sp_prefix)
        # Normalize the actual residual values if requested
        normalized_orig_resid = (
            norm(row, orig_resid, weight_col)
            if normalize and weight_col
            else orig_resid
        )
        normalized_sp_resid = (
            norm(row, sp_resid, weight_col) if normalize and weight_col else sp_resid
        )
        resid_diff = (
            normalized_orig_resid - normalized_sp_resid
        )  # Use normalized residuals for diff
        l1_vals = {}
        for l1_name, l2_list in l1_groups.items():
            # Apply normalization within the sum for L1 values
            orig_sum = sum(
                [norm(row, f"{l1_prefix}{l2}", weight_col) for l2 in l2_list]
            )
            sp_sum = sum(
                [norm(row, f"{l1_sp_prefix}{l2}", weight_col) for l2 in l2_list]
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
