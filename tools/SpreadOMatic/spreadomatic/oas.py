# oas.py
# Purpose: Option-adjusted spread estimator (simple Black model on next call).

from __future__ import annotations
# ignore

import math
from typing import List, Dict, Optional
from scipy.optimize import brentq

from .discount import discount_factor, pv_cashflows, Compounding
from .interpolation import linear_interpolate
from .cashflows import extract_cashflows
from .duration import effective_duration
from .yield_spread import solve_ytm, z_spread
from .daycount import year_fraction, to_datetime

__all__ = ["compute_oas"]


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_oas(
    payment_schedule: List[Dict],
    valuation_date,
    zero_times: List[float],
    zero_rates: List[float],
    day_basis: str,
    clean_price: float,
    *,
    next_call_date,
    next_call_price: float,
    comp: Compounding = "annual",
    sigma: float = 0.20,
    accrued: Optional[float] = None,
    dirty_price: Optional[float] = None,
) -> Optional[float]:
    """Return OAS using simple Black model on the *next* call date.

    Parameters
    ----------
    payment_schedule : list[dict]
        Full bond cash-flow schedule.
    valuation_date : datetime
        Valuation date.
    zero_times, zero_rates : list[float]
        Zero curve expressed as times (in years) and annual-compounded yields.
    day_basis : str
        Day-count basis for year-fraction conversions.
    clean_price : float
        Clean price of the bond (per 100).
    next_call_date, next_call_price : datetime, float
        First upcoming call.
    comp : {"annual", "semiannual", "quarterly", "continuous"}
        Compounding basis used for discount factors.
    sigma : float
        Annualised log-normal price volatility (constant).
    """

    if next_call_date is None or next_call_date <= valuation_date:
        return None

    # --- Helper: estimate accrued interest from full schedule ---------------
    def _estimate_accrued_from_schedule(schedule: List[Dict], val_dt) -> float:
        try:
            # Collect all schedule dates and amounts
            items = [(to_datetime(it["date"]), float(it["amount"])) for it in schedule]
            if not items:
                return 0.0

            # Identify surrounding coupon dates
            past = [it for it in items if it[0] <= val_dt]
            future = [it for it in items if it[0] > val_dt]
            if not future or not past:
                return 0.0
            prev_dt = max(past, key=lambda x: x[0])[0]
            next_dt, next_amt = min(future, key=lambda x: x[0])

            # Estimate typical coupon amount (exclude largest payment which includes principal)
            amounts = sorted(a for (_, a) in items)
            if len(amounts) >= 2:
                typical_coupon = amounts[-2]  # second largest as a heuristic
            else:
                typical_coupon = amounts[0]

            # Guard against pathological schedules
            if typical_coupon <= 0:
                return 0.0

            # If next amount is close to typical coupon, use it; otherwise use typical coupon
            coupon_amt = typical_coupon
            if abs(next_amt - typical_coupon) / max(1e-8, typical_coupon) < 0.25:
                coupon_amt = next_amt

            # Accrued = coupon * accrual fraction in current period
            period = max(1e-12, year_fraction(prev_dt, next_dt, day_basis))
            elapsed = max(0.0, year_fraction(prev_dt, val_dt, day_basis))
            frac = min(max(elapsed / period, 0.0), 1.0)
            return coupon_amt * frac
        except Exception:
            return 0.0

    # Time to call
    T_call = year_fraction(valuation_date, next_call_date, day_basis)
    if T_call <= 0:
        return None

    # --- Forward price of remaining cash flows at the call date -------------
    pv_remaining = 0.0
    for item in payment_schedule:
        dt_item = to_datetime(item["date"])
        if dt_item <= next_call_date:
            continue
        t_item = year_fraction(valuation_date, dt_item, day_basis)
        r_item = linear_interpolate(zero_times, zero_rates, t_item)
        pv_remaining += float(item["amount"]) * discount_factor(r_item, t_item, comp)

    # Discount factor to call date
    r_call = linear_interpolate(zero_times, zero_rates, T_call)
    df_call = discount_factor(r_call, T_call, comp)

    if df_call <= 0:
        return None

    F = pv_remaining / df_call  # forward price
    K = next_call_price

    if F <= 0:
        return None

    std_dev = sigma * math.sqrt(T_call)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T_call) / std_dev
    d2 = d1 - std_dev

    option_value = df_call * (F * _normal_cdf(d1) - K * _normal_cdf(d2))

    # --- Price inputs and PV01 approximation --------------------------------
    times, cfs = extract_cashflows(
        payment_schedule, valuation_date, zero_times, zero_rates, day_basis
    )
    # Prefer caller-supplied dirty/accrued; else estimate from schedule
    if dirty_price is not None and dirty_price > 0:
        dp = dirty_price
    elif accrued is not None:
        dp = clean_price + float(accrued)
    else:
        acc_est = _estimate_accrued_from_schedule(payment_schedule, valuation_date)
        dp = clean_price + acc_est

    ytm = solve_ytm(dp, times, cfs, comp=comp)
    dur = effective_duration(dp, times, cfs, zero_times, zero_rates, comp=comp)
    # PV01 (DV01) using effective duration and a 1bp bump
    pv01 = dp * dur * 0.0001

    if pv01 <= 0:
        return None

    # Proper OAS calculation using root-finding
    def _model_price_error(oas_candidate: float) -> float:
        """Return model price minus market price for given OAS candidate."""
        # Apply OAS to zero rates
        adjusted_rates = [r + oas_candidate for r in zero_rates]

        # Calculate PV of cash flows with adjusted rates
        pv_cfs = 0.0
        for t, cf in zip(times, cfs):
            if t > 0:
                r_adj = linear_interpolate(zero_times, adjusted_rates, t)
                pv_cfs += cf * discount_factor(r_adj, t, comp)

        # Calculate embedded option value
        # Apply OAS to call date rate
        r_call_adj = linear_interpolate(zero_times, adjusted_rates, T_call)
        df_call_adj = discount_factor(r_call_adj, T_call, comp)

        # Forward price with adjusted rates
        F_adj = pv_remaining / df_call_adj if df_call_adj > 0 else 0.0

        if F_adj <= 0:
            option_value_adj = 0.0
        else:
            std_dev = sigma * math.sqrt(T_call)
            d1 = (math.log(F_adj / K) + 0.5 * sigma ** 2 * T_call) / std_dev
            d2 = d1 - std_dev
            option_value_adj = df_call_adj * (F_adj * _normal_cdf(d1) - K * _normal_cdf(d2))

        model_price = pv_cfs + option_value_adj
        return model_price - dp

    # Use root-finding to solve for OAS where model price = market price
    try:
        # Search for OAS in reasonable bounds (-5% to +5%)
        oas_result = brentq(_model_price_error, -0.05, 0.05, xtol=1e-8)
        return oas_result
    except ValueError:
        # If root-finding fails, fall back to approximation method
        z_base = z_spread(dp, times, cfs, zero_times, zero_rates, comp=comp)
        return z_base + option_value / pv01 
