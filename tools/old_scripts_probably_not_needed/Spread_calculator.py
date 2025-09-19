# Spread_calculator.py
# Purpose: Legacy wrapper that exposes SpreadOMatic analytics via a simple JSON/CSV interface.
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Optional pandas integration ------------------------------------------------
try:
    import pandas as pd  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    pd = None

# --- Import analytics from modular package ----------------------------------

from spreadomatic.daycount import to_datetime, year_fraction
from spreadomatic.interpolation import linear_interpolate
from spreadomatic.cashflows import extract_cashflows, generate_fixed_schedule as _gen_fixed_schedule
from spreadomatic.yield_spread import solve_ytm, g_spread, z_spread
from spreadomatic.discount import Compounding
from spreadomatic.duration import (
    effective_duration,
    modified_duration,
    effective_convexity,
    key_rate_durations,
)
from spreadomatic.oas import compute_oas
try:
    from spreadomatic.oas_enhanced import compute_oas_enhanced, VolatilityCalibrator
    ENHANCED_OAS_AVAILABLE = True
except ImportError:
    ENHANCED_OAS_AVAILABLE = False

# Backwards-compatibility aliases -------------------------------------------
_to_datetime = to_datetime
_generate_fixed_schedule = _gen_fixed_schedule

# ---------------------------------------------------------------------------
# Utility I/O helpers (kept lightweight)                                       
# ---------------------------------------------------------------------------

def _parse_json_maybe_path(data_or_path):
    """If *data_or_path* looks like a path, load JSON; else return parsed object."""
    if isinstance(data_or_path, (dict, list)):
        return data_or_path
    try:
        return json.loads(data_or_path)
    except json.JSONDecodeError:
        with open(data_or_path, "r", encoding="utf-8") as f:
            return json.load(f)

# ---------------------------------------------------------------------------
# Public API – same signature, new engine                                     
# ---------------------------------------------------------------------------

