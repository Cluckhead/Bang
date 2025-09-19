"""
Security helpers
================
This module provides reusable helper functions used by the security-related
views (see `security_views.py`).  They cover exclusions loading, dataframe
filtering / sorting, pagination utilities and a CSV loader that extracts a
single security time-series from the long-format `sec_*.csv` files.

Extracting these helpers keeps `security_views.py` lean (<500 lines target)
and allows the same logic to be reused by other blueprints if required.
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any, Dict, Set, Tuple
import re

import numpy as np
import pandas as pd
from flask import current_app

from core import config
from analytics.security_processing import load_and_process_security_data
from core.utils import load_fund_groups, parse_fund_list
from views.exclusion_views import load_exclusions

__all__ = [
    "get_active_exclusions",
    "apply_security_filters",
    "apply_security_sorting",
    "paginate_security_data",
    "load_filter_and_extract",
]


def get_active_exclusions(data_folder_path: str) -> Set[str]:
    """Return currently *active* exclusions as a set of *SecurityID* strings.

    The helper wraps :pyfunc:`views.exclusion_views.load_exclusions` and
    filters the records so that only exclusions valid **today** are kept.
    """
    exclusions = load_exclusions(data_folder_path)
    active_exclusions: set[str] = set()
    today = datetime.now().date()

    for ex in exclusions:
        try:
            add_date = ex["AddDate"].date() if pd.notna(ex["AddDate"]) else None
            end_date = ex["EndDate"].date() if pd.notna(ex["EndDate"]) else None
            security_id = str(ex["SecurityID"])  # Ensure comparison as str

            if (
                add_date
                and add_date <= today
                and (end_date is None or end_date >= today)
            ):
                active_exclusions.add(security_id)
        except Exception as exc:  # pragma: no cover – defensive
            current_app.logger.error(
                "Error processing exclusion record %s: %s", ex, exc
            )

    current_app.logger.info("Found %d active exclusions", len(active_exclusions))
    return active_exclusions


# ---------------------------------------------------------------------------
# Dataframe utilities
# ---------------------------------------------------------------------------


def apply_security_filters(
    df: pd.DataFrame,
    id_col_name: str,
    search_term: str,
    fund_groups_dict: dict[str, list[str]],
    selected_fund_group: str | None,
    active_exclusion_ids: Set[str],
    active_filters: Dict[str, Any],
    exclude_min_zero: bool = True,
) -> pd.DataFrame:
    """Return *df* filtered according to the UI selections.

    This consolidates all filtering logic in a single place so it can be
    shared between summary routes and potential API endpoints.
    """

    filtered_df = df.copy()

    # ---- Fund-group filter ---------------------------------------------
    if selected_fund_group and selected_fund_group in fund_groups_dict:
        allowed_funds = set(fund_groups_dict[selected_fund_group])
        if config.FUNDS_COL in filtered_df.columns:
            filtered_df = filtered_df[
                filtered_df[config.FUNDS_COL].apply(
                    lambda x: (
                        any(f in allowed_funds for f in parse_fund_list(x))
                        if pd.notna(x)
                        else False
                    )
                )
            ]
        else:
            fund_col_candidates = [
                col
                for col in ["Fund", "Fund Code", config.CODE_COL]
                if col in filtered_df.columns
            ]
            if fund_col_candidates:
                fund_col = fund_col_candidates[0]
                filtered_df = filtered_df[filtered_df[fund_col].isin(allowed_funds)]

    # ---- Search-term filter ---------------------------------------------
    if search_term:
        filtered_df = filtered_df[
            filtered_df[id_col_name]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
        ]

    # ---- Active exclusions ----------------------------------------------
    if active_exclusion_ids:
        filtered_df = filtered_df[
            ~filtered_df[id_col_name].astype(str).isin(active_exclusion_ids)
        ]

    # ---- Dynamic column=value filters -----------------------------------
    for col, value in active_filters.items():
        if col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df[col].astype(str) == str(value)]

    # ---- Exclude Min==0 toggle ------------------------------------------
    if exclude_min_zero and "Min" in filtered_df.columns:
        filtered_df = filtered_df[~(filtered_df["Min"].fillna(0) == 0)]

    return filtered_df


def apply_security_sorting(
    df: pd.DataFrame,
    sort_by: str | None,
    sort_order: str,
    id_col_name: str,
) -> tuple[pd.DataFrame, str, str]:
    """Sort *df* according to UI parameters returning *(df, sort_by, sort_order)*."""

    temp_abs_col = "_abs_z_score_"

    # Validate sort_order first
    if sort_order not in {"asc", "desc"}:
        sort_order = "desc"

    effective_sort_by = sort_by
    is_default_sort = False

    if sort_by not in df.columns:
        # Fallback to absolute Z-score when Change Z-Score available
        if "Change Z-Score" in df.columns:
            df[temp_abs_col] = df["Change Z-Score"].fillna(0).abs()
            effective_sort_by = temp_abs_col
            if sort_by != "Change Z-Score":
                sort_order = "desc"
            is_default_sort = True
        else:
            # Final fallback = id column ascending
            effective_sort_by = id_col_name
            sort_order = "asc"

    ascending_order = sort_order == "asc"

    try:
        df.sort_values(
            by=effective_sort_by,
            ascending=ascending_order,
            inplace=True,
            na_position="last",
            key=lambda col: (
                col.astype(str).str.lower() if col.dtype == "object" else col
            ),
        )
    except Exception:  # pragma: no cover – best-effort fallback
        df.sort_values(by=id_col_name, ascending=True, inplace=True, na_position="last")
        effective_sort_by = id_col_name
        sort_order = "asc"

    if is_default_sort and temp_abs_col in df.columns:
        df.drop(columns=[temp_abs_col], inplace=True)
        effective_sort_by = "Change Z-Score"

    return df, effective_sort_by, sort_order


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def paginate_security_data(
    df: pd.DataFrame,
    page: int,
    per_page: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Slice *df* according to *page*/*per_page* returning (df_slice, ctx)."""

    safe_per_page = max(1, per_page)
    total_items = len(df)
    total_pages = max(1, math.ceil(total_items / safe_per_page))

    # Clamp page into valid range
    page = max(1, min(page, total_pages))

    start_index = (page - 1) * safe_per_page
    end_index = start_index + safe_per_page
    paginated_df = df.iloc[start_index:end_index]

    page_window = 2
    start_page_display = max(1, page - page_window)
    end_page_display = min(total_pages, page + page_window)

    pagination_ctx = {
        "page": page,
        "per_page": safe_per_page,
        "total_pages": total_pages,
        "total_items": total_items,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_num": page - 1,
        "next_num": page + 1,
        "start_page_display": start_page_display,
        "end_page_display": end_page_display,
    }

    return paginated_df, pagination_ctx


