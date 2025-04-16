# Purpose: Defines the Attribution summary view for the Simple Data Checker app.
# This blueprint provides a page that loads att_factors.csv and displays the sum of residuals
# for each fund and day, for two cases: Benchmark and Portfolio, with both Prod and S&P columns.
# Residuals are calculated as L0 Total - (L1 Rates + L1 Credit + L1 FX), with L1s computed from L2s.

from flask import Blueprint, render_template, current_app, request, jsonify, url_for
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

@attribution_bp.route('/radar')
def attribution_radar():
    """
    Attribution Radar Chart Page: Aggregates L1 or L2 factors (plus residual) for Portfolio and Benchmark
    for a single fund, over a selected date range and characteristic. Data is prepared for radar charts.
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
    selected_level = request.args.get('level', default='L2', type=str)  # Default to L2

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

    # Filter by fund (only one fund allowed)
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
    l2_all = l2_credit + l2_rates + l2_fx

    # L1 groupings
    l1_groups = {
        'Rates': l2_rates,
        'Credit': l2_credit,
        'FX': l2_fx
    }

    # --- Aggregation for Radar Chart ---
    def sum_l2s_block(df_block, prefix, l2_cols):
        return [df_block[f'{prefix}{col}'].sum() if f'{prefix}{col}' in df_block else 0 for col in l2_cols]

    def sum_l1s_block(df_block, prefix):
        return [df_block[[f'{prefix}{col}' for col in l2s if f'{prefix}{col}' in df_block]].sum().sum() for l2s in l1_groups.values()]

    def compute_residual_block(df_block, l0_col, l2_prefix, l2_cols):
        l0 = df_block[l0_col].sum() if l0_col in df_block else 0
        l2_sum = sum([df_block[f'{l2_prefix}{col}'].sum() if f'{l2_prefix}{col}' in df_block else 0 for col in l2_cols])
        return l0 - l2_sum

    # Prepare radar data for Portfolio and Benchmark, Prod and S&P
    radar_labels = []
    port_prod = []
    port_sp = []
    bench_prod = []
    bench_sp = []
    residual_labels = ['Residual']

    if selected_level == 'L1':
        radar_labels = list(l1_groups.keys()) + residual_labels
        # Portfolio
        port_l1_prod = sum_l1s_block(df, 'L2 Port ', l2_all)
        port_l1_sp = sum_l1s_block(df, 'SPv3_L2 Port ', l2_all)
        port_resid_prod = compute_residual_block(df, 'L0 Port Total Daily ', 'L2 Port ', l2_all)
        port_resid_sp = compute_residual_block(df, 'L0 Port Total Daily ', 'SPv3_L2 Port ', l2_all)
        port_prod = port_l1_prod + [port_resid_prod]
        port_sp = port_l1_sp + [port_resid_sp]
        # Benchmark
        bench_l1_prod = sum_l1s_block(df, 'L2 Bench ', l2_all)
        bench_l1_sp = sum_l1s_block(df, 'SPv3_L2 Bench ', l2_all)
        bench_resid_prod = compute_residual_block(df, 'L0 Bench Total Daily', 'L2 Bench ', l2_all)
        bench_resid_sp = compute_residual_block(df, 'L0 Bench Total Daily', 'SPv3_L2 Bench ', l2_all)
        bench_prod = bench_l1_prod + [bench_resid_prod]
        bench_sp = bench_l1_sp + [bench_resid_sp]
    else:  # L2 (default)
        radar_labels = l2_all + residual_labels
        # Portfolio
        port_l2_prod = sum_l2s_block(df, 'L2 Port ', l2_all)
        port_l2_sp = sum_l2s_block(df, 'SPv3_L2 Port ', l2_all)
        port_resid_prod = compute_residual_block(df, 'L0 Port Total Daily ', 'L2 Port ', l2_all)
        port_resid_sp = compute_residual_block(df, 'L0 Port Total Daily ', 'SPv3_L2 Port ', l2_all)
        port_prod = port_l2_prod + [port_resid_prod]
        port_sp = port_l2_sp + [port_resid_sp]
        # Benchmark
        bench_l2_prod = sum_l2s_block(df, 'L2 Bench ', l2_all)
        bench_l2_sp = sum_l2s_block(df, 'SPv3_L2 Bench ', l2_all)
        bench_resid_prod = compute_residual_block(df, 'L0 Bench Total Daily', 'L2 Bench ', l2_all)
        bench_resid_sp = compute_residual_block(df, 'L0 Bench Total Daily', 'SPv3_L2 Bench ', l2_all)
        bench_prod = bench_l2_prod + [bench_resid_prod]
        bench_sp = bench_l2_sp + [bench_resid_sp]

    # Prepare output for Chart.js radar chart
    radar_data = {
        'labels': radar_labels,
        'portfolio': {
            'prod': port_prod,
            'sp': port_sp
        },
        'benchmark': {
            'prod': bench_prod,
            'sp': bench_sp
        }
    }

    return render_template(
        'attribution_radar.html',
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
        selected_level=selected_level
    )

@attribution_bp.route('/security')
def attribution_security_page():
    """
    Attribution Security-Level Page: Shows attribution data for each security (ISIN) for a selected date and fund.
    Supports filtering by date, fund, type, bench/portfolio toggle, MTD aggregation, normalization, and pagination.
    Table columns: Security Name (linked), ISIN, Type, Returns (L0 Total), Original Residual, S&P Residual, Residual Diff, L1 values (Orig & S&P)
    """
    import numpy as np
    from pandas.tseries.offsets import BDay
    data_folder = current_app.config['DATA_FOLDER']
    att_path = os.path.join(data_folder, 'att_factors.csv')
    wsecs_path = os.path.join(data_folder, 'w_secs.csv')
    if not os.path.exists(att_path) or not os.path.exists(wsecs_path):
        return "Required data files not found", 404

    # Load data
    df = pd.read_csv(att_path)
    df.columns = df.columns.str.strip()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date', 'Fund', 'ISIN'])
    wsecs = pd.read_csv(wsecs_path)
    wsecs.columns = wsecs.columns.str.strip()
    static_cols = [col for col in wsecs.columns if col not in ['ISIN'] and not _is_date_like(col)]
    wsecs_static = wsecs.drop_duplicates(subset=['ISIN'])[['ISIN'] + static_cols]

    # --- UI Controls ---
    # Date picker: default to previous business day
    max_date = df['Date'].max()
    prev_bday = (max_date if max_date is not pd.NaT else pd.Timestamp.today())
    prev_bday = prev_bday if prev_bday.weekday() < 5 else prev_bday - BDay(1)
    selected_date_str = request.args.get('date', default=prev_bday.strftime('%Y-%m-%d'), type=str)
    selected_date = pd.to_datetime(selected_date_str, errors='coerce')
    # Fund dropdown: default to first fund
    available_funds = sorted(df['Fund'].dropna().unique())
    selected_fund = request.args.get('fund', default=available_funds[0] if available_funds else '', type=str)
    # Type filter
    available_types = sorted(wsecs_static['Type'].dropna().unique())
    selected_type = request.args.get('type', default='', type=str)
    # Bench/Portfolio toggle
    bench_or_port = request.args.get('bench_or_port', default='bench', type=str)  # 'bench' or 'port'
    # MTD toggle
    mtd = request.args.get('mtd', default='off', type=str) == 'on'
    # Normalize toggle
    normalize = request.args.get('normalize', default='off', type=str) == 'on'
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # --- Filter and Join Data ---
    df = df[df['Fund'] == selected_fund]
    if selected_type:
        # Join to get type for filtering
        df = df.merge(wsecs_static[['ISIN', 'Type']], on='ISIN', how='left')
        df = df[df['Type'] == selected_type]
    else:
        df = df.merge(wsecs_static[['ISIN', 'Type']], on='ISIN', how='left')

    # Date filtering/aggregation
    if mtd:
        # Get all dates in month up to selected_date
        if selected_date is pd.NaT:
            selected_date = max_date
        month_start = selected_date.replace(day=1)
        mtd_dates = pd.date_range(month_start, selected_date, freq='B')
        df = df[df['Date'].isin(mtd_dates)]
        # Fill missing days for each ISIN with zeros
        all_isins = df['ISIN'].unique()
        all_dates = mtd_dates
        idx = pd.MultiIndex.from_product([all_isins, all_dates], names=['ISIN', 'Date'])
        df = df.set_index(['ISIN', 'Date'])
        df = df.reindex(idx, fill_value=0).reset_index().merge(df.reset_index(), on=['ISIN', 'Date'], how='left', suffixes=('', '_orig'))
        # Use original columns where available, otherwise zeros
        for col in df.columns:
            if col.endswith('_orig'):
                base = col[:-5]
                df[base] = df[col].combine_first(df[base])
        # Aggregate (sum) over month for each ISIN
        group_cols = ['ISIN']
        # Only sum numeric columns, keep first for non-numeric
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        agg_dict = {col: 'sum' for col in numeric_cols if col not in group_cols}
        # For non-numeric columns (like 'Type', 'Security Name'), keep the first value
        for col in ['Type', 'Security Name']:
            if col in df.columns:
                agg_dict[col] = 'first'
        df = df.groupby(group_cols).agg(agg_dict).reset_index()
        # Add back static info
        df = df.merge(wsecs_static, on='ISIN', how='left')
    else:
        df = df[df['Date'] == selected_date]

    # --- Normalization ---
    if bench_or_port == 'bench':
        weight_col = 'Bench Weight'
        l0_col = 'L0 Bench Total Daily'
        l1_prefix = 'L2 Bench '
        l1_sp_prefix = 'SPv3_L2 Bench '
    else:
        weight_col = 'Port Exp Wgt'
        l0_col = 'L0 Port Total Daily '
        l1_prefix = 'L2 Port '
        l1_sp_prefix = 'SPv3_L2 Port '
    # L1 factor names
    l1_factors = [
        'Rates Carry Daily', 'Rates Convexity Daily', 'Rates Curve Daily', 'Rates Duration Daily', 'Rates Roll Daily',
        'Credit Spread Change Daily', 'Credit Convexity Daily', 'Credit Carry Daily', 'Credit Defaulted',
        'FX Carry Daily', 'FX Change Daily'
    ]
    # Residual calculation
    def calc_residual(row, l0, l1_prefix):
        l1_sum = sum([row.get(f'{l1_prefix}{f}', 0) for f in l1_factors])
        return row.get(l0, 0) - l1_sum
    # Normalization
    def norm(row, col, weight_col):
        w = row.get(weight_col, 0)
        v = row.get(col, 0)
        if normalize and w:
            return v / w
        return v
    # Prepare table rows
    table_rows = []
    for _, row in df.iterrows():
        returns = norm(row, l0_col, weight_col)
        orig_resid = calc_residual(row, l0_col, l1_prefix)
        sp_resid = calc_residual(row, l0_col, l1_sp_prefix)
        orig_resid = norm(row, None, weight_col) if normalize and weight_col else orig_resid
        sp_resid = norm(row, None, weight_col) if normalize and weight_col else sp_resid
        resid_diff = orig_resid - sp_resid
        l1_vals = {f: (norm(row, f'{l1_prefix}{f}', weight_col), norm(row, f'{l1_sp_prefix}{f}', weight_col)) for f in l1_factors}
        table_rows.append({
            'Security Name': row.get('Security Name', ''),
            'ISIN': row['ISIN'],
            'Type': row.get('Type', ''),
            'Returns': returns,
            'Original Residual': orig_resid,
            'S&P Residual': sp_resid,
            'Residual Diff': resid_diff,
            'L1 Values': l1_vals
        })
    # Sort by abs(Original Residual)
    table_rows = sorted(table_rows, key=lambda r: abs(r['Original Residual']), reverse=True)
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
            args['page'] = p
            return url_for('attribution_bp.attribution_security_page', **args)
    pagination = Pagination(page, per_page, total_items)
    return render_template(
        'attribution_security_page.html',
        rows=page_rows,
        pagination=pagination,
        available_funds=available_funds,
        selected_fund=selected_fund,
        available_types=available_types,
        selected_type=selected_type,
        selected_date=selected_date.strftime('%Y-%m-%d') if selected_date is not pd.NaT else '',
        bench_or_port=bench_or_port,
        mtd=mtd,
        normalize=normalize
    ) 