def calculate_spreads(
    zero_curve: str | dict | list,
    payment_schedule: str | dict | list,
    price: float,
    *,
    accrued_interest: Optional[float] = None,
    valuation_date: Optional[str | datetime] = None,
    day_basis: str = "30/360",
    currency: str | None = None,
    call_schedule: Optional[str | dict | list] = None,
    compounding: Compounding = "annual",
) -> Dict[str, float]:
    """Compute spreads & risk metrics – now powered by *spreadomatic* modules."""

    valuation_dt = to_datetime(valuation_date) if valuation_date else datetime.utcnow()

    zero_data = _parse_json_maybe_path(zero_curve)
    pay_data = _parse_json_maybe_path(payment_schedule)

    # Zero curve to (times, rates)
    z_times, z_rates = zip(*[
        (
            year_fraction(valuation_dt, to_datetime(row["date"]), day_basis),
            float(row["rate"]),
        )
        for row in zero_data
    ])
    z_times, z_rates = list(z_times), list(z_rates)

    # Cash-flows
    times, cfs = extract_cashflows(
        pay_data, valuation_dt, z_times, z_rates, day_basis
    )
    if not times:
        raise ValueError("No future cash-flows after valuation date")

    # Interpret price as:
    # - Dirty when accrued_interest is None
    # - Clean when accrued_interest is provided → convert to dirty
    dirty_price = price if accrued_interest is None else price + accrued_interest
    if dirty_price <= 0:
        raise ValueError("Dirty price must be positive")

    maturity = max(times)

    # Core spreads & durations
    ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
    gspr = g_spread(ytm, maturity, z_times, z_rates)
    zspr = z_spread(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
    eff_dur = effective_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)

    # Convexity & KRDs
    convexity = effective_convexity(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
    krd = key_rate_durations(dirty_price, times, cfs, z_times, z_rates, comp=compounding)

    # Option analytics (single next-call Black model)
    next_call_date = next_call_price = None
    if call_schedule:
        call_data = _parse_json_maybe_path(call_schedule)
        future = [c for c in call_data if to_datetime(c["date"]) > valuation_dt]
        if future:
            nxt = min(future, key=lambda c: to_datetime(c["date"]))
            next_call_date, next_call_price = to_datetime(nxt["date"]), float(nxt["price"])

    oas_val = compute_oas(
        pay_data,
        valuation_dt,
        z_times,
        z_rates,
        day_basis,
        dirty_price,
        next_call_date=next_call_date,
        next_call_price=next_call_price,
        comp=compounding,
    )

    # Determine frequency from compounding convention
    frequency = {'annual': 1, 'semiannual': 2, 'quarterly': 4, 'continuous': 1}.get(compounding, 2)
    
    result = {
        "yield_to_maturity": ytm,
        "g_spread": gspr,
        "z_spread": zspr,
        "effective_duration": eff_dur,
        "modified_duration": modified_duration(eff_dur, ytm, frequency),
        "convexity": convexity,
        "oas": oas_val,
        **{f"krd_{k}": v for k, v in krd.items()},
    }

    return result

# ---------------------------------------------------------------------------
# Simple CLI (kept for legacy scripts)                                        
# ---------------------------------------------------------------------------

def _build_arg_parser():
    import argparse

    p = argparse.ArgumentParser(description="Compute spread/duration metrics (legacy wrapper).")
    sub = p.add_subparsers(dest="mode", help="single | batch")

    s = sub.add_parser("single", help="Single bond inputs (JSON paths)")
    s.add_argument("zero_curve")
    s.add_argument("payment_schedule")
    s.add_argument("price", type=float)
    s.add_argument("--accrued-interest", type=float)
    s.add_argument("--valuation-date")
    s.add_argument("--day-basis", default="30/360")
    s.add_argument("--compounding", default="annual", choices=["annual", "semiannual", "quarterly", "continuous"])

    b = sub.add_parser("batch", help="Batch mode – CSV inputs (requires pandas)")
    b.add_argument("curves_csv")
    b.add_argument("bonds_csv")
    b.add_argument("--output")

    return p

def _run_single(args):
    res = calculate_spreads(
        args.zero_curve,
        args.payment_schedule,
        args.price,
        accrued_interest=args.accrued_interest,
        valuation_date=args.valuation_date,
        day_basis=args.day_basis,
        compounding=args.compounding,
    )
    print(json.dumps(res, indent=2))

def _run_batch(args):
    if pd is None:
        sys.exit("Pandas required for batch mode – pip install pandas")

    curves_df = pd.read_csv(args.curves_csv)
    bonds_df = pd.read_csv(args.bonds_csv)

    out_rows: List[Dict[str, Any]] = []

    # Group curve rows by curve_id once
    grouped = {
        cid: grp[["date", "rate"]].rename(columns={"date": "date", "rate": "rate"}).to_dict("records")
        for cid, grp in curves_df.groupby("curve_id")
    }

    for _, bond in bonds_df.iterrows():
        cid = bond["curve_id"]
        if cid not in grouped:
            raise KeyError(f"Curve id '{cid}' not found in curves CSV")

        zero_curve_obj = grouped[cid]

        # Build/gather payment schedule
        if "payment_schedule" in bond and pd.notna(bond["payment_schedule"]) and str(bond["payment_schedule"]).strip():
            pay_sched_obj = json.loads(bond["payment_schedule"])
        else:
            sched = _gen_fixed_schedule(
                to_datetime(bond.get("issue_date", datetime.utcnow().isoformat())),
                to_datetime(bond["first_coupon_date"]),
                to_datetime(bond["maturity_date"]),
                float(bond["coupon_rate"]),
                bond.get("day_basis", "30/360"),
                bond.get("currency", cid),
            )
            pay_sched_obj = sched

        metrics = calculate_spreads(
            zero_curve_obj,
            pay_sched_obj,
            price=float(bond["price"]),
            accrued_interest=bond.get("accrued_interest"),
            valuation_date=bond.get("valuation_date"),
            day_basis=bond.get("day_basis", "30/360"),
            currency=bond.get("currency"),
            call_schedule=(bond["call_schedule"] if "call_schedule" in bond and pd.notna(bond["call_schedule"]) and str(bond["call_schedule"]).strip() else None),
        )

        out_rows.append({**bond.to_dict(), **metrics})

    out_df = pd.DataFrame(out_rows)

    if args.output:
        out_df.to_csv(args.output, index=False)
        print(f"Results written to {args.output}")
    else:
        print(out_df.to_csv(index=False))

if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.mode == "single":
        _run_single(args)
    elif args.mode == "batch":
        _run_batch(args)
    else:
        parser.print_help(sys.stderr)
