# Purpose: Verify that synth_sec_*.csv outputs match a provided comprehensive analytics CSV.
# Loads each synthetic metric (ZSpread, GSpread, YTM, durations, convexity, OAS) from Data,
# aligns with the comprehensive CSV (expected in long format: ISIN, Date, metric columns),
# and reports mismatch counts within a numeric tolerance.

from __future__ import annotations

import argparse
import os
from typing import Dict, List, Tuple

import pandas as pd


METRIC_FILE_MAP: Dict[str, str] = {
    "ZSpread": "synth_sec_ZSpread.csv",
    "GSpread": "synth_sec_GSpread.csv",
    "YTM": "synth_sec_YTM.csv",
    "EffectiveDuration": "synth_sec_EffectiveDuration.csv",
    "ModifiedDuration": "synth_sec_ModifiedDuration.csv",
    "Convexity": "synth_sec_Convexity.csv",
    "SpreadDuration": "synth_sec_SpreadDuration.csv",
    "OAS": "synth_sec_OAS.csv",
}

# Default scale factors to align units (1.0 means same units in both files)
# Adjust if your comprehensive file uses different units.
DEFAULT_SCALES: Dict[str, float] = {
    "ZSpread": 1.0,       # bps in synth; set to 10000.0 if comprehensive uses decimal
    "GSpread": 1.0,       # bps in synth; set to 10000.0 if decimal
    "YTM": 1.0,           # percent in synth; set to 100.0 if decimal
    "EffectiveDuration": 1.0,
    "ModifiedDuration": 1.0,
    "Convexity": 1.0,
    "SpreadDuration": 1.0,
    "OAS": 1.0,           # bps in synth; set to 10000.0 if decimal
}

META_COLS = {"ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"}


def parse_scale_overrides(scale_str: str | None) -> Dict[str, float]:
    if not scale_str:
        return {}
    scales: Dict[str, float] = {}
    for pair in scale_str.split(","):
        if not pair:
            continue
        key, _, val = pair.partition(":")
        key = key.strip()
        if not _:
            continue
        try:
            scales[key] = float(val)
        except ValueError:
            raise ValueError(f"Invalid scale value for {key}: {val}")
    return scales


def melt_synth_wide_to_long(df: pd.DataFrame) -> pd.DataFrame:
    meta_cols_present = [c for c in df.columns if c in META_COLS]
    date_cols = [c for c in df.columns if c not in meta_cols_present]
    long_df = df.melt(id_vars=meta_cols_present, value_vars=date_cols, var_name="Date", value_name="Value")
    # Normalise date to ISO yyyy-mm-dd where possible; leave as-is otherwise
    try:
        parsed = pd.to_datetime(long_df["Date"], dayfirst=False, errors="coerce")
        fallback = pd.to_datetime(long_df.loc[parsed.isna(), "Date"], dayfirst=True, errors="coerce")
        parsed.loc[parsed.isna()] = fallback
        long_df["Date"] = parsed.dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    long_df = long_df[["ISIN", "Date", "Value"]]
    return long_df


def load_synth_metric_long(data_dir: str, metric: str) -> pd.DataFrame:
    path = os.path.join(data_dir, METRIC_FILE_MAP[metric])
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing synth file for {metric}: {path}")
    df = pd.read_csv(path)
    return melt_synth_wide_to_long(df)