# ---------------------------------------------------------------------------
# File loader helper
# ---------------------------------------------------------------------------


def load_filter_and_extract(
    data_folder: str,
    filename: str,
    security_id_to_filter: str,
    id_column_name: str = "ISIN",
) -> Tuple[pd.Series | None, Set[pd.Timestamp], Dict[str, Any]]:
    """Load *filename*, filter on *security_id_to_filter* and return series.

    Returns a tuple *(series, dates, static_info)*.  On any error `None` and
    empty containers are returned to allow callers to continue gracefully.
    """

    current_app.logger.info("Loading file: %s", filename)
    filepath = os.path.join(data_folder, filename)
    if not os.path.exists(filepath):
        current_app.logger.warning("File not found – %s", filename)
        return None, set(), {}

    try:
        df_long, static_cols = load_and_process_security_data(filename, data_folder)
        if df_long is None or df_long.empty:
            current_app.logger.warning("No data loaded from %s", filename)
            return None, set(), {}

        # Ensure ID column is present (either column or index level)
        if (
            id_column_name not in df_long.index.names
            and id_column_name not in df_long.columns
        ):
            current_app.logger.error(
                "ID column '%s' not found in processed data from %s",
                id_column_name,
                filename,
            )
            fallback_id_col = df_long.index.name
            if fallback_id_col and fallback_id_col in df_long.index.names:
                id_column_name = fallback_id_col  # use actual index name
            else:
                return None, set(), {}

        # ---- Filter by security id (with base-ISIN fallback) ----------
        def _select_best_variant(df_subset: pd.DataFrame, value_col: str, level_name: str) -> pd.DataFrame:
            """Given rows for multiple ISIN variants, select the one with the most non-null values.
            Falls back to the first variant deterministically if tie/empty."""
            try:
                if df_subset.empty:
                    return df_subset
                if isinstance(df_subset.index, pd.MultiIndex):
                    level_idx = df_subset.index.names.index(level_name)
                    variant_ids = df_subset.index.get_level_values(level_idx)
                else:
                    variant_ids = df_subset.index
                # Build counts per variant
                counts = (
                    df_subset.assign(_variant=variant_ids)
                    .groupby("_variant")[value_col]
                    .apply(lambda s: s.notna().sum())
                    .sort_values(ascending=False)
                )
                best = counts.index[0] if len(counts) > 0 else None
                if best is None:
                    return df_subset
                if isinstance(df_subset.index, pd.MultiIndex):
                    return df_subset[variant_ids == best]
                return df_subset.loc[[best]]
            except Exception:
                return df_subset

        # Helper: attempt exact, then base-ISIN matching (handles hyphenated variants)
        def _filter_by_isin_with_fallback(df_src: pd.DataFrame, id_name: str, target_id: str) -> Tuple[pd.DataFrame, str]:
            base = re.sub(r"-\d+$", "", target_id or "")
            target_has_suffix = bool(re.search(r"-\d+$", target_id or ""))

            # Gather variant subset for this base (base and any -n variants)
            subset = df_src.iloc[0:0]
            if id_name == config.ISIN_COL and base:
                if id_name in df_src.index.names:
                    if isinstance(df_src.index, pd.MultiIndex):
                        lvl = df_src.index.names.index(id_name)
                        id_vals = df_src.index.get_level_values(lvl).astype(str)
                    else:
                        id_vals = df_src.index.astype(str)
                else:
                    id_vals = df_src[id_name].astype(str)
                mask = (id_vals == base) | id_vals.str.match(rf"^{re.escape(base)}-\d+$")
                subset = df_src[mask]

            # 1) If target includes a suffix, prefer exact variant if present
            if target_has_suffix:
                if id_name in df_src.index.names:
                    if isinstance(df_src.index, pd.MultiIndex):
                        lvl = df_src.index.names.index(id_name)
                        exact = df_src[df_src.index.get_level_values(lvl) == target_id]
                    else:
                        exact = df_src.loc[[target_id]] if target_id in df_src.index else df_src.iloc[0:0]
                else:
                    exact = df_src[df_src[id_name] == target_id]
                if not exact.empty:
                    return exact, id_name
                # Fallback to best among variants if exact missing
                if not subset.empty:
                    value_col = config.VALUE_COL if config.VALUE_COL in subset.columns else subset.columns.difference([id_name]).tolist()[0]
                    best = _select_best_variant(subset, value_col, id_name)
                    if not best.empty:
                        return best, id_name

            # 2) If target is base (or not suffixed), choose the best variant among all variants when available
            if not target_has_suffix and not subset.empty:
                value_col = config.VALUE_COL if config.VALUE_COL in subset.columns else subset.columns.difference([id_name]).tolist()[0]
                best = _select_best_variant(subset, value_col, id_name)
                if not best.empty:
                    return best, id_name

            # 3) Otherwise try exact match for non-ISIN IDs or when no variants present
            if id_name in df_src.index.names:
                if isinstance(df_src.index, pd.MultiIndex):
                    lvl = df_src.index.names.index(id_name)
                    exact = df_src[df_src.index.get_level_values(lvl) == target_id]
                else:
                    exact = df_src.loc[[target_id]] if target_id in df_src.index else df_src.iloc[0:0]
            else:
                exact = df_src[df_src[id_name] == target_id]
            if not exact.empty:
                return exact, id_name

            # 4) Final fallback: try Security Name equality (legacy)
            alt_id_col = config.SEC_NAME_COL
            if id_name == config.ISIN_COL and alt_id_col in df_src.columns:
                alt = df_src[df_src[alt_id_col] == target_id]
                if not alt.empty:
                    return alt, alt_id_col
            return df_src.iloc[0:0], id_name

        # Execute filtering with fallback
        if id_column_name in df_long.index.names:
            if isinstance(df_long.index, pd.MultiIndex):
                # No direct filtering here; use helper to handle all cases uniformly
                filtered_df, id_column_name = _filter_by_isin_with_fallback(
                    df_long, id_column_name, security_id_to_filter
                )
            else:
                filtered_df, id_column_name = _filter_by_isin_with_fallback(
                    df_long, id_column_name, security_id_to_filter
                )
        else:
            filtered_df, id_column_name = _filter_by_isin_with_fallback(
                df_long, id_column_name, security_id_to_filter
            )

        if filtered_df.empty:
            current_app.logger.warning(
                "No data found for %s='%s' in %s (after base-ISIN fallback)",
                id_column_name,
                security_id_to_filter,
                filename,
            )
            return None, set(), {}

        value_col_name = config.VALUE_COL
        if value_col_name not in filtered_df.columns:
            potential_value_cols = [
                col
                for col in filtered_df.columns
                if col not in static_cols and col != id_column_name
            ]
            if potential_value_cols:
                value_col_name = potential_value_cols[0]
                current_app.logger.info("Using '%s' as value column", value_col_name)
            else:
                current_app.logger.error(
                    "Could not determine value column in %s", filename
                )
                return None, set(), {}

        # Ensure 'Date' is the index
        if config.DATE_COL in filtered_df.columns:
            filtered_df = filtered_df.set_index(config.DATE_COL)
        elif not isinstance(filtered_df.index, pd.DatetimeIndex):
            if config.DATE_COL in filtered_df.index.names:
                filtered_df = filtered_df.reset_index().set_index(config.DATE_COL)
            else:
                current_app.logger.error(
                    "Cannot find '%s' in %s", config.DATE_COL, filename
                )
                return None, set(), {}

        data_series = filtered_df[value_col_name].sort_index()
        dates: set[pd.Timestamp] = set(data_series.index)

        # Static info (take first row)
        local_static_info: dict[str, Any] = {}
        relevant_static_cols = [
            col
            for col in static_cols
            if col in filtered_df.columns and col != id_column_name
        ]
        if not filtered_df.empty and relevant_static_cols:
            first_row = filtered_df.iloc[0]
            local_static_info = {
                col: first_row[col]
                for col in relevant_static_cols
                if pd.notna(first_row[col])
            }

        return data_series, dates, local_static_info

    except Exception as exc:  # pragma: no cover – diagnostics
        current_app.logger.error("Error processing file %s: %s", filename, exc)
        return None, set(), {}
