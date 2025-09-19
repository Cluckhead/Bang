#!/usr/bin/env python
# file_delivery_processing.py
# Purpose: Provide reusable functions to monitor file delivery health for files that share a common
#          naming pattern (e.g. <Name>_YYYYMMDD.csv).  It captures simple *meta* information about
#          each file – rows, columns, completeness %, column headers, modification timestamps –
#          and persists that information to a rolling CSV log (`filedelivery.log`).
#          The log is then used by the Flask views to create a dashboard showing the latest file
#          vs the previous one, flagging unusual changes (row-count deltas, header changes, etc.)
#          and to power a time-series modal going back 30 days.
#
# This module is **data-agnostic** – it does *not* parse business content – only structural aspects.

import os
import csv
import glob
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any

import pandas as pd

from core.utils import load_yaml_config
from core.settings_loader import get_file_delivery_monitors
from core import config

LOGGER = logging.getLogger(__name__)

# Constants
DEFAULT_CONFIG_PATH = os.path.join("config", "file_delivery.yaml")
DEFAULT_LOG_PATH = "filedelivery.log"  # project root

# --------------------------------------------------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------------------------------------------------

def _hash_headers(headers: List[str]) -> str:
    """Return a short hash of the column header list so we can detect changes quickly."""
    joined = "|".join(headers)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def _compute_completeness(df: pd.DataFrame) -> float:
    """Return overall completeness percentage (non-null cells / total cells)."""
    total_cells = df.size
    if total_cells == 0:
        return 0.0
    non_null = df.notna().sum().sum()
    return round(non_null / total_cells * 100, 2)


def _safe_read_csv(path: str, max_rows: int = None) -> pd.DataFrame:
    """Read a CSV robustly with pandas, optionally limiting rows to minimise memory usage."""
    try:
        df = pd.read_csv(path, low_memory=False, nrows=max_rows)
        return df
    except Exception as exc:
        LOGGER.error("Failed to read %s – %s", path, exc, exc_info=True)
        return pd.DataFrame()

# --------------------------------------------------------------------------------------------------------------------
# Core processing
# --------------------------------------------------------------------------------------------------------------------

def load_monitors(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Dict[str, Any]]:
    """Load the monitors from settings. Returns an empty dict if missing/invalid."""
    monitors = get_file_delivery_monitors()
    if not monitors:
        LOGGER.warning("No monitors found in settings")
        return {}
    return monitors


def _parse_file_date(file_path: str, cfg: Dict[str, Any]) -> str | None:
    """Return ISO date string extracted per config (or None)."""
    date_cfg = cfg.get("date_parse", {}) if cfg else {}
    source = date_cfg.get("source", "filename")
    try:
        if source == "mtime":
            ts = os.path.getmtime(file_path)
            return datetime.fromtimestamp(ts).date().isoformat()
        else:  # filename
            regex = date_cfg.get("regex")
            fmt = date_cfg.get("format")
            if regex and fmt:
                import re
                m = re.search(regex, os.path.basename(file_path))
                if m:
                    return datetime.strptime(m.group(1), fmt).date().isoformat()
            # fallback old logic: look for last _YYYYMMDD
            parts = os.path.splitext(os.path.basename(file_path))[0].split("_")
            maybe_date = parts[-1]
            if maybe_date.isdigit() and len(maybe_date) >= 8:
                try:
                    return datetime.strptime(maybe_date[:8], "%Y%m%d").date().isoformat()
                except Exception:
                    return None
    except Exception:
        return None


