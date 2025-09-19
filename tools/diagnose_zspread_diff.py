# Purpose: Diagnose z-spread discrepancies between `synth_spread_calculator.py` and `synth_analytics_csv_processor.py`.
# Compares the exact inputs (curves, cashflows, compounding, dirty price) fed into SpreadOMatic for the same ISIN/date.

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import sys

# Ensure project root is on sys.path so we can import top-level packages like `analytics`
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Local imports
from analytics.synth_spread_calculator import (
    build_zero_curve,
    generate_payment_schedule,
    get_supported_day_basis,
    parse_date_robust,
    get_base_isin,
)
from analytics import synth_analytics_csv_processor as sa


# SpreadOMatic core
from tools.SpreadOMatic.spreadomatic.daycount import to_datetime
from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows
from tools.SpreadOMatic.spreadomatic.yield_spread import z_spread
from tools.SpreadOMatic.spreadomatic.yield_spread import g_spread as g_spread_fn
from tools.SpreadOMatic.spreadomatic.duration import effective_duration as eff_dur_fn
from tools.SpreadOMatic.spreadomatic.duration import modified_duration as sm_modified_duration


# Compounding preference used by bond_calculation (to match synth_spread_calculator)
try:
    from bond_calculation.config import COMPOUNDING as COMPOUNDING_PREF  # type: ignore
except Exception:
    COMPOUNDING_PREF = "semiannual"


@dataclass
class PipelineInputs:
    isin: str
    date: str
    currency: str
    dirty_price: float
    compounding: str
    z_times: List[float]
    z_rates: List[float]
    times: List[float]
    cfs: List[float]


def _first_non_null_price_row(price_df: pd.DataFrame, date_col: str) -> List[int]:
    mask = price_df[date_col].notna() & (price_df[date_col].astype(str).str.strip().str.lower().isin({"n/a", "na", "", "null", "none"}) == False)
    return list(price_df[mask].index)


