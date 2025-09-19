# analytics.py
# Purpose: Spreads, duration, convexity, KRDs, and OAS orchestration using SpreadOMatic

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from .config import COMPOUNDING

from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, z_spread, g_spread
from tools.SpreadOMatic.spreadomatic.duration import (
    effective_duration,
    modified_duration,
    effective_convexity,
    key_rate_durations,
    effective_spread_duration,
)
from tools.SpreadOMatic.spreadomatic.oas import compute_oas
from tools.SpreadOMatic.spreadomatic.oas_enhanced import compute_oas_enhanced, VolatilityCalibrator


def calculate_spreads_durations_and_oas(
    price: float,
    cashflows: List[Dict],
    curve_data: Tuple[List[float], List[float]],
    valuation_date: datetime,
    bond_data: Dict,
) -> Dict:
    times = [cf["time_years"] for cf in cashflows]
    cfs = [cf["total"] for cf in cashflows]
    zero_times = list(curve_data[0])
    zero_rates = list(curve_data[1])

    ytm = solve_ytm(price, times, cfs, comp=COMPOUNDING)
    z_spread_value = z_spread(price, times, cfs, zero_times, zero_rates, comp=COMPOUNDING)
    maturity = times[-1] if times else 1.0
    g_spread_value = g_spread(ytm, maturity, zero_times, zero_rates)

    eff_dur = effective_duration(price, times, cfs, zero_times, zero_rates, comp=COMPOUNDING)
    
    # Get frequency from bond data for accurate modified duration
    frequency = bond_data.get("schedule", {}).get("Coupon Frequency", 2)
    if isinstance(frequency, str):
        frequency = int(frequency) if frequency.isdigit() else 2
    
    # Use enhanced modified duration calculation if available
    try:
        from tools.SpreadOMatic.spreadomatic.duration_enhanced import modified_duration_precise
        mod_dur = modified_duration_precise(
            times, cfs, ytm, price, 
            frequency=frequency, 
            comp=COMPOUNDING,
            day_basis=bond_data.get("schedule", {}).get("Day Basis")
        )
    except ImportError:
        # Fallback to standard Macaulay-based calculation
        try:
            from tools.SpreadOMatic.spreadomatic.duration import modified_duration_standard as _mod_std
            mod_dur = _mod_std(times, cfs, ytm, comp=COMPOUNDING, frequency=frequency)
        except Exception:
            # Last resort: legacy scaling of effective duration
            mod_dur = modified_duration(eff_dur, ytm, frequency=frequency)
    
    convex = effective_convexity(price, times, cfs, zero_times, zero_rates, comp=COMPOUNDING)
    spread_dur = effective_spread_duration(price, times, cfs, zero_times, zero_rates, comp=COMPOUNDING)
    krds = key_rate_durations(price, times, cfs, zero_times, zero_rates, comp=COMPOUNDING)

    oas_standard = None
    oas_enhanced = None
    oas_details: Dict = {}

    if bond_data.get("call_schedule"):
        from .cashflows import to_payment_schedule
        from tools.SpreadOMatic.spreadomatic.daycount import to_datetime as oas_to_datetime

        payment_schedule = to_payment_schedule(cashflows)
        day_basis = bond_data["schedule"].get("Day Basis", "30/360")
        if "30E" in day_basis or "30e" in day_basis:
            day_basis = "30/360"

        # Optional: lookup accrued from sec_accrued.csv when available
        accrued_value = None
        try:
            import os as _os
            import pandas as _pd
            from .config import DATA_DIR as _DATA_DIR

            isin_val = bond_data.get("reference", {}).get("ISIN") or bond_data.get("schedule", {}).get("ISIN")
            if isin_val:
                accrued_path = _os.path.join(_DATA_DIR, "sec_accrued.csv")
                if _os.path.exists(accrued_path):
                    _adf = _pd.read_csv(accrued_path)
                    _row = _adf[_adf["ISIN"] == isin_val]
                    if not _row.empty:
                        # Prefer exact date; fallback to nearest previous
                        _meta = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
                        _date_cols = [c for c in _adf.columns if c not in _meta]
                        _target = valuation_date.strftime("%Y-%m-%d")
                        if _target in _date_cols:
                            _val = _row.iloc[0][_target]
                            if _pd.notna(_val) and str(_val).strip().lower() not in {"n/a","na","","null","none"}:
                                accrued_value = float(_val)
                        if accrued_value is None:
                            # fallback to latest <= target
                            _pairs = []
                            for _c in _date_cols:
                                try:
                                    _dt = _pd.to_datetime(_c)
                                    if _pd.notna(_dt):
                                        _pairs.append((_dt, _c))
                                except Exception:
                                    continue
                            _pairs.sort(key=lambda x: x[0])
                            _prev = [col for (dt, col) in _pairs if dt <= valuation_date]
                            if _prev:
                                _col = _prev[-1]
                                _val2 = _row.iloc[0][_col]
                                if _pd.notna(_val2) and str(_val2).strip().lower() not in {"n/a","na","","null","none"}:
                                    accrued_value = float(_val2)
        except Exception:
            accrued_value = None

        try:
            first_call = bond_data["call_schedule"][0]
            next_call_date = oas_to_datetime(first_call["date"])
            next_call_price = first_call["price"]
            oas_standard = compute_oas(
                payment_schedule,
                valuation_date,
                zero_times,
                zero_rates,
                day_basis,
                price,
                next_call_date=next_call_date,
                next_call_price=next_call_price,
                comp=COMPOUNDING,
                sigma=0.20,
                accrued=accrued_value,
            )
            oas_details["standard_volatility"] = 0.20
            oas_details["calls_used"] = 1
        except Exception:
            oas_standard = None

        try:
            vol_cal = VolatilityCalibrator()
            oas_enhanced = compute_oas_enhanced(
                payment_schedule,
                valuation_date,
                zero_times,
                zero_rates,
                day_basis,
                price,
                call_schedule=[{"date": c["date"], "price": c["price"]} for c in bond_data["call_schedule"]],
                comp=COMPOUNDING,
                volatility_calibrator=vol_cal,
                use_binomial=True,
                bond_characteristics=bond_data.get("bond_characteristics", {}),
            )
            oas_details["enhanced_volatility"] = getattr(vol_cal, "default_vol", None)
            oas_details["method"] = "Binomial Tree"
            oas_details["calls_used"] = len(bond_data["call_schedule"]) if bond_data.get("call_schedule") else 0
        except Exception:
            oas_enhanced = None

    return {
        "ytm": ytm,
        "z_spread": z_spread_value,
        "g_spread": g_spread_value,
        "oas_standard": oas_standard,
        "oas_enhanced": oas_enhanced,
        "oas_details": oas_details,
        "effective_duration": eff_dur,
        "modified_duration": mod_dur,
        "convexity": convex,
        "spread_duration": spread_dur,
        "key_rate_durations": krds,
        "calculated": True,
    }


