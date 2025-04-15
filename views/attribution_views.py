# Purpose: Defines the Attribution summary view for the Simple Data Checker app.
# This blueprint provides a page that loads att_factors.csv and displays the sum of residuals
# for each fund and day, for two cases: Benchmark and Portfolio, with both Prod and S&P columns.
# Residuals are calculated as L0 Total - (L1 Rates + L1 Credit + L1 FX), with L1s computed from L2s.

from flask import Blueprint, render_template, current_app, request, jsonify
import pandas as pd
import os
import json

attribution_bp = Blueprint('attribution_bp', __name__, url_prefix='/attribution')

def _is_date_like(column_name):
    import re
    if not isinstance(column_name, str):
        return False
    date_patterns = [
        r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
        r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
        r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{1,2}/\d{1,2}/\d{2,4}',  # D/M/YY or D/M/YYYY
        r'\d{1,2}-\d{1,2}-\d{2,4}',  # D-M-YY or D-M-YYYY
    ]
    return any(re.search(pattern, column_name) for pattern in date_patterns)

@attribution_bp.route('/summary')
def attribution_summary():
    """
    Loads att_factors.csv and computes residuals for each fund and day for Benchmark and Portfolio,
    showing both Prod and S&P (SPv3) columns. Supports grouping/filtering by characteristic.
    Table columns: Date, Fund, (Group by), Residual (Prod), Residual (S&P), Abs Residual (Prod), Abs Residual (S&P)
    Also supports L1 and L2 breakdowns via a 3-way toggle.
    """
    data_folder = current_app.config['DATA_FOLDER']
    file_path = os.path.join(data_folder, 'att_factors.csv')
    if not os.path.exists(file_path):
        return "att_factors.csv not found", 404

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()  # Remove accidental spaces
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date', 'Fund'])

    # --- Load w_secs.csv and extract static characteristics ---
    wsecs_path = os.path.join(data_folder, 'w_secs.csv')
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [col for col in wsecs.columns if col not in ['ISIN'] and not _is_date_like(col)]
    wsecs_static = wsecs.drop_duplicates(subset=['ISIN'])[['ISIN'] + static_cols]

    # --- Characteristic selection ---
    available_characteristics = static_cols
    selected_characteristic = request.args.get('characteristic', default='Type', type=str)
    if selected_characteristic not in available_characteristics:
        selected_characteristic = available_characteristics[0] if available_characteristics else None

    # Join att_factors with w_secs static info
    df = df.merge(wsecs_static, on='ISIN', how='left')

    # Get available funds and date range for UI
    available_funds = sorted(df['Fund'].dropna().unique())
    min_date = df['Date'].min()
    max_date = df['Date'].max()

    # Get filter parameters from query string
    selected_fund = request.args.get('fund', default='', type=str)
    start_date_str = request.args.get('start_date', default=None, type=str)
    end_date_str = request.args.get('end_date', default=None, type=str)
    selected_level = request.args.get('level', default='L0', type=str)
    selected_characteristic_value = request.args.get('characteristic_value', default='', type=str)

    # Default to first fund if none selected
    if not selected_fund and available_funds:
        selected_fund = available_funds[0]

    # Parse date range
    start_date = pd.to_datetime(start_date_str, errors='coerce') if start_date_str else min_date
    end_date = pd.to_datetime(end_date_str, errors='coerce') if end_date_str else max_date

    # Helper: L2 column names for each group
    l2_credit = [
        'Credit Spread Change Daily', 'Credit Convexity Daily', 'Credit Carry Daily', 'Credit Defaulted'
    ]
    l2_rates = [
        'Rates Carry Daily', 'Rates Convexity Daily', 'Rates Curve Daily', 'Rates Duration Daily', 'Rates Roll Daily'
    ]
    l2_fx = [
        'FX Carry Daily', 'FX Change Daily'
    ]
    l2_all = l2_credit + l2_rates + l2_fx

    def sum_l2s(row, prefix):
        credit = sum([row.get(f'{prefix}{col}', 0) for col in l2_credit])
        rates = sum([row.get(f'{prefix}{col}', 0) for col in l2_rates])
        fx = sum([row.get(f'{prefix}{col}', 0) for col in l2_fx])
        return credit, rates, fx

    def compute_residual(row, l0_col, l2_prefix):
        l0 = row.get(l0_col, 0)
        credit, rates, fx = sum_l2s(row, l2_prefix)
        l1_total = credit + rates + fx
        return l0 - l1_total

    # Prepare results: group by Date, Fund, and selected characteristic
    group_cols = ['Date', 'Fund']
    if selected_characteristic:
        group_cols.append(selected_characteristic)
    benchmark_results = []
    portfolio_results = []

    # Compute available values for the selected characteristic
    if selected_characteristic:
        available_characteristic_values = sorted(df[selected_characteristic].dropna().unique())
    else:
        available_characteristic_values = []

    for group_keys, group in df.groupby(group_cols):
        if selected_characteristic:
            date, fund, char_val = group_keys
        else:
            date, fund = group_keys
            char_val = None
        if selected_fund and fund != selected_fund:
            continue
        if not (start_date <= date <= end_date):
            continue

        # Filter by characteristic value if set
        if selected_characteristic and selected_characteristic_value:
            if char_val != selected_characteristic_value:
                continue

        # L0: Residuals and Abs Residuals
        if selected_level == 'L0' or not selected_level:
            bench_prod_res = group.apply(lambda row: compute_residual(row, 'L0 Bench Total Daily', 'L2 Bench '), axis=1)
            bench_sp_res = group.apply(lambda row: compute_residual(row, 'L0 Bench Total Daily', 'SPv3_L2 Bench '), axis=1)
            port_prod_res = group.apply(lambda row: compute_residual(row, 'L0 Port Total Daily ', 'L2 Port '), axis=1)
            port_sp_res = group.apply(lambda row: compute_residual(row, 'L0 Port Total Daily ', 'SPv3_L2 Port '), axis=1)
            bench_prod = bench_prod_res.sum()
            bench_sp = bench_sp_res.sum()
            port_prod = port_prod_res.sum()
            port_sp = port_sp_res.sum()
            bench_prod_abs = bench_prod_res.abs().sum()
            bench_sp_abs = bench_sp_res.abs().sum()
            port_prod_abs = port_prod_res.abs().sum()
            port_sp_abs = port_sp_res.abs().sum()
            row_info_bench = {
                'Date': date, 'Fund': fund, 'Residual_Prod': bench_prod, 'Residual_SP': bench_sp,
                'AbsResidual_Prod': bench_prod_abs, 'AbsResidual_SP': bench_sp_abs
            }
            row_info_port = {
                'Date': date, 'Fund': fund, 'Residual_Prod': port_prod, 'Residual_SP': port_sp,
                'AbsResidual_Prod': port_prod_abs, 'AbsResidual_SP': port_sp_abs
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)

        # L1: Show L1 Rates, Credit, FX (Prod and S&P)
        elif selected_level == 'L1':
            # Aggregate L1s for Prod and S&P
            bench_l1_credit_prod = group.apply(lambda row: sum([row.get(f'L2 Bench {col}', 0) for col in l2_credit]), axis=1).sum()
            bench_l1_credit_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Bench {col}', 0) for col in l2_credit]), axis=1).sum()
            bench_l1_rates_prod = group.apply(lambda row: sum([row.get(f'L2 Bench {col}', 0) for col in l2_rates]), axis=1).sum()
            bench_l1_rates_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Bench {col}', 0) for col in l2_rates]), axis=1).sum()
            bench_l1_fx_prod = group.apply(lambda row: sum([row.get(f'L2 Bench {col}', 0) for col in l2_fx]), axis=1).sum()
            bench_l1_fx_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Bench {col}', 0) for col in l2_fx]), axis=1).sum()
            port_l1_credit_prod = group.apply(lambda row: sum([row.get(f'L2 Port {col}', 0) for col in l2_credit]), axis=1).sum()
            port_l1_credit_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Port {col}', 0) for col in l2_credit]), axis=1).sum()
            port_l1_rates_prod = group.apply(lambda row: sum([row.get(f'L2 Port {col}', 0) for col in l2_rates]), axis=1).sum()
            port_l1_rates_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Port {col}', 0) for col in l2_rates]), axis=1).sum()
            port_l1_fx_prod = group.apply(lambda row: sum([row.get(f'L2 Port {col}', 0) for col in l2_fx]), axis=1).sum()
            port_l1_fx_sp = group.apply(lambda row: sum([row.get(f'SPv3_L2 Port {col}', 0) for col in l2_fx]), axis=1).sum()
            row_info_bench = {
                'Date': date, 'Fund': fund,
                'L1Rates_Prod': bench_l1_rates_prod, 'L1Rates_SP': bench_l1_rates_sp,
                'L1Credit_Prod': bench_l1_credit_prod, 'L1Credit_SP': bench_l1_credit_sp,
                'L1FX_Prod': bench_l1_fx_prod, 'L1FX_SP': bench_l1_fx_sp
            }
            row_info_port = {
                'Date': date, 'Fund': fund,
                'L1Rates_Prod': port_l1_rates_prod, 'L1Rates_SP': port_l1_rates_sp,
                'L1Credit_Prod': port_l1_credit_prod, 'L1Credit_SP': port_l1_credit_sp,
                'L1FX_Prod': port_l1_fx_prod, 'L1FX_SP': port_l1_fx_sp
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)

        # L2: Show all L2 values (Prod and S&P) side by side
        elif selected_level == 'L2':
            # For each L2, sum for group, for both Prod and S&P
            l2prod = {col: group.apply(lambda row: row.get(f'L2 Bench {col}', 0), axis=1).sum() for col in l2_all}
            l2sp = {col: group.apply(lambda row: row.get(f'SPv3_L2 Bench {col}', 0), axis=1).sum() for col in l2_all}
            l2prod_port = {col: group.apply(lambda row: row.get(f'L2 Port {col}', 0), axis=1).sum() for col in l2_all}
            l2sp_port = {col: group.apply(lambda row: row.get(f'SPv3_L2 Port {col}', 0), axis=1).sum() for col in l2_all}
            row_info_bench = {
                'Date': date, 'Fund': fund,
                'L2Prod': l2prod, 'L2SP': l2sp, 'L2ProdKeys': l2_all
            }
            row_info_port = {
                'Date': date, 'Fund': fund,
                'L2Prod': l2prod_port, 'L2SP': l2sp_port, 'L2ProdKeys': l2_all
            }
            if selected_characteristic:
                row_info_bench[selected_characteristic] = char_val
                row_info_port[selected_characteristic] = char_val
            benchmark_results.append(row_info_bench)
            portfolio_results.append(row_info_port)

    # Sort
    benchmark_results = sorted(benchmark_results, key=lambda x: (x['Date'], x['Fund'], x.get(selected_characteristic, '')))
    portfolio_results = sorted(portfolio_results, key=lambda x: (x['Date'], x['Fund'], x.get(selected_characteristic, '')))

    return render_template(
        'attribution_summary.html',
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
        selected_characteristic_value=selected_characteristic_value
    )