def load_comprehensive_long(comp_path: str, metrics: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_csv(comp_path)
    # Try to detect long format: presence of a date-like column
    date_col = None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("date", "position date", "position_date"):
            date_col = c
            break
    if date_col is None:
        raise ValueError(
            "Comprehensive CSV must be in long format with a 'Date' column (e.g., Date/Position Date)."
        )

    # Normalise Date to ISO string
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    fallback = pd.to_datetime(df.loc[parsed.isna(), date_col], dayfirst=True, errors="coerce")
    parsed.loc[parsed.isna()] = fallback
    df["Date"] = parsed.dt.strftime("%Y-%m-%d")

    # Identify which metric columns exist
    present_metrics = [m for m in metrics if m in df.columns]
    if not present_metrics:
        raise ValueError(
            f"None of the expected metric columns were found in {comp_path}. "
            f"Expected any of: {metrics}"
        )

    # Keep only required cols
    keep = [c for c in ("ISIN", "Date") if c in df.columns] + present_metrics
    return df[keep].copy(), present_metrics


def compare_metric(
    synth_long: pd.DataFrame, comp_long: pd.DataFrame, metric: str, scale: float, tolerance: float
) -> Dict[str, int | float]:
    # Extract metric column as Value for comprehensive
    comp_metric = comp_long[[c for c in comp_long.columns if c in ("ISIN", "Date", metric)]].copy()
    comp_metric = comp_metric.rename(columns={metric: "Value"})

    # Inner join on ISIN, Date
    merged = synth_long.merge(comp_metric, on=["ISIN", "Date"], suffixes=("_synth", "_comp"))

    # Apply scale to comprehensive to align units to synth
    merged["Value_comp_scaled"] = merged["Value_comp"] * scale

    # Compute difference where both are numeric
    diffs = (merged["Value_synth"].astype(float) - merged["Value_comp_scaled"].astype(float)).abs()
    mismatches = (diffs > tolerance) & (~merged["Value_synth"].isna()) & (~merged["Value_comp_scaled"].isna())

    total_pairs = int(len(merged))
    mismatch_count = int(mismatches.sum())

    return {
        "pairs_compared": total_pairs,
        "mismatches": mismatch_count,
        "mismatch_pct": (mismatch_count / total_pairs * 100.0) if total_pairs else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify synth_sec_*.csv against comprehensive analytics CSV")
    parser.add_argument("comp_file", help="Path to comprehensive analytics CSV (long format: ISIN, Date, metric columns)")
    parser.add_argument("--data-dir", default="Data", help="Folder containing synth_sec_*.csv (default: Data)")
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=list(METRIC_FILE_MAP.keys()),
        help=f"Metrics to compare (default: {list(METRIC_FILE_MAP.keys())})",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="Absolute tolerance for comparison after scaling (default: 1e-6)",
    )
    parser.add_argument(
        "--scale",
        default=None,
        help="Override scales as comma-separated pairs, e.g. 'ZSpread:10000,GSpread:10000,YTM:100'",
    )

    args = parser.parse_args()

    scales = DEFAULT_SCALES.copy()
    scales.update(parse_scale_overrides(args.scale))

    comp_long, present_metrics = load_comprehensive_long(args.comp_file, args.metrics)

    print(f"Comprehensive file: {args.comp_file}")
    print(f"Data dir: {os.path.abspath(args.data_dir)}")
    print(f"Metrics requested: {args.metrics}")
    print(f"Metrics present in comprehensive: {present_metrics}")
    print(f"Tolerance: {args.tolerance}")
    print(f"Scales: { {m: scales.get(m, 1.0) for m in present_metrics} }")
    print()

    grand_total = 0
    grand_mismatches = 0

    for metric in present_metrics:
        try:
            synth_long = load_synth_metric_long(args.data_dir, metric)
        except FileNotFoundError as e:
            print(f"[SKIP] {metric}: {e}")
            continue

        result = compare_metric(synth_long, comp_long, metric, scales.get(metric, 1.0), args.tolerance)
        grand_total += result["pairs_compared"]
        grand_mismatches += result["mismatches"]

        print(
            f"{metric}: compared={result['pairs_compared']}, mismatches={result['mismatches']} "
            f"({result['mismatch_pct']:.4f}%)"
        )

    print()
    if grand_total:
        pct = grand_mismatches / grand_total * 100.0
    else:
        pct = 0.0
    print(f"Overall: compared={grand_total}, mismatches={grand_mismatches} ({pct:.4f}%)")


if __name__ == "__main__":
    main()