def _load_dataframes(data_folder: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_df = pd.read_csv(os.path.join(data_folder, "sec_Price.csv"))
    schedule_df = pd.read_csv(os.path.join(data_folder, "schedule.csv"))
    curves_df = pd.read_csv(os.path.join(data_folder, "curves.csv"))
    reference_path = os.path.join(data_folder, "reference.csv")
    reference_df = pd.read_csv(reference_path) if os.path.exists(reference_path) else pd.DataFrame()
    # Normalize ISINs
    if "ISIN" in price_df.columns:
        price_df["ISIN"] = price_df["ISIN"].astype(str).str.strip().str.upper()
    if "ISIN" in schedule_df.columns:
        schedule_df["ISIN"] = schedule_df["ISIN"].astype(str).str.strip().str.upper()
    if not reference_df.empty and "ISIN" in reference_df.columns:
        reference_df["ISIN"] = reference_df["ISIN"].astype(str).str.strip().str.upper()
    return price_df, schedule_df, curves_df, reference_df


def _merge_coupon_into_schedule(schedule_df: pd.DataFrame, reference_df: pd.DataFrame) -> pd.DataFrame:
    if schedule_df is None or schedule_df.empty:
        return schedule_df
    if reference_df is None or reference_df.empty or "Coupon Rate" not in reference_df.columns:
        return schedule_df
    # If schedule already has Coupon Rate column but with NaNs, we'll still try to fill
    merged = schedule_df.copy()
    try:
        ref = reference_df[["ISIN", "Coupon Rate"]].copy()
        # Exact ISIN merge
        merged = merged.merge(ref, on="ISIN", how="left", suffixes=("", "_ref"))
        # Prefer schedule coupon if present, else use reference
        if "Coupon Rate" in schedule_df.columns:
            merged["Coupon Rate"] = merged["Coupon Rate"].fillna(merged["Coupon Rate_ref"])  # type: ignore
            merged.drop(columns=[c for c in ["Coupon Rate_ref"] if c in merged.columns], inplace=True)
        else:
            merged.rename(columns={"Coupon Rate_ref": "Coupon Rate"}, inplace=True)

        # Base ISIN merge for still-missing coupons (handles hyphenated suffix)
        if merged["Coupon Rate"].isna().any():
            try:
                merged["__ISIN_BASE"] = merged["ISIN"].apply(get_base_isin)
                ref2 = ref.copy()
                ref2["__ISIN_BASE"] = ref2["ISIN"].apply(get_base_isin)
                merged = merged.merge(
                    ref2[["__ISIN_BASE", "Coupon Rate"]].rename(columns={"Coupon Rate": "Coupon Rate_base"}),
                    on="__ISIN_BASE",
                    how="left",
                )
                merged["Coupon Rate"] = merged["Coupon Rate"].fillna(merged["Coupon Rate_base"])  # type: ignore
                merged.drop(columns=[c for c in ["Coupon Rate_base", "__ISIN_BASE"] if c in merged.columns], inplace=True)
            except Exception:
                pass
        return merged
    except Exception:
        return schedule_df


def _accrued_lookup_from_matrix(accrued_df: Optional[pd.DataFrame]) -> Optional[callable]:
    if accrued_df is None or accrued_df.empty:
        return None

    def _lookup(isin_val: str, date_str: str) -> float:
        try:
            row = accrued_df[accrued_df["ISIN"] == isin_val]
            if row.empty:
                return 0.0
            if date_str in accrued_df.columns:
                val = row.iloc[0][date_str]
                return float(val) if pd.notna(val) else 0.0
            return 0.0
        except Exception:
            return 0.0

    return _lookup


def build_inputs_pipeline_spread_calculator(
    price_row: pd.Series,
    schedule_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    curves_df: pd.DataFrame,
    accrued_df: Optional[pd.DataFrame],
    date_col: str,
) -> Optional[PipelineInputs]:
    isin = str(price_row["ISIN"]).strip()
    currency = price_row.get("Currency", "USD")
    price = float(price_row[date_col])

    # Ensure coupon rates present like synth_spread_calculator merging logic
    schedule_aug = _merge_coupon_into_schedule(schedule_df, reference_df=pd.DataFrame())
    schedule_match = schedule_aug[schedule_aug["ISIN"] == isin]
    if schedule_match.empty:
        return None
    schedule_row = schedule_match.iloc[0]

    # Merge coupon into schedule like production path does
    schedule_aug = _merge_coupon_into_schedule(schedule_df, reference_df)
    schedule_match = schedule_aug[schedule_aug["ISIN"] == isin]

    # Accrued lookup
    accrued_lookup = _accrued_lookup_from_matrix(accrued_df) if accrued_df is not None else None
    accrued_interest = 0.0
    if accrued_lookup is not None:
        try:
            accrued_interest = float(accrued_lookup(isin, date_col))
        except Exception:
            accrued_interest = float(schedule_row.get("Accrued Interest", 0.0) or 0.0)
    else:
        accrued_interest = float(schedule_row.get("Accrued Interest", 0.0) or 0.0)

    dirty_price = price + accrued_interest

    # Zero curve
    z_times, z_rates, _ = build_zero_curve(curves_df, currency, date_col)

    # Payment schedule and cashflows
    day_basis_raw = schedule_row.get("Day Basis", "30/360")
    day_basis = get_supported_day_basis(day_basis_raw)
    payment_schedule = generate_payment_schedule(schedule_row)

    val_dt_parsed = parse_date_robust(date_col, dayfirst=True)
    val_dt = to_datetime(val_dt_parsed.strftime("%Y-%m-%d"))

    times, cfs = extract_cashflows(payment_schedule, val_dt, z_times, z_rates, day_basis)

    return PipelineInputs(
        isin=isin,
        date=date_col,
        currency=currency,
        dirty_price=dirty_price,
        compounding=COMPOUNDING_PREF,
        z_times=z_times,
        z_rates=z_rates,
        times=times,
        cfs=cfs,
    )


def build_inputs_pipeline_analytics_csv(
    price_row: pd.Series,
    latest_date: str,
    schedule_df: Optional[pd.DataFrame],
    reference_df: Optional[pd.DataFrame],
    curves_df: Optional[pd.DataFrame],
    accrued_df: Optional[pd.DataFrame],
) -> Optional[PipelineInputs]:
    isin = str(price_row["ISIN"]).strip()
    currency = price_row.get("Currency", "USD")
    price = float(price_row[latest_date])

    # Pull schedule/reference rows
    schedule_row = None
    if schedule_df is not None and not schedule_df.empty:
        m = schedule_df[schedule_df["ISIN"] == isin]
        if not m.empty:
            schedule_row = m.iloc[0]

    reference_row = None
    if reference_df is not None and not reference_df.empty:
        m = reference_df[reference_df["ISIN"] == isin]
        if not m.empty:
            reference_row = m.iloc[0]

    # Combined data (replicates analytics CSV pipeline)
    combined = sa._combine_security_data(price_row, reference_row, schedule_row, latest_date)

    # Curves
    z_times, z_rates = sa._parse_curve_data(curves_df, currency, latest_date)

    # Accrued interest
    accrued_interest = sa._get_accrued_interest(isin, latest_date, accrued_df)
    dirty_price = price + accrued_interest

    # Cashflows
    valuation_date = to_datetime(latest_date)
    times, cfs = sa._build_cashflows_from_combined_data(
        combined, valuation_date, price_row, schedule_row, z_times, z_rates
    )

    # Compounding in analytics CSV depends on coupon frequency
    coupon_freq = int(combined.get("Coupon Frequency", 2))
    comp = "semiannual" if coupon_freq == 2 else "annual"

    return PipelineInputs(
        isin=isin,
        date=latest_date,
        currency=currency,
        dirty_price=dirty_price,
        compounding=comp,
        z_times=z_times,
        z_rates=z_rates,
        times=times,
        cfs=cfs,
    )


def compute_zspread(pi: PipelineInputs) -> float:
    if not pi.times or not pi.cfs:
        return float("nan")
    return float(z_spread(pi.dirty_price, pi.times, pi.cfs, pi.z_times, pi.z_rates, comp=pi.compounding))


def compute_gspread(pi: PipelineInputs) -> float:
    if not pi.times or not pi.cfs:
        return float("nan")
    maturity = max(pi.times)
    # g_spread returns decimal
    return float(g_spread_fn(compute_ytm(pi), maturity, pi.z_times, pi.z_rates))


def compute_ytm(pi: PipelineInputs) -> float:
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm
    return float(solve_ytm(pi.dirty_price, pi.times, pi.cfs, comp=pi.compounding))


def compute_mod_duration(pi: PipelineInputs) -> float:
    if not pi.times or not pi.cfs:
        return float("nan")
    # Effective duration first
    eff = float(eff_dur_fn(pi.dirty_price, pi.times, pi.cfs, pi.z_times, pi.z_rates, comp=pi.compounding))
    ytm = compute_ytm(pi)
    # Mirror synth_spread_calculator logic
    if pi.compounding == 'semiannual':
        return eff / (1 + ytm / 2)
    elif pi.compounding == 'annual':
        return eff / (1 + ytm)
    elif pi.compounding == 'continuous':
        return eff
    elif pi.compounding == 'monthly':
        return eff / (1 + ytm / 12)
    else:
        # Fallback with frequency=2 (semiannual) if unknown
        return float(sm_modified_duration(eff, ytm, frequency=2))


def compute_effective_duration(pi: PipelineInputs) -> float:
    if not pi.times or not pi.cfs:
        return float("nan")
    return float(eff_dur_fn(pi.dirty_price, pi.times, pi.cfs, pi.z_times, pi.z_rates, comp=pi.compounding))


def summarize_diff(a: PipelineInputs, b: PipelineInputs) -> Dict[str, Any]:
    def _arr(a1: List[float]) -> np.ndarray:
        return np.array(a1, dtype=float)

    # Curves
    curve_len_diff = (len(a.z_times), len(b.z_times))
    curve_rate_diff = float("nan")
    if len(a.z_rates) and len(b.z_rates):
        min_len = min(len(a.z_rates), len(b.z_rates))
        if min_len:
            curve_rate_diff = float(np.nanmean(np.abs(_arr(a.z_rates[:min_len]) - _arr(b.z_rates[:min_len]))))

    # Cashflows
    cf_len_diff = (len(a.times), len(b.times))
    cf_amt_diff = float("nan")
    if len(a.cfs) and len(b.cfs):
        min_len_cf = min(len(a.cfs), len(b.cfs))
        if min_len_cf:
            cf_amt_diff = float(np.nanmean(np.abs(_arr(a.cfs[:min_len_cf]) - _arr(b.cfs[:min_len_cf]))))

    return {
        "compounding_sc": a.compounding,
        "compounding_csv": b.compounding,
        "dirty_price_sc": a.dirty_price,
        "dirty_price_csv": b.dirty_price,
        "curve_points": curve_len_diff,
        "avg_curve_rate_abs_diff": curve_rate_diff,
        "cashflow_points": cf_len_diff,
        "avg_cashflow_abs_diff": cf_amt_diff,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose z-spread input differences between two pipelines")
    parser.add_argument("--data", dest="data_folder", default=None, help="Path to Data folder (defaults to core settings or ./Data)")
    parser.add_argument("--limit", dest="limit", type=int, default=5, help="Number of securities to analyze")
    args = parser.parse_args()

    # Resolve data folder
    data_folder = args.data_folder
    if not data_folder:
        try:
            from core.settings_loader import get_app_config  # type: ignore

            app_cfg = get_app_config() or {}
            dfolder = app_cfg.get("data_folder") or "Data"
            data_folder = dfolder if os.path.isabs(dfolder) else os.path.join(os.path.dirname(__file__), "..", dfolder)
        except Exception:
            data_folder = os.path.join(os.path.dirname(__file__), "..", "Data")

    data_folder = os.path.abspath(data_folder)

    # Load data
    latest_date, price_df_latest = sa.get_latest_date_from_csv(data_folder)
    if latest_date is None or price_df_latest is None:
        print("Could not determine latest date or load prices")
        return

    price_df, schedule_df, curves_df, reference_df = _load_dataframes(data_folder)

    # Optional accrued
    accrued_path = os.path.join(data_folder, "sec_accrued.csv")
    accrued_df = pd.read_csv(accrued_path) if os.path.exists(accrued_path) else None

    # Select rows with price for latest_date
    idxs = _first_non_null_price_row(price_df, latest_date)[: args.limit]
    if not idxs:
        print(f"No non-null prices found for {latest_date}")
        return

    print(f"Analyzing {len(idxs)} securities for {latest_date} in {data_folder}\n")
    for i in idxs:
        row = price_df.loc[i]
        isin = str(row["ISIN"]).strip()

        a = build_inputs_pipeline_spread_calculator(row, schedule_df, reference_df, curves_df, accrued_df, latest_date)
        b = build_inputs_pipeline_analytics_csv(row, latest_date, schedule_df, reference_df, curves_df, accrued_df)

        if a is None or b is None:
            print(f"ISIN {isin}: missing inputs in one of the pipelines; skipping\n")
            continue

        z_a = compute_zspread(a)
        z_b = compute_zspread(b)
        g_a = compute_gspread(a)
        g_b = compute_gspread(b)
        md_a = compute_mod_duration(a)
        md_b = compute_mod_duration(b)
        ed_a = compute_effective_duration(a)
        ed_b = compute_effective_duration(b)
        diff = summarize_diff(a, b)

        print(f"ISIN: {isin}")
        print(f"  Z-Spread (bps): SC={z_a*10000:.3f}  CSV={z_b*10000:.3f}  diff_bps={(z_a - z_b)*10000:.3f}")
        print(f"  G-Spread (bps): SC={g_a*10000:.3f}  CSV={g_b*10000:.3f}  diff_bps={(g_a - g_b)*10000:.3f}")
        print(f"  EffDuration:    SC={ed_a:.6f}       CSV={ed_b:.6f}       diff={ed_a - ed_b:.6f}")
        print(f"  ModDuration:    SC={md_a:.6f}       CSV={md_b:.6f}       diff={md_a - md_b:.6f}")
        print(f"  Dirty price: SC={a.dirty_price:.6f} CSV={b.dirty_price:.6f}")
        print(f"  Compounding: SC={a.compounding} CSV={b.compounding}")
        print(
            f"  Curve points: SC={diff['curve_points'][0]} CSV={diff['curve_points'][1]} | avg |Δrate|={diff['avg_curve_rate_abs_diff']:.8f}"
        )
        print(
            f"  Cashflow points: SC={diff['cashflow_points'][0]} CSV={diff['cashflow_points'][1]} | avg |Δcf|={diff['avg_cashflow_abs_diff']:.8f}"
        )
        # Show a few curve and cashflow samples
        def _head(xs: List[float], n: int = 3) -> List[float]:
            return [float(f"{x:.6f}") for x in xs[:n]]
        print(f"  SC curve times head: {_head(a.z_times)} rates head: {_head(a.z_rates)}")
        print(f"  CSV curve times head: {_head(b.z_times)} rates head: {_head(b.z_rates)}")
        print(f"  SC cashflow times: {_head(a.times, 5)} amounts: {_head(a.cfs, 5)}")
        print(f"  CSV cashflow times: {_head(b.times, 5)} amounts: {_head(b.cfs, 5)}")
        print("")


if __name__ == "__main__":
    main()