def gather_file_meta(monitor_name: str, file_path: str, monitor_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a dict of meta information for the specified file."""
    try:
        stat = os.stat(file_path)
        modified_ts = datetime.fromtimestamp(stat.st_mtime)
        df_head = _safe_read_csv(file_path)  # read full file – we need row/col counts & completeness
        line_count = len(df_head)
        column_headers = list(df_head.columns)
        columns_hash = _hash_headers(column_headers)
        completeness_pct = _compute_completeness(df_head)
        date_in_name = _parse_file_date(file_path, monitor_cfg)

        return {
            "monitor": monitor_name,
            "filename": os.path.basename(file_path),
            "file_path": file_path,
            "file_date": date_in_name,
            "rows": line_count,
            "cols": len(column_headers),
            "completeness_pct": completeness_pct,
            "headers_hash": columns_hash,
            "headers": "|".join(column_headers),
            "modified_ts": modified_ts.isoformat(timespec="seconds"),
            "processed_ts": datetime.now().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        LOGGER.error("Error gathering meta for %s – %s", file_path, exc, exc_info=True)
        return {}


def _load_log(log_path: str = DEFAULT_LOG_PATH) -> pd.DataFrame:
    if not os.path.exists(log_path):
        return pd.DataFrame()
    try:
        return pd.read_csv(log_path)
    except Exception as exc:
        LOGGER.error("Failed to read log %s – %s", log_path, exc, exc_info=True)
        return pd.DataFrame()


def _append_log(row: Dict[str, Any], log_path: str = DEFAULT_LOG_PATH) -> None:
    file_exists = os.path.isfile(log_path)
    try:
        with open(log_path, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as exc:
        LOGGER.error("Failed to append to log %s – %s", log_path, exc, exc_info=True)


def update_log(monitors: Dict[str, Dict[str, Any]], log_path: str = DEFAULT_LOG_PATH) -> None:
    """Walk through configured monitors, compute meta for newest file (and any unseen ones), and update log."""
    existing = _load_log(log_path)
    for name, cfg in monitors.items():
        directory = cfg.get("directory")
        pattern = cfg.get("pattern")
        if not directory or not pattern:
            LOGGER.warning("Monitor %s missing directory/pattern", name)
            continue
        dir_path = (
            directory
            if os.path.isabs(directory)
            else os.path.join(config.BASE_DIR, directory)
        )
        glob_expr = os.path.join(dir_path, pattern)
        
        # Get all matching files and sort by modification time (newest first)
        all_files = glob.glob(glob_expr)
        all_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        
        # Limit to maximum of 30 files per monitor
        max_files = cfg.get("max_files", 30)  # Allow override in config, default to 30
        files_to_process = all_files[:max_files]
        
        if len(all_files) > max_files:
            LOGGER.info("Monitor %s: Processing %d most recent files out of %d total files found", 
                       name, max_files, len(all_files))
        
        for file_path in files_to_process:
            meta = gather_file_meta(name, file_path, cfg)
            if not meta:
                continue
            if not existing.empty:
                mask = (
                    (existing["monitor"] == name)
                    & (existing["filename"] == meta["filename"])
                    & (existing["modified_ts"] == meta["modified_ts"])
                )
                if mask.any():
                    continue  # already recorded
            _append_log(meta, log_path)


# --------------------------------------------------------------------------------------------------------------------
# Public API for the views
# --------------------------------------------------------------------------------------------------------------------

def get_latest_and_previous(monitor_name: str, log_path: str = DEFAULT_LOG_PATH) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (latest_row, previous_row) for a monitor; rows are dicts or None."""
    df = _load_log(log_path)
    if df.empty:
        return None, None
    df_m = df[df["monitor"] == monitor_name].copy()
    if df_m.empty:
        return None, None
    # Sort by processed_ts (iso format string – okay lexicographically) and take last two
    df_m.sort_values(by="processed_ts", inplace=True)
    latest = df_m.iloc[-1].to_dict()
    prev = df_m.iloc[-2].to_dict() if len(df_m) >= 2 else None
    return latest, prev


def build_dashboard_summary(monitors: Dict[str, Dict[str, Any]], log_path: str = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    """Return a list of summary dicts for each monitor for dashboard display."""
    summaries: List[Dict[str, Any]] = []
    for name, cfg in monitors.items():
        display_name = cfg.get("display_name", name)
        latest, prev = get_latest_and_previous(name, log_path)
        if latest is None:
            summaries.append(
                {
                    "monitor": name,
                    "display_name": display_name,
                    "status": "missing",
                    "message": "No log entries yet.",
                }
            )
            continue
        # Compute deltas
        delta_rows = None
        delta_completeness = None
        if prev is not None:
            try:
                delta_rows = int(latest["rows"]) - int(prev["rows"])
            except Exception:
                delta_rows = None
            try:
                delta_completeness = round(float(latest["completeness_pct"]) - float(prev["completeness_pct"]), 2)
            except Exception:
                delta_completeness = None
        header_changed = prev is not None and latest.get("headers_hash") != prev.get(
            "headers_hash"
        )
        summaries.append(
            {
                "monitor": name,
                "display_name": display_name,
                "latest_file": latest["filename"],
                "file_date": latest.get("file_date"),
                "latest_rows": latest["rows"],
                "delta_rows": delta_rows,
                "header_changed": header_changed,
                "completeness_pct": latest["completeness_pct"],
                "delta_completeness": delta_completeness,
            }
        )
    return summaries


def get_time_series(monitor_name: str, days: int = 30, log_path: str = DEFAULT_LOG_PATH) -> pd.DataFrame:
    """Return DataFrame of log entries for a monitor limited to *days* back (based on processed_ts)."""
    df = _load_log(log_path)
    if df.empty:
        return pd.DataFrame()
    df_m = df[df["monitor"] == monitor_name].copy()
    if df_m.empty:
        return pd.DataFrame()
    df_m["processed_ts_dt"] = pd.to_datetime(df_m["processed_ts"], errors="coerce")
    cutoff = datetime.now() - timedelta(days=days)
    df_m = df_m[df_m["processed_ts_dt"] >= cutoff]
    df_m.sort_values(by="processed_ts_dt", inplace=True)
    return df_m

# --------------------------------------------------------------------------------------------------------------------
# Column completeness helpers (on-demand, for modal)
# --------------------------------------------------------------------------------------------------------------------

def _column_completeness(df: pd.DataFrame) -> Dict[str, float]:
    """Return completeness % per column."""
    result = {}
    if df is None or df.empty:
        return result
    total_rows = len(df)
    for col in df.columns:
        non_null = df[col].notna().sum()
        pct = round(non_null / total_rows * 100, 2) if total_rows else 0.0
        result[col] = pct
    return result

def get_column_completeness_comparison(
    monitor_name: str, log_path: str = DEFAULT_LOG_PATH
) -> List[Dict[str, Any]]:
    """Return list of {column, latest_pct, prev_pct, delta} for given monitor.
    Empty list if insufficient history.
    """
    latest, prev = get_latest_and_previous(monitor_name, log_path)
    if not latest or not prev:
        return []

    try:
        latest_df = _safe_read_csv(latest["file_path"])
        prev_df = _safe_read_csv(prev["file_path"])

        latest_comp = _column_completeness(latest_df)
        prev_comp = _column_completeness(prev_df)

        ordered_cols = list(latest_df.columns) + [c for c in prev_df.columns if c not in latest_df.columns]

        # Determine id_column for equality checks from YAML
        monitors_cfg = load_monitors()
        monitor_cfg = monitors_cfg.get(monitor_name, {}) if monitors_cfg else {}
        id_col = monitor_cfg.get("id_column")
        if id_col is None or id_col not in latest_df.columns or id_col not in prev_df.columns:
            id_col = None  # disable identical count if not present

        rows = []
        for col in ordered_cols:
            l_pct = latest_comp.get(col)
            p_pct = prev_comp.get(col)
            delta = None
            if l_pct is not None and p_pct is not None:
                delta = round(l_pct - p_pct, 2)

            identical_count = None
            if id_col and col in latest_df.columns and col in prev_df.columns:
                try:
                    latest_map = latest_df.set_index(id_col)[col]
                    prev_map = prev_df.set_index(id_col)[col]
                    joined = latest_map.to_frame('latest').join(prev_map.to_frame('prev'), how='inner')
                    identical_mask = (joined['latest'] == joined['prev']) | (joined['latest'].isna() & joined['prev'].isna())
                    total = len(identical_mask)
                    if total > 0:
                        identical_count = round(identical_mask.sum() / total * 100, 2)
                    else:
                        identical_count = None
                except Exception:
                    identical_count = None

            rows.append(
                {
                    "column": col,
                    "latest": l_pct,
                    "prev": p_pct,
                    "delta": delta,
                    "identical_pct": identical_count,
                }
            )
        return rows
    except Exception as exc:
        LOGGER.error("Error computing column completeness comparison for %s: %s", monitor_name, exc, exc_info=True)
        return [] 