@attribution_bp.route('/charts')
def attribution_charts():
    """
    Attribution Residuals Chart Page: Shows residuals over time for Benchmark and Portfolio (Prod and S&P),
    with filters and grouping as in the summary view. Data is prepared for JS charts.
    """
    data_folder = current_app.config['DATA_FOLDER']
    file_path = os.path.join(data_folder, 'att_factors.csv')
    if not os.path.exists(file_path):
        return "att_factors.csv not found", 404

    # Load data
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date', 'Fund'])

    # --- Load w_secs.csv and extract static characteristics ---
    wsecs_path = os.path.join(data_folder, 'w_secs.csv')
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [col for col in wsecs.columns if col not in ['ISIN'] and not _is_date_like(col)]
    wsecs_static = wsecs.drop_duplicates(subset=['ISIN'])[['ISIN'] + static_cols]

    # --- Characteristic selection ---
    available_characteristics = static_cols
    selected_characteristic = request.args.get('characteristic', default='Type', type=str)
    if selected_characteristic not in available_characteristics:
        selected_characteristic = available_characteristics[0] if available_characteristics else None
    selected_characteristic_value = request.args.get('characteristic_value', default='', type=str)

    # Join att_factors with w_secs static info
    df = df.merge(wsecs_static, on='ISIN', how='left')

    # Get available funds and date range for UI
    available_funds = sorted(df['Fund'].dropna().unique())
    min_date = df['Date'].min()
    max_date = df['Date'].max()

    # Get filter parameters from query string
    selected_fund = request.args.get('fund', default='', type=str)
    start_date_str = request.args.get('start_date', default=None, type=str)
    end_date_str = request.args.get('end_date', default=None, type=str)

    # Default to first fund if none selected
    if not selected_fund and available_funds:
        selected_fund = available_funds[0]

    # Parse date range
    start_date = pd.to_datetime(start_date_str, errors='coerce') if start_date_str else min_date
    end_date = pd.to_datetime(end_date_str, errors='coerce') if end_date_str else max_date

    # Compute available values for the selected characteristic
    if selected_characteristic:
        available_characteristic_values = sorted(df[selected_characteristic].dropna().unique())
    else:
        available_characteristic_values = []

    # Filter by characteristic value if set
    if selected_characteristic and selected_characteristic_value:
        df = df[df[selected_characteristic] == selected_characteristic_value]

    # Filter by fund
    if selected_fund:
        df = df[df['Fund'] == selected_fund]

    # Filter by date range
    df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]

    # Helper: L2 column names for each group
    l2_credit = [
        'Credit Spread Change Daily', 'Credit Convexity Daily', 'Credit Carry Daily', 'Credit Defaulted'
    ]
    l2_rates = [
        'Rates Carry Daily', 'Rates Convexity Daily', 'Rates Curve Daily', 'Rates Duration Daily', 'Rates Roll Daily'
    ]
    l2_fx = [
        'FX Carry Daily', 'FX Change Daily'
    ]

    def sum_l2s(row, prefix):
        credit = sum([row.get(f'{prefix}{col}', 0) for col in l2_credit])
        rates = sum([row.get(f'{prefix}{col}', 0) for col in l2_rates])
        fx = sum([row.get(f'{prefix}{col}', 0) for col in l2_fx])
        return credit, rates, fx

    def compute_residual(row, l0_col, l2_prefix):
        l0 = row.get(l0_col, 0)
        credit, rates, fx = sum_l2s(row, l2_prefix)
        l1_total = credit + rates + fx
        return l0 - l1_total

    # Group by Date (and characteristic if grouping)
    group_cols = ['Date']
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
            date, = group_keys
            char_val = None
        # Aggregate residuals for this day (sum over all ISINs)
        bench_prod_res = group.apply(lambda row: compute_residual(row, 'L0 Bench Total Daily', 'L2 Bench '), axis=1)
        bench_sp_res = group.apply(lambda row: compute_residual(row, 'L0 Bench Total Daily', 'SPv3_L2 Bench '), axis=1)
        port_prod_res = group.apply(lambda row: compute_residual(row, 'L0 Port Total Daily ', 'L2 Port '), axis=1)
        port_sp_res = group.apply(lambda row: compute_residual(row, 'L0 Port Total Daily ', 'SPv3_L2 Port '), axis=1)
        # Net and abs
        bench_prod = bench_prod_res.sum()
        bench_sp = bench_sp_res.sum()
        port_prod = port_prod_res.sum()
        port_sp = port_sp_res.sum()
        bench_prod_abs = bench_prod_res.abs().sum()
        bench_sp_abs = bench_sp_res.abs().sum()
        port_prod_abs = port_prod_res.abs().sum()
        port_sp_abs = port_sp_res.abs().sum()
        chart_data_bench.append({
            'date': date.strftime('%Y-%m-%d'),
            'residual_prod': bench_prod,
            'residual_sp': bench_sp,
            'abs_residual_prod': bench_prod_abs,
            'abs_residual_sp': bench_sp_abs
        })
        chart_data_port.append({
            'date': date.strftime('%Y-%m-%d'),
            'residual_prod': port_prod,
            'residual_sp': port_sp,
            'abs_residual_prod': port_prod_abs,
            'abs_residual_sp': port_sp_abs
        })
    # Sort by date
    chart_data_bench = sorted(chart_data_bench, key=lambda x: x['date'])
    chart_data_port = sorted(chart_data_port, key=lambda x: x['date'])
    # Add cumulative net residuals
    cum_bench_prod = 0
    cum_bench_sp = 0
    cum_port_prod = 0
    cum_port_sp = 0
    for d in chart_data_bench:
        cum_bench_prod += d['residual_prod']
        cum_bench_sp += d['residual_sp']
        d['cum_residual_prod'] = cum_bench_prod
        d['cum_residual_sp'] = cum_bench_sp
    for d in chart_data_port:
        cum_port_prod += d['residual_prod']
        cum_port_sp += d['residual_sp']
        d['cum_residual_prod'] = cum_port_prod
        d['cum_residual_sp'] = cum_port_sp

    # Pass as JSON for JS charts
    chart_data_bench_json = json.dumps(chart_data_bench)
    chart_data_port_json = json.dumps(chart_data_port)

    return render_template(
        'attribution_charts.html',
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
        abs_toggle_default=False
    ) 