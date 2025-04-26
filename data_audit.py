# data_audit.py
"""
Purpose: Implements the Data Consistency Audit for the Simple Data Checker application.

This module provides a function to check:
  1. That all ts_*.csv and sp_ts_*.csv files cover the same date range.
  2. That all sec_*.csv files cover the same date range.
  3. That all funds are present for all dates in every ts_*.csv and sp_ts_*.csv file.
  4. That files do not contain blank lines, blank columns, missing headers, or only headers (no data rows).

The audit is designed to be triggered from the /get_data page and returns a structured report for display in the UI.

Usage:
    from data_audit import run_data_consistency_audit
    report = run_data_consistency_audit(data_folder)
"""
import os
import pandas as pd
import logging
from typing import Dict, Any, List
from collections import defaultdict

logger = logging.getLogger(__name__)

def run_data_consistency_audit(data_folder: str) -> Dict[str, Any]:
    """
    Enhanced: Runs a data consistency audit on ts_*, sp_ts_*, and sec_* files in the given data folder.
    Returns a structured report dictionary summarizing findings, with detailed file diagnostics and recommendations.
    """
    report = {
        'ts_files': {},
        'sp_ts_files': {},
        'sec_files': {},
        'structure_issues': [],
        'summary': [],
        'file_details': {},  # New: detailed info per file
        'scanned_files': [],
        'skipped_files': [],
        'recommendations': []
    }

    def find_files(prefix: str) -> List[str]:
        return [f for f in os.listdir(data_folder) if f.startswith(prefix) and f.endswith('.csv')]

    # Helper: get file size in human-readable format (no external dependencies)
    def get_file_size(path):
        try:
            size = os.path.getsize(path)
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} PB"
        except Exception:
            return 'N/A'

    # List of additional key files to always check (regardless of prefix)
    key_files = [
        'w_Bench.csv', 'w_Funds.csv', 'w_secs.csv', 'att_factors.csv', 'curves.csv'
    ]
    # Map of file name to format: 'wide' (dates as columns) or 'long' (date in a column)
    key_file_formats = {
        'w_Bench.csv': 'wide',
        'w_Funds.csv': 'wide',
        'w_secs.csv': 'wide',
        'att_factors.csv': 'auto',  # Try both
        'curves.csv': 'long',
    }

    # --- Scan all files and collect details ---
    all_prefixes = ['ts_', 'sp_ts_', 'sec_']
    already_scanned = set()
    for prefix in all_prefixes:
        files = find_files(prefix)
        for fname in files:
            already_scanned.add(fname)
            fpath = os.path.join(data_folder, fname)
            file_info = {
                'file': fname,
                'prefix': prefix,
                'size': get_file_size(fpath),
                'columns': [],
                'date_columns': [],
                'fund_column': None,
                'n_rows': None,
                'n_cols': None,
                'first_rows': [],
                'issues': [],
                'date_range': None,  # New: store date range here
            }
            try:
                df = pd.read_csv(fpath)
                file_info['columns'] = list(df.columns)
                file_info['n_rows'] = len(df)
                file_info['n_cols'] = len(df.columns)
                file_info['fund_column'] = df.columns[0] if len(df.columns) > 0 else None
                # --- For ts_*.csv and sp_ts_*.csv: date is in a column (long format) ---
                if prefix in ['ts_', 'sp_ts_']:
                    date_col = None
                    for col in df.columns:
                        if col.strip().lower() in ['position date', 'date']:
                            date_col = col
                            break
                    if date_col:
                        dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                        if not dates.empty:
                            file_info['date_range'] = (str(dates.min()), str(dates.max()))
                        else:
                            file_info['issues'].append(f"Could not parse any valid dates in column '{date_col}'")
                            file_info['date_range'] = None
                    else:
                        file_info['issues'].append("No date column found (expected e.g. 'Position Date' or 'Date')")
                        file_info['date_range'] = None
                # --- For sec_*.csv: date columns are columns (wide format) ---
                elif prefix == 'sec_':
                    file_info['date_columns'] = [col for col in df.columns if _is_date_like(col)]
                    if file_info['date_columns']:
                        date_cols_sorted = sorted(file_info['date_columns'])
                        file_info['date_range'] = (date_cols_sorted[0], date_cols_sorted[-1])
                    else:
                        file_info['issues'].append('No date columns detected')
                        file_info['date_range'] = None
                if file_info['n_rows'] == 0:
                    file_info['issues'].append('File contains only header, no data rows')
                    report['recommendations'].append(
                        f"File {fname}: Only header, no data rows. Recommendation: Check file export process."
                    )
                for idx, col in enumerate(file_info['columns']):
                    if not str(col).strip():
                        file_info['issues'].append(f'Blank column header at position {idx+1}')
                        report['recommendations'].append(
                            f"File {fname}: Blank column header at position {idx+1}. Recommendation: Remove empty columns."
                        )
                for col in df.columns:
                    if df[col].isna().all():
                        file_info['issues'].append(f'Column "{col}" is entirely blank')
                        report['recommendations'].append(
                            f"File {fname}: Column '{col}' is entirely blank. Recommendation: Remove or fill this column."
                        )
            except Exception as e:
                file_info['issues'].append(f'Error reading file: {e}')
                report['recommendations'].append(
                    f"File {fname}: Could not be read. Error: {e}. Recommendation: Check file format and encoding."
                )
            report['file_details'][fname] = file_info
            report['scanned_files'].append(fname)

    # --- Scan key files (by name) ---
    for fname in key_files:
        if fname in already_scanned:
            continue
        fpath = os.path.join(data_folder, fname)
        file_info = {
            'file': fname,
            'prefix': 'key',
            'size': get_file_size(fpath),
            'columns': [],
            'date_columns': [],
            'fund_column': None,
            'n_rows': None,
            'n_cols': None,
            'first_rows': [],
            'issues': [],
            'date_range': None,
        }
        try:
            df = pd.read_csv(fpath)
            file_info['columns'] = list(df.columns)
            file_info['n_rows'] = len(df)
            file_info['n_cols'] = len(df.columns)
            file_info['fund_column'] = df.columns[0] if len(df.columns) > 0 else None
            fmt = key_file_formats.get(fname, 'auto')
            if fmt == 'wide':
                file_info['date_columns'] = [col for col in df.columns if _is_date_like(col)]
                if file_info['date_columns']:
                    date_cols_sorted = sorted(file_info['date_columns'])
                    file_info['date_range'] = (date_cols_sorted[0], date_cols_sorted[-1])
                else:
                    file_info['issues'].append('No date columns detected')
                    file_info['date_range'] = None
            elif fmt == 'long':
                date_col = None
                for col in df.columns:
                    if col.strip().lower() in ['position date', 'date']:
                        date_col = col
                        break
                if date_col:
                    dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                    if not dates.empty:
                        file_info['date_range'] = (str(dates.min()), str(dates.max()))
                    else:
                        file_info['issues'].append(f"Could not parse any valid dates in column '{date_col}'")
                        file_info['date_range'] = None
                else:
                    file_info['issues'].append("No date column found (expected e.g. 'Position Date' or 'Date')")
                    file_info['date_range'] = None
            else:  # auto: try wide, then long
                # Try wide
                file_info['date_columns'] = [col for col in df.columns if _is_date_like(col)]
                if file_info['date_columns']:
                    date_cols_sorted = sorted(file_info['date_columns'])
                    file_info['date_range'] = (date_cols_sorted[0], date_cols_sorted[-1])
                else:
                    # Try long
                    date_col = None
                    for col in df.columns:
                        if col.strip().lower() in ['position date', 'date']:
                            date_col = col
                            break
                    if date_col:
                        dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                        if not dates.empty:
                            file_info['date_range'] = (str(dates.min()), str(dates.max()))
                        else:
                            file_info['issues'].append(f"Could not parse any valid dates in column '{date_col}'")
                            file_info['date_range'] = None
                    else:
                        file_info['issues'].append("No date column found (expected e.g. 'Position Date' or 'Date')")
                        file_info['date_range'] = None
            if file_info['n_rows'] == 0:
                file_info['issues'].append('File contains only header, no data rows')
                report['recommendations'].append(
                    f"File {fname}: Only header, no data rows. Recommendation: Check file export process."
                )
            for idx, col in enumerate(file_info['columns']):
                if not str(col).strip():
                    file_info['issues'].append(f'Blank column header at position {idx+1}')
                    report['recommendations'].append(
                        f"File {fname}: Blank column header at position {idx+1}. Recommendation: Remove empty columns."
                    )
            for col in df.columns:
                if df[col].isna().all():
                    file_info['issues'].append(f'Column "{col}" is entirely blank')
                    report['recommendations'].append(
                        f"File {fname}: Column '{col}' is entirely blank. Recommendation: Remove or fill this column."
                    )
        except Exception as e:
            file_info['issues'].append(f'Error reading file: {e}')
            report['recommendations'].append(
                f"File {fname}: Could not be read. Error: {e}. Recommendation: Check file format and encoding."
            )
        report['file_details'][fname] = file_info
        report['scanned_files'].append(fname)

    # --- 1. Date Range Consistency for ts_*.csv and sp_ts_*.csv and key files ---
    for prefix, key in [('ts_', 'ts_files'), ('sp_ts_', 'sp_ts_files'), ('sec_', 'sec_files')]:
        files = find_files(prefix)
        date_ranges = {}
        for fname in files:
            info = report['file_details'].get(fname, {})
            drange = info.get('date_range', None)
            if drange:
                date_ranges[fname] = drange
            else:
                if prefix == 'sec_':
                    report['structure_issues'].append({'file': fname, 'issue': 'No date columns detected'})
        unique_ranges = set(date_ranges.values())
        report[key]['date_ranges'] = date_ranges
        report[key]['all_match'] = len(unique_ranges) == 1 and len(unique_ranges) > 0
        report[key]['unique_ranges'] = list(unique_ranges)

    # --- 1b. Date Range Consistency for key files ---
    key_date_ranges = {}
    for fname in key_files:
        info = report['file_details'].get(fname, {})
        drange = info.get('date_range', None)
        if drange:
            key_date_ranges[fname] = drange
    # Optionally, you could group these by format or type for mismatch highlighting
    report['key_files'] = {
        'date_ranges': key_date_ranges,
        'all_match': len(set(key_date_ranges.values())) == 1 and len(key_date_ranges) > 0,
        'unique_ranges': list(set(key_date_ranges.values())),
    }

    # --- 2. Fund Presence Consistency for ts_*.csv and sp_ts_*.csv ---
    for prefix, key in [('ts_', 'ts_files'), ('sp_ts_', 'sp_ts_files')]:
        files = find_files(prefix)
        all_funds = set()
        fund_presence = {}
        all_dates = set()
        for fname in files:
            info = report['file_details'].get(fname, {})
            try:
                df = pd.read_csv(os.path.join(data_folder, fname))
                fund_col = info.get('fund_column')
                if not fund_col or fund_col not in df.columns:
                    fund_presence[fname] = [{'issue': 'No fund column detected'}]
                    continue
                funds = set(df[fund_col].dropna().astype(str))
                all_funds.update(funds)
                date_cols = info.get('date_columns', [])
                all_dates.update(date_cols)
                missing = []
                for date in date_cols:
                    funds_with_data = set(df.loc[~df[date].isna(), fund_col].astype(str))
                    missing_funds = all_funds - funds_with_data
                    if missing_funds:
                        missing.append({'date': date, 'missing_funds': list(missing_funds)})
                fund_presence[fname] = missing
            except Exception as e:
                fund_presence[fname] = [{'issue': f'Error checking fund presence: {e}'}]
        report[key]['fund_presence_issues'] = fund_presence

    # --- 3. File Structure Sanity Checks (already included above) ---
    # --- 4. Summary ---
    report['summary'].append({'check': 'ts_*.csv date ranges match', 'result': report['ts_files']['all_match']})
    report['summary'].append({'check': 'sp_ts_*.csv date ranges match', 'result': report['sp_ts_files']['all_match']})
    report['summary'].append({'check': 'sec_*.csv date ranges match', 'result': report['sec_files']['all_match']})
    for key in ['ts_files', 'sp_ts_files']:
        fund_issues = report[key].get('fund_presence_issues', {})
        any_issues = any(fund_issues.values())
        report['summary'].append({'check': f'{key} fund presence', 'result': not any_issues})
    report['summary'].append({'check': 'File structure issues', 'result': len(report['structure_issues']) == 0})

    # --- 5. Skipped files (non-matching prefix) ---
    all_files = set(os.listdir(data_folder))
    matched = set(report['scanned_files'])
    skipped = [f for f in all_files if f.endswith('.csv') and f not in matched]
    report['skipped_files'] = skipped

    return report

def _is_date_like(s: str) -> bool:
    """Heuristic to check if a string looks like a date column (YYYY-MM-DD, DD/MM/YYYY, etc.)."""
    import re
    s = s.strip()
    # Accepts YYYY-MM-DD, DD/MM/YYYY, YYYY-MM-DDTHH:MM:SS, etc.
    date_patterns = [
        r'^\d{4}-\d{2}-\d{2}$',
        r'^\d{2}/\d{2}/\d{4}$',
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    ]
    return any(re.match(p, s) for p in date_patterns) 