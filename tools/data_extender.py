"""
# data_extender.py — Scale sample CSVs to production-like size
#
# Purpose:
#   This script reads the existing CSV data files under the Data/ directory, then
#   procedurally generates additional securities, fund holdings, and time-series
#   values so that the dataset approximates a full production environment
#   (~3 500 bonds, 30 funds, 10 currencies).  All high-level parameters and
#   column headers live in an external YAML file (see
#   config/data_extender_settings.yaml).  Re-run the script any time you want to
#   regenerate or tweak the synthetic data.
#
# Typical usage (PowerShell):
#   python tools/data_extender.py -s config/data_extender_settings.yaml
#
# The utility deliberately keeps the logic simple and reproducible:
#   1. Counts current unique ISINs in reference.csv
#   2. Generates new ISINs up to the target count (3 500)
#   3. Distributes ISINs across funds (IG01-IG30) with 100-300 bonds each
#   4. Creates pre_sec_*.csv files with time series data for each metric
#   5. Creates pre_w_*.csv files with weight data
#   6. Creates ts_*.csv files with fund-level time series
#   7. Creates att_factors_*.csv files with attribution data
#   8. Backs up originals before overwriting
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import yaml
from datetime import datetime, timedelta
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extend sample CSV data to production scale"
    )
    parser.add_argument(
        "-s",
        "--settings",
        required=True,
        help="Path to YAML settings file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )
    return parser.parse_args()


def load_settings(settings_path):
    """Load configuration from YAML file."""
    with open(settings_path, "r") as f:
        return yaml.safe_load(f)


def backup_file(filepath):
    """Create a backup of the file if it exists."""
    if os.path.exists(filepath):
        backup_path = filepath + ".bak"
        shutil.copy2(filepath, backup_path)
        print(f"  Backed up: {filepath} -> {backup_path}")


def generate_isin():
    """Generate a realistic-looking ISIN code."""
    # Country codes for variety
    countries = ["XS", "US", "GB", "DE", "FR", "CH", "JP", "AU", "CA", "SE"]
    country = np.random.choice(countries)
    
    # Generate 10 random digits
    digits = "".join([str(np.random.randint(0, 10)) for _ in range(10)])
    
    return f"{country}{digits}"


def extend_reference(settings, data_dir, dry_run=False):
    """Extend reference.csv to target number of securities."""
    ref_path = os.path.join(data_dir, settings["file_globs"]["reference"])
    
    # Read existing reference data
    if os.path.exists(ref_path):
        ref_df = pd.read_csv(ref_path)
        existing_isins = set(ref_df["ISIN"].unique())
        print(f"Found {len(existing_isins)} existing ISINs in reference.csv")
    else:
        ref_df = pd.DataFrame()
        existing_isins = set()
        print("No existing reference.csv found, creating new one")
    
    target_count = settings["securities"]["num_total"]
    to_generate = target_count - len(existing_isins)
    
    if to_generate <= 0:
        print(f"Already have {len(existing_isins)} ISINs, target is {target_count}")
        return ref_df
    
    print(f"Generating {to_generate} new ISINs...")
    
    # Generate new ISINs
    new_isins = set()
    while len(new_isins) < to_generate:
        isin = generate_isin()
        if isin not in existing_isins and isin not in new_isins:
            new_isins.add(isin)
    
    # Create new rows for reference.csv (security static data only)
    currencies = settings["securities"]["currencies"]
    rng = np.random.RandomState(settings["random_seed"])
    
    new_rows = []
    for i, isin in enumerate(new_isins):
        # Generate security static data
        security_number = len(existing_isins) + i + 1
        security_name = f"Security_{security_number:04d}"
        
        # Random attributes
        currency = rng.choice(currencies)
        rating = rng.choice(["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "B"])
        sector = rng.choice(["Banking", "Industrials", "Utilities", "Consumer", "Technology", "Healthcare", "Energy", "Materials"])
        sub_type = rng.choice(["Corp", "MBS", "Govt Bond", "ABS", "Municipal"])
        country = rng.choice(["United States", "Germany", "United Kingdom", "France", "Japan", "Canada", "Australia", "Switzerland"])
        ticker = rng.choice(["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"])
        
        new_rows.append({
            "ISIN": isin,
            "Security Name": security_name,
            "BBG ID": f"BBG{isin[-10:]}",
            "Security Sub Type": sub_type,
            "SS Project - In Scope": str(rng.choice([True, False])),
            "Is Distressed": str(rng.choice([True, False])),
            "BBG Ticker Yellow": f"{isin} {sub_type}",
            "Rating": rating,
            "BBG LEVEL 3": sector,
            "Position Currency": currency,
            "Country Of Risk": country,
            "Call Indicator": str(rng.choice([True, False])),
            "Make Whole Call": str(rng.choice([True, False])),
            "Coupon Rate": round(rng.uniform(1, 8), 1),
            "Maturity Date": (datetime.now() + timedelta(days=rng.randint(365, 10950))).strftime("%Y-%m-%dT%H:%M:%S"),
            "Ticker": ticker
        })
    
    # Combine with existing data
    new_df = pd.DataFrame(new_rows)
    combined_df = pd.concat([ref_df, new_df], ignore_index=True)
    
    if not dry_run:
        backup_file(ref_path)
        combined_df.to_csv(ref_path, index=False)
        print(f"Updated reference.csv: {len(ref_df)} -> {len(combined_df)} rows")
    else:
        print(f"Would update reference.csv: {len(ref_df)} -> {len(combined_df)} rows")
    
    return combined_df


def extend_pre_sec_files(settings, data_dir, reference_df, weight_df, dry_run=False):
    """Create or extend pre_sec_*.csv files in long format for ALL securities in reference.csv."""
    print("\nExtending pre_sec_*.csv files...")

    if reference_df is None or reference_df.empty:
        print("  No reference data provided – skipping pre_sec generation.")
        return

    # Get fund assignments from weight_df to determine which funds each security appears in
    fund_isin_map = {}
    if weight_df is not None and not weight_df.empty:
        for (isin, fund), group in weight_df.groupby(["ISIN", "Funds"]):
            if isin not in fund_isin_map:
                fund_isin_map[isin] = []
            fund_isin_map[isin].append(fund)
    
    # Date range
    start_date = pd.to_datetime(settings["time_series"]["start_date"])
    end_date = pd.to_datetime(settings["time_series"]["end_date"])
    date_range = pd.date_range(start_date, end_date, freq='D')
    
    rng = np.random.RandomState(settings["random_seed"])
    
    # Metrics and their value ranges for random walk initialization
    metrics = {
        "YTM": {"start_range": (2.0, 6.0), "volatility": 0.02},
        "YTMSP": {"start_range": (2.0, 6.0), "volatility": 0.02},
        "YTW": {"start_range": (1.8, 5.8), "volatility": 0.02},
        "YTWSP": {"start_range": (1.8, 5.8), "volatility": 0.02},
        "Price": {"start_range": (95.0, 105.0), "volatility": 0.5},
        "Spread": {"start_range": (50, 300), "volatility": 2.0},
        "SpreadSP": {"start_range": (50, 300), "volatility": 2.0},
        "duration": {"start_range": (3.0, 8.0), "volatility": 0.05},
        "durationSP": {"start_range": (3.0, 8.0), "volatility": 0.05},
        "Spread Duration": {"start_range": (3.0, 8.0), "volatility": 0.05},
        "Spread DurationSP": {"start_range": (3.0, 8.0), "volatility": 0.05}
    }
    
    for metric, params in metrics.items():
        filename = f"pre_sec_{metric}.csv"
        filepath = os.path.join(data_dir, filename)
        
        print(f"  Processing {filename}")
        
        # Generate data for ALL securities in reference.csv for ALL dates
        all_rows = []

        for isin in reference_df["ISIN"].unique():
            # Get funds for this ISIN from weight data
            isin_funds = fund_isin_map.get(isin, [])
            
            # If ISIN has no fund assignments, assign to a default fund
            if not isin_funds:
                isin_funds = [settings["funds"]["codes"][0]]  # Default to first fund
            
            for fund in isin_funds:
                # Create a random walk for this ISIN/Fund combination across ALL dates
                start_value = rng.uniform(params["start_range"][0], params["start_range"][1])
                current_value = start_value

                for date in date_range:
                    # Random walk step
                    current_value += rng.normal(0, params["volatility"])

                    # Clip values to reasonable ranges
                    if metric in ["YTM", "YTMSP", "YTW", "YTWSP", "duration", "durationSP", "Spread duration", "Spread durationSP"]:
                        current_value = max(0.1, current_value)
                    elif metric in ["Spread", "SpreadSP"]:
                        current_value = max(10, current_value)
                    elif metric == "Price":
                        current_value = max(50, min(150, current_value))

                    fund_value = current_value + rng.normal(0, params["volatility"] * 0.1)

                    all_rows.append({
                        "ISIN": isin,
                        "Funds": fund,
                        "Date": date.strftime("%Y-%m-%d"),
                        "Value": round(fund_value, 4)
                    })
        
        # Create DataFrame
        new_df = pd.DataFrame(all_rows)
        
        if not dry_run:
            backup_file(filepath)
            new_df.to_csv(filepath, index=False)
            print(f"    Created {filename}: {len(new_df)} rows")
        else:
            print(f"    Would create {filename}: {len(new_df)} rows")


# ---------------------------------------------------------------------------
#  Pre-W (weights) generation – now produces *long-format* ISIN/Fund/Date/Value
#  with purchase + sale logic:
#     • 3 % of bonds are *bought* during the period (start weight = 0 then >0)
#     • Each day a held position has a 0.5 % chance of being *sold* (weight→0)
#     • Once sold, it cannot be bought again.
# ---------------------------------------------------------------------------


def extend_pre_w_files(settings, data_dir, reference_df, dry_run=False):
    """Create or extend pre_w_*.csv files.

    Returns
    -------
    pd.DataFrame
        The long-format `pre_w_secs` dataframe (ISIN, Funds, Date, Value) so
        that downstream generators (pre_sec_*) can respect the holding
        periods.
    """
    print("\nExtending pre_w_*.csv files...")

    rng = np.random.RandomState(settings["random_seed"])

    # --- Setup -------------------------------------------------------------
    date_range = pd.date_range(
        pd.to_datetime(settings["time_series"]["start_date"]),
        pd.to_datetime(settings["time_series"]["end_date"]),
        freq="D",
    )

    # Universe of securities and funds
    unique_isins = reference_df["ISIN"].unique()
    funds = settings["funds"]["codes"]

    # Allocate bonds per fund respecting min/max bounds --------------------
    min_per = settings["funds"]["bonds_per_fund"]["min"]
    max_per = settings["funds"]["bonds_per_fund"]["max"]

    fund_isin_combos = []
    remaining_isins = list(unique_isins)
    rng.shuffle(remaining_isins)

    for fund in funds:
        # Pick target number
        target_n = rng.randint(min_per, max_per + 1)
        # Sample without replacement; if not enough left, recycle pool
        if target_n > len(remaining_isins):
            remaining_isins = list(unique_isins)
            rng.shuffle(remaining_isins)
        chosen = remaining_isins[:target_n]
        remaining_isins = remaining_isins[target_n:]
        fund_isin_combos.extend([(fund, isin) for isin in chosen])

    # Optional overlap: add additional random combos so some bonds in 2-5 funds
    additional_ratio = 0.15  # 15 % extra combos for overlap
    extra_n = int(len(fund_isin_combos) * additional_ratio)
    for _ in range(extra_n):
        isin = rng.choice(unique_isins)
        fund = rng.choice(funds)
        fund_isin_combos.append((fund, isin))

    # Determine which combos are “late purchases” (3 %)
    num_late = int(len(fund_isin_combos) * 0.03)
    late_purchase_idxs = set(rng.choice(len(fund_isin_combos), size=num_late, replace=False))

    weight_rows = []

    for idx, (fund, isin) in enumerate(fund_isin_combos):
        base_weight = rng.uniform(0.005, 0.02)  # 0.5 % – 2 %

        # Purchase day
        if idx in late_purchase_idxs:
            purchase_date_idx = rng.randint(1, len(date_range))  # not day 0
        else:
            purchase_date_idx = 0  # held from day 0

        sold = False

        for d_idx, date in enumerate(date_range):
            if sold or d_idx < purchase_date_idx:
                weight_val = 0.0
            else:
                # Currently held
                weight_val = base_weight * rng.uniform(0.9, 1.1)

                # 0.5 % chance per day to sell (per requirement)
                if rng.rand() < 0.005:
                    sold = True  # future days will be 0
            weight_rows.append(
                {
                    "ISIN": isin,
                    "Funds": fund,
                    "Date": date.strftime("%Y-%m-%d"),
                    "Value": round(weight_val * 100, 6)  # store as percent (0-100)
                }
            )

    pre_w_secs_df = pd.DataFrame(weight_rows)

    # Write to disk ---------------------------------------------------------
    pre_w_secs_path = os.path.join(data_dir, "pre_w_secs.csv")
    if not dry_run:
        backup_file(pre_w_secs_path)
        pre_w_secs_df.to_csv(pre_w_secs_path, index=False)
        print(f"  Created pre_w_secs.csv: {len(pre_w_secs_df)} rows")
    else:
        print(f"  Would create pre_w_secs.csv: {len(pre_w_secs_df)} rows")

    # --- pre_w_fund & pre_w_bench (static) --------------------------------
    pre_w_fund_path = os.path.join(data_dir, "pre_w_fund.csv")
    pre_w_bench_path = os.path.join(data_dir, "pre_w_bench.csv")

    fund_weights = []
    total_weight = 100.0
    remaining = len(funds)
    for i, fund in enumerate(funds):
        if i == len(funds) - 1:
            wt = round(total_weight, 2)
        else:
            wt = round(rng.uniform(1, min(10, total_weight - remaining + 1)), 2)
            total_weight -= wt
            remaining -= 1
        fund_weights.append({"Fund": fund, "Weight": wt})

    fund_df = pd.DataFrame(fund_weights)
    if not dry_run:
        backup_file(pre_w_fund_path)
        backup_file(pre_w_bench_path)
        fund_df.to_csv(pre_w_fund_path, index=False)
        fund_df.to_csv(pre_w_bench_path, index=False)
        print("  Created pre_w_fund.csv & pre_w_bench.csv")

    return pre_w_secs_df


# ---------------------------------------------------------------------------
#  KRD generation (pre_KRD.csv & pre_KRDSP.csv)
# ---------------------------------------------------------------------------


def extend_pre_krd_files(settings, data_dir, reference_df, dry_run=False):
    """Generate pre_KRD.csv (and SP overlay) with tenor buckets per security in reference.csv."""

    print("\nExtending pre_KRD files...")

    if reference_df is None or reference_df.empty:
        print("  No reference data provided – skipping KRD generation.")
        return

    rng = np.random.RandomState(settings["random_seed"])

    date_range = pd.date_range(
        pd.to_datetime(settings["time_series"]["start_date"]),
        pd.to_datetime(settings["time_series"]["end_date"]),
        freq="D",
    )

    # New tenor structure as requested: 1M, 3M, 6M, 1Y, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y, 20Y, 30Y, 50Y
    tenors = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "20Y", "30Y", "50Y"]

    # Get all unique ISINs from reference data
    unique_isins = reference_df["ISIN"].unique()

    rows = []
    for isin in unique_isins:
        # Base level for this security to keep curves somewhat stable
        base = rng.uniform(0.01, 0.05)  # 1–5 bps for 1M

        for date in date_range:
            curve = {}
            prev = base
            for t in tenors:
                # Random incremental increase + noise
                increment = rng.uniform(0.0005, 0.002)  # 0.05–0.2 bps per step
                val = max(0.0, prev + increment + rng.normal(0, 0.0005))
                curve[f"KRD - {t}"] = round(val, 6)  # Add KRD prefix to column name
                prev = val

            rows.append({
                "ISIN": isin,
                "Date": date.strftime("%d/%m/%Y"),  # match sample dd/mm/yyyy
                **curve,
            })

    if not rows:
        print("  No KRD rows generated.")
        return

    krd_df = pd.DataFrame(rows)

    pre_krd_path = os.path.join(data_dir, "pre_KRD.csv")
    if not dry_run:
        backup_file(pre_krd_path)
        krd_df.to_csv(pre_krd_path, index=False)
        print(f"  Created pre_KRD.csv: {len(krd_df)} rows")
    else:
        print(f"  Would create pre_KRD.csv: {len(krd_df)} rows")

    # SP overlay with ±2 % noise
    krd_sp = krd_df.copy()
    for t in tenors:
        krd_col = f"{t} - KRD"
        krd_sp[krd_col] = (krd_sp[krd_col] * (1 + rng.normal(0, 0.02, size=len(krd_sp)))).round(6)

    pre_krdsp_path = os.path.join(data_dir, "pre_KRDSP.csv")
    if not dry_run:
        backup_file(pre_krdsp_path)
        krd_sp.to_csv(pre_krdsp_path, index=False)
        print(f"  Created pre_KRDSP.csv: {len(krd_sp)} rows")
    else:
        print(f"  Would create pre_KRDSP.csv: {len(krd_sp)} rows")


def extend_ts_files(settings, data_dir, dry_run=False):
    """Create or extend ts_*.csv time series files."""
    print("\nExtending ts_*.csv files...")
    
    # Date range from settings
    start_date = pd.to_datetime(settings["time_series"]["start_date"])
    end_date = pd.to_datetime(settings["time_series"]["end_date"])
    date_range = pd.date_range(start_date, end_date, freq='D')
    
    rng = np.random.RandomState(settings["random_seed"])
    
    for metric in settings["time_series"]["metrics"]:
        filename = f"ts_{metric}.csv"
        filepath = os.path.join(data_dir, filename)
        
        # Check existing file structure
        if os.path.exists(filepath):
            sample_df = pd.read_csv(filepath, nrows=10)
            columns = sample_df.columns.tolist()
        else:
            # Default columns based on sample files
            columns = ["Position Date", "Fund Code", "SS Project - In Scope", 
                      f"Fund {metric}", f"Benchmark {metric}"]
        
        print(f"  Processing {filename}")
        
        rows = []
        for date in date_range:
            for fund in settings["funds"]["codes"]:
                # Create rows for both TRUE and FALSE "SS Project - In Scope"
                for in_scope in [True, False]:
                    row = {
                        "Position Date": date.strftime("%Y-%m-%dT%H:%M:%S"),
                        "Fund Code": fund,
                        "SS Project - In Scope": str(in_scope).upper()
                    }
                    
                    # Generate metric values
                    if metric == "Spread":
                        base_fund = rng.uniform(100, 400)
                        base_bench = base_fund + rng.normal(0, 10)
                    elif metric == "Duration":
                        base_fund = rng.uniform(3, 10)
                        base_bench = base_fund + rng.normal(0, 0.5)
                    elif metric == "YTW":
                        base_fund = rng.uniform(2, 8)
                        base_bench = base_fund + rng.normal(0, 0.2)
                    elif metric == "Spread Duration":
                        base_fund = rng.uniform(3, 15)
                        base_bench = base_fund + rng.normal(0, 0.5)
                    else:
                        base_fund = rng.uniform(50, 150)
                        base_bench = base_fund + rng.normal(0, 5)
                    
                    # Add some variation over time
                    time_factor = (date - start_date).days / 365.0
                    fund_value = base_fund + rng.normal(0, base_fund * 0.02) + time_factor * rng.normal(0, 1)
                    bench_value = base_bench + rng.normal(0, base_bench * 0.02) + time_factor * rng.normal(0, 1)
                    
                    row[f"Fund {metric}"] = round(fund_value, 2)
                    row[f"Benchmark {metric}"] = round(bench_value, 2)
                    
                    rows.append(row)
        
        # Create DataFrame for primary ts_ (let pandas infer columns)
        new_df = pd.DataFrame(rows)

        # If we have a sample column order, reindex to preserve it – adding
        # any new columns at the end.
        if columns:
            missing_cols = [c for c in new_df.columns if c not in columns]
            ordered_cols = columns + missing_cols
            new_df = new_df.reindex(columns=ordered_cols)

        # ----------------- Write primary ts_ file -------------------------
        if not dry_run:
            backup_file(filepath)
            new_df.to_csv(filepath, index=False)
            print(f"    Created {filename}: {len(new_df)} rows")
        else:
            print(f"    Would create {filename}: {len(new_df)} rows")

        # ----------------- Generate sp_ts_ overlay ------------------------
        # Dynamically detect Fund / Benchmark value columns containing the metric name
        metric_lower = metric.lower()
        fund_cols = [c for c in new_df.columns if c.lower().startswith("fund") and metric_lower in c.lower()]
        bench_cols = [c for c in new_df.columns if c.lower().startswith("benchmark") and metric_lower in c.lower()]

        if not fund_cols or not bench_cols:
            # Fallback to generic naming if detection fails
            fund_cols = [f"Fund {metric}"]
            bench_cols = [f"Benchmark {metric}"]

        sp_df = new_df.copy()
        for col in fund_cols:
            if col in sp_df.columns:
                sp_df[col] = (sp_df[col] * (1 + rng.normal(0, 0.02, size=len(sp_df)))).round(2)
        for col in bench_cols:
            if col in sp_df.columns:
                sp_df[col] = (sp_df[col] * (1 + rng.normal(0, 0.02, size=len(sp_df)))).round(2)

        sp_filename = f"sp_ts_{metric}.csv"
        sp_filepath = os.path.join(data_dir, sp_filename)

        if not dry_run:
            backup_file(sp_filepath)
            sp_df.to_csv(sp_filepath, index=False)
            print(f"    Created {sp_filename}: {len(sp_df)} rows")
        else:
            print(f"    Would create {sp_filename}: {len(sp_df)} rows")


def extend_att_factors(settings, data_dir, reference_df, dry_run=False):
    """Create or extend att_factors_*.csv attribution files."""
    print("\nExtending att_factors_*.csv files...")
    
    # Date range
    start_date = pd.to_datetime(settings["time_series"]["start_date"])
    end_date = pd.to_datetime(settings["time_series"]["end_date"])
    date_range = pd.date_range(start_date, end_date, freq='D')
    
    rng = np.random.RandomState(settings["random_seed"])
    
    # Get sample columns from existing file
    sample_path = os.path.join(data_dir, "att_factors_IG01.csv")
    if os.path.exists(sample_path):
        sample_df = pd.read_csv(sample_path, nrows=5)
        att_columns = [col for col in sample_df.columns if col not in ["Date", "ISIN", "Fund"]]
    else:
        # Default attribution columns
        att_columns = [
            "Bench Weight", "Port Exp Wgt", "L0 Bench Total Daily", "L0 Port Total Daily",
            "L2 Bench Credit Spread Change Daily", "L2 Bench Rates Curve Daily",
            "L2 Port Credit Spread Change Daily", "L2 Port Rates Curve Daily"
        ]
    
    # Load fund-ISIN relationships from pre_w_secs.csv
    pre_w_secs_path = os.path.join(data_dir, "pre_w_secs.csv")

    if os.path.exists(pre_w_secs_path):
        weights_df = pd.read_csv(pre_w_secs_path)
        print("  Using fund-ISIN relationships from pre_w_secs.csv")
    else:
        print("  Warning: No weights file found, generating random fund-ISIN relationships")
        # Generate random fund-ISIN relationships as fallback
        unique_isins = reference_df["ISIN"].unique()
        funds = settings["funds"]["codes"]
        fund_isin_data = []
        
        for isin in unique_isins:
            num_funds = rng.randint(1, min(6, len(funds)))
            selected_funds = rng.choice(funds, size=num_funds, replace=False)
            for fund in selected_funds:
                fund_isin_data.append({"Fund": fund, "ISIN": isin})
        
        weights_df = pd.DataFrame(fund_isin_data)
    
    # Ensure Fund column name is consistent
    if "Funds" in weights_df.columns and "Fund" not in weights_df.columns:
        weights_df.rename(columns={"Funds": "Fund"}, inplace=True)
    
    for fund in settings["funds"]["codes"]:
        filename = f"att_factors_{fund}.csv"
        filepath = os.path.join(data_dir, filename)
        
        print(f"  Processing {filename}")
        
        # Get ISINs for this fund
        fund_isins = weights_df[weights_df["Fund"] == fund]["ISIN"].unique()
        
        if len(fund_isins) == 0:
            print(f"    Warning: No ISINs found for fund {fund}")
            continue
        
        rows = []
        for date in date_range:
            # Select a subset of ISINs for each date (not all bonds report every day)
            num_isins = rng.randint(max(1, len(fund_isins) // 2), len(fund_isins))
            selected_isins = rng.choice(fund_isins, size=num_isins, replace=False)
            
            for isin in selected_isins:
                row = {
                    "Date": date.strftime("%Y-%m-%dT%H:%M:%S"),
                    "ISIN": isin,
                    "Fund": fund
                }
                
                # Generate weights
                row["Bench Weight"] = f"{round(rng.uniform(0.1, 5.0), 2)}%"
                row["Port Exp Wgt"] = f"{round(rng.uniform(0.1, 5.0), 2)}%"
                
                # Generate attribution values
                for col in att_columns:
                    if col not in ["Bench Weight", "Port Exp Wgt"]:
                        # Most attribution values are small numbers around 0
                        if "Total" in col:
                            row[col] = round(rng.normal(0, 5), 3)
                        else:
                            row[col] = round(rng.normal(0, 0.5), 3)
                
                rows.append(row)
        
        # Create DataFrame with all columns
        all_columns = ["Date", "ISIN", "Fund", "Bench Weight", "Port Exp Wgt"] + \
                     [col for col in att_columns if col not in ["Bench Weight", "Port Exp Wgt"]]
        new_df = pd.DataFrame(rows, columns=all_columns)
        
        if not dry_run:
            backup_file(filepath)
            new_df.to_csv(filepath, index=False)
            print(f"    Created {filename}: {len(new_df)} rows")


# ---------------------------------------------------------------------------
#  Curve generation (curves.csv)
# ---------------------------------------------------------------------------

def extend_curves_files(settings, data_dir, dry_run=False):
    """Generate curves.csv with realistic term structures and daily parallel shifts."""
    print("\nExtending curves.csv ...")

    rng = np.random.RandomState(settings["random_seed"] + 99)  # separate seq

    start_date = pd.to_datetime(settings["time_series"]["start_date"])
    end_date = pd.to_datetime(settings["time_series"]["end_date"])
    date_range = pd.date_range(start_date, end_date, freq="D")

    tenors = ["7D", "14D", "1M", "2M", "6M", "12M", "24M", "48M", "60M", "120M"]
    tenor_years = {
        "7D": 7/365,
        "14D": 14/365,
        "1M": 1/12,
        "2M": 2/12,
        "6M": 0.5,
        "12M": 1,
        "24M": 2,
        "48M": 4,
        "60M": 5,
        "120M": 10,
    }

    rows = []
    for ccy in settings["securities"]["currencies"]:
        # Base short rate and slope per currency
        short_rate = rng.uniform(0.5, 3.0) / 100  # 0.5%–3%
        long_rate = short_rate + rng.uniform(1.0, 2.5) / 100  # add 1–2.5%

        for d_idx, date in enumerate(date_range):
            # Daily parallel shift (normal 3 bps)
            shift = rng.normal(0, 0.0003)
            for tenor in tenors:
                # Linear interpolation between short and long via years
                t_year = tenor_years[tenor]
                max_year = max(tenor_years.values())
                base_rate = short_rate + (long_rate - short_rate)*(t_year / max_year)
                rate = base_rate + shift
                rows.append({
                    "Date": date.strftime("%Y-%m-%dT%H:%M:%S"),
                    "Currency Code": ccy,
                    "Term": tenor,
                    "Daily Value": round(rate * 100, 3),  # store in %
                })

    curve_df = pd.DataFrame(rows)

    curve_path = os.path.join(data_dir, "curves.csv")
    if not dry_run:
        backup_file(curve_path)
        curve_df.to_csv(curve_path, index=False)
        print(f"  Created curves.csv: {len(curve_df)} rows")
    else:
        print(f"  Would create curves.csv: {len(curve_df)} rows")


def clean_reference_file(settings, data_dir, weight_df, dry_run=False):
    """Clean up reference.csv to only include securities that appear in weight files."""
    print("\nCleaning reference.csv to match securities in weight files...")
    
    if weight_df is None or weight_df.empty:
        print("  No weight data provided – skipping reference cleanup.")
        return None
    
    # Get unique ISINs that actually appear in weight files
    used_isins = set(weight_df["ISIN"].unique())
    print(f"  Found {len(used_isins)} unique ISINs in weight files")
    
    # Read current reference file
    ref_path = os.path.join(data_dir, "reference.csv")
    if not os.path.exists(ref_path):
        print("  No reference.csv found – skipping cleanup.")
        return None
    
    reference_df = pd.read_csv(ref_path)
    original_count = len(reference_df)
    print(f"  Original reference.csv had {original_count} securities")
    
    # Filter to only include securities that appear in weight files
    cleaned_reference_df = reference_df[reference_df["ISIN"].isin(used_isins)].copy()
    final_count = len(cleaned_reference_df)
    removed_count = original_count - final_count
    
    print(f"  Cleaned reference.csv now has {final_count} securities (removed {removed_count})")
    
    # Write cleaned reference file
    if not dry_run:
        backup_file(ref_path)
        cleaned_reference_df.to_csv(ref_path, index=False)
        print(f"  Updated reference.csv: {original_count} -> {final_count} rows")
    else:
        print(f"  Would update reference.csv: {original_count} -> {final_count} rows")
    
    return cleaned_reference_df


def main():
    """Main entry point."""
    args = parse_args()
    
    # Load settings
    try:
        settings = load_settings(args.settings)
    except Exception as e:
        print(f"Error loading settings file: {e}")
        sys.exit(1)
    
    # Get data directory
    data_dir = settings["data_dir"]
    if not os.path.isabs(data_dir):
        # Make it relative to current working directory
        data_dir = os.path.join(os.getcwd(), data_dir)
    
    if not os.path.exists(data_dir):
        print(f"Error: Data directory not found: {data_dir}")
        sys.exit(1)
    
    print(f"Data directory: {data_dir}")
    print(f"Dry run: {args.dry_run}")
    print(f"Random seed: {settings['random_seed']}")
    
    # Set random seed for reproducibility
    np.random.seed(settings["random_seed"])
    
    # Step 1: Extend reference.csv (initial full set)
    reference_df = extend_reference(settings, data_dir, args.dry_run)
    
    # Step 2: Generate pre_w_secs.csv (determines which securities are actually used)
    weight_df = extend_pre_w_files(settings, data_dir, reference_df, args.dry_run)

    # Step 3: Clean reference.csv to only include securities that appear in weight files
    cleaned_reference_df = clean_reference_file(settings, data_dir, weight_df, args.dry_run)
    if cleaned_reference_df is not None:
        reference_df = cleaned_reference_df

    # Step 4: Extend pre_sec_*.csv files (now using only securities from cleaned reference)
    extend_pre_sec_files(settings, data_dir, reference_df, weight_df, args.dry_run)
    
    # Step 5: Extend ts_*.csv files
    extend_ts_files(settings, data_dir, args.dry_run)
    
    # Step 6: Extend att_factors_*.csv files
    extend_att_factors(settings, data_dir, reference_df, args.dry_run)
    
    # Step 7: Extend pre_KRD files (now using only securities from cleaned reference)
    extend_pre_krd_files(settings, data_dir, reference_df, args.dry_run)
    
    # Step 8: Extend curves.csv
    extend_curves_files(settings, data_dir, args.dry_run)
    
    print("\nData extension complete!")
    if args.dry_run:
        print("This was a dry run - no files were modified.")
    else:
        print("Files have been updated. Original files backed up with .bak extension.")


if __name__ == "__main__":
    main() 