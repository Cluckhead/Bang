# test_fixed_income_harness.py
# Purpose: Systematic, scenario-based tests for core fixed income analytics starting
#          from vanilla fixed-coupon bonds and building up in complexity.

from __future__ import annotations

import math
from typing import List, Tuple

import pytest

from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows
from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, z_spread, g_spread
from tools.SpreadOMatic.spreadomatic.duration import (
    effective_duration,
    effective_convexity,
    modified_duration,
    key_rate_durations,
)
from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows
from tools.SpreadOMatic.spreadomatic.daycount import year_fraction


# -----------------------------
# Helper builders
# -----------------------------

def build_flat_zero_curve(rate: float, horizon: float, n: int = 50) -> Tuple[List[float], List[float]]:
    times = [horizon * i / n for i in range(1, n + 1)]
    rates = [rate for _ in times]
    return times, rates


def build_fixed_coupon_cashflows(
    coupon_rate: float,
    maturity_years: float,
    frequency: int,
) -> Tuple[List[float], List[float]]:
    num_periods = int(round(maturity_years * frequency))
    dt = 1.0 / frequency
    times = [dt * i for i in range(1, num_periods + 1)]
    coupon_payment = 100.0 * coupon_rate * dt
    cfs = [coupon_payment for _ in range(num_periods - 1)] + [coupon_payment + 100.0]
    return times, cfs


def build_payment_schedule_dates(
    valuation_date_dt,
    years: int,
    frequency: int,
    coupon_rate: float,
    basis: str,
) -> List[dict]:
    # Build a simple fixed-coupon schedule using date math and basis for accrual amounts
    schedule: List[dict] = []
    months = 12 // frequency
    prev = valuation_date_dt
    from datetime import timedelta
    current_year = valuation_date_dt.year
    current_month = valuation_date_dt.month
    current_day = valuation_date_dt.day
    # Start first coupon one period ahead
    for i in range(1, years * frequency + 1):
        # naive month increment that keeps day stable when possible
        month_total = current_month + months
        year_inc = (month_total - 1) // 12
        month_mod = ((month_total - 1) % 12) + 1
        current_year += year_inc
        current_month = month_mod
        # Handle month-end by capping day
        from calendar import monthrange
        last_day = monthrange(current_year, current_month)[1]
        day = min(current_day, last_day)
        pay_dt = valuation_date_dt.replace(year=current_year, month=current_month, day=day)
        accr = year_fraction(prev, pay_dt, basis)
        amount = round(100.0 * coupon_rate * accr + (100.0 if i == years * frequency else 0.0), 8)
        schedule.append({"date": pay_dt.isoformat(), "amount": amount})
        prev = pay_dt
    return schedule


# -----------------------------
# Core vanilla scenarios
# -----------------------------


@pytest.mark.parametrize(
    "curve_rate,coupon_rate,maturity,frequency,comp",
    [
        (0.05, 0.05, 5.0, 1, "annual"),      # Par annual coupon
        (0.05, 0.05, 5.0, 2, "semiannual"),  # Par semiannual coupon
        (0.04, 0.00, 3.0, 1, "annual"),      # Zero-coupon bond
    ],
)
def test_price_yield_spreads_and_duration(curve_rate, coupon_rate, maturity, frequency, comp):
    times, cfs = build_fixed_coupon_cashflows(coupon_rate, maturity, frequency)
    zero_times, zero_rates = build_flat_zero_curve(curve_rate, maturity)

    # Price from the zero curve (clean equals PV of future cfs in this synthetic setup)
    price = pv_cashflows(times, cfs, zero_times, zero_rates, comp=comp)

    # YTM should match the curve/coupon for par construction (or solve exactly for zero)
    ytm = solve_ytm(price, times, cfs, comp=comp)

    if coupon_rate > 0:
        assert pytest.approx(ytm, rel=1e-10, abs=1e-12) == coupon_rate
    else:
        # Zero-coupon: YTM equals curve rate by construction
        assert pytest.approx(ytm, rel=1e-10, abs=1e-12) == curve_rate

    # Z-spread recovers ~0 when priced exactly off the zero curve
    z = z_spread(price, times, cfs, zero_times, zero_rates, comp=comp)
    assert abs(z) < 1e-10

    # G-spread should be near zero for flat curve when ytm equals terminal zero rate
    g = g_spread(ytm, maturity, zero_times, zero_rates)
    assert abs(g) < 1e-10

    # Effective duration via library equals bump-and-reprice on the curve
    eff = effective_duration(price, times, cfs, zero_times, zero_rates, comp=comp)

    # Validate effective duration by manual bump-and-reprice
    dlt = 1e-4
    p_up = pv_cashflows(times, cfs, zero_times, [r + dlt for r in zero_rates], comp=comp)
    p_dn = pv_cashflows(times, cfs, zero_times, [r - dlt for r in zero_rates], comp=comp)
    eff_manual = (p_dn - p_up) / (2 * price * dlt)
    assert pytest.approx(eff, rel=1e-8, abs=1e-10) == eff_manual

    # Modified duration expectation depends on compounding convention
    if comp == "semiannual":
        expected_mod = eff / (1.0 + ytm / 2.0)
    else:
        expected_mod = modified_duration(eff, ytm)
    assert expected_mod > 0

    # Convexity via library equals manual bump-and-reprice using the same delta
    convex = effective_convexity(price, times, cfs, zero_times, zero_rates, comp=comp)
    dlt_cx = 0.01
    p_up_c = pv_cashflows(times, cfs, zero_times, [r + dlt_cx for r in zero_rates], comp=comp)
    p_dn_c = pv_cashflows(times, cfs, zero_times, [r - dlt_cx for r in zero_rates], comp=comp)
    convex_manual = (p_dn_c + p_up_c - 2 * price) / (price * dlt_cx ** 2)
    assert pytest.approx(convex, rel=1e-3, abs=1e-6) == convex_manual

    # KRDs: Sum of KRDs should approximate effective duration under small parallel shifts
    krds = key_rate_durations(price, times, cfs, zero_times, zero_rates, comp=comp)
    sum_krd = sum(krds.values())
    # Allow tolerance since tenors are discrete and interpolation/compounding differ.
    # Empirically, 7% relative tolerance covers typical deviations on flat curves.
    rel_err = abs(sum_krd - eff) / eff if eff != 0 else 0.0
    assert rel_err < 0.07


def test_z_spread_recovers_synthetic_spread():
    curve_rate = 0.03
    maturity = 7.0
    frequency = 2
    comp = "semiannual"
    coupon_rate = 0.035
    s_true = 0.005  # 50 bps

    times, cfs = build_fixed_coupon_cashflows(coupon_rate, maturity, frequency)
    zero_times, zero_rates = build_flat_zero_curve(curve_rate, maturity)

    # Price using a constant spread over the zero curve
    price = pv_cashflows(times, cfs, zero_times, zero_rates, spread=s_true, comp=comp)

    s_est = z_spread(price, times, cfs, zero_times, zero_rates, comp=comp)
    assert pytest.approx(s_est, rel=1e-10, abs=1e-9) == s_true


@pytest.mark.parametrize(
    "basis,comp,frequency",
    [
        ("30/360", "annual", 1),
        ("ACT/365", "annual", 1),
        ("ACT/ACT", "annual", 1),
        ("ACT/360", "semiannual", 2),
        ("ISDA", "semiannual", 2),
    ],
)
def test_daycount_parametrized_z_spread_recovery(basis, comp, frequency):
    from datetime import datetime
    valuation_dt = datetime(2025, 1, 2)
    years = 3
    coupon_rate = 0.04
    curve_rate = 0.035
    s_true = 0.0025

    payment_schedule = build_payment_schedule_dates(valuation_dt, years, frequency, coupon_rate, basis)
    zero_times, zero_rates = build_flat_zero_curve(curve_rate, years + 0.5)
    times, cfs = extract_cashflows(payment_schedule, valuation_dt, zero_times, zero_rates, basis)

    price = pv_cashflows(times, cfs, zero_times, zero_rates, spread=s_true, comp=comp)
    s_est = z_spread(price, times, cfs, zero_times, zero_rates, comp=comp)
    # Allow tiny absolute tolerance for numerical derivative in solver
    assert pytest.approx(s_est, rel=1e-12, abs=5e-11) == s_true


def test_price_yield_monotonicity():
    times, cfs = build_fixed_coupon_cashflows(0.05, 5.0, 2)
    zero_times, zero_rates = build_flat_zero_curve(0.05, 5.0)
    comp = "semiannual"
    price = pv_cashflows(times, cfs, zero_times, zero_rates, comp=comp)
    ytm = solve_ytm(price, times, cfs, comp=comp)
    ytm_up_price = solve_ytm(price * 1.01, times, cfs, comp=comp)
    assert ytm_up_price < ytm


def test_frn_z_spread_recovery():
    from datetime import datetime, timedelta
    valuation_dt = datetime(2025, 1, 2)
    # Build three monthly FRN coupons with reset today for each
    basis = "ACT/360"
    notional = 100.0
    spread_coupon = 0.0
    months = [1, 2, 3]
    payment_schedule: List[dict] = []
    for m in months:
        pay_dt = valuation_dt + timedelta(days=int(30 * m))
        payment_schedule.append({
            "date": pay_dt.isoformat(),
            "notional": notional,
            "spread": spread_coupon,
            "reset_date": valuation_dt.isoformat(),
            "basis": basis,
        })

    zero_times, zero_rates = build_flat_zero_curve(0.03, 1.0)
    times, cfs = extract_cashflows(payment_schedule, valuation_dt, zero_times, zero_rates, basis)
    comp = "annual"
    s_true = 0.004
    price = pv_cashflows(times, cfs, zero_times, zero_rates, spread=s_true, comp=comp)
    s_est = z_spread(price, times, cfs, zero_times, zero_rates, comp=comp)
    assert pytest.approx(s_est, rel=1e-12, abs=1e-9) == s_true


def test_oas_sanity_otm_and_volatility_effects():
    # OTM call: OAS >= Z; lower vol or higher strike drives OAS closer to Z
    from datetime import datetime, timedelta
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas

    valuation_dt = datetime(2025, 1, 2)
    basis = "30/360"
    frequency = 2
    years = 2
    coupon_rate = 0.04
    payment_schedule = build_payment_schedule_dates(valuation_dt, years, frequency, coupon_rate, basis)

    zero_times, zero_rates = build_flat_zero_curve(0.035, years + 0.5)
    times, cfs = extract_cashflows(payment_schedule, valuation_dt, zero_times, zero_rates, basis)

    comp = "semiannual"
    clean_price = pv_cashflows(times, cfs, zero_times, zero_rates, comp=comp)
    z_base = z_spread(clean_price, times, cfs, zero_times, zero_rates, comp=comp)

    next_call_date = valuation_dt + timedelta(days=365)
    # Moderately OTM, two vol settings
    K_mid = 200.0
    oas_hi_vol = compute_oas(
        payment_schedule,
        valuation_dt,
        zero_times,
        zero_rates,
        basis,
        clean_price,
        next_call_date=next_call_date,
        next_call_price=K_mid,
        comp=comp,
        sigma=0.20,
    )
    oas_lo_vol = compute_oas(
        payment_schedule,
        valuation_dt,
        zero_times,
        zero_rates,
        basis,
        clean_price,
        next_call_date=next_call_date,
        next_call_price=K_mid,
        comp=comp,
        sigma=0.01,
    )
    assert oas_hi_vol is not None and oas_lo_vol is not None
    # OAS should be >= z_base for a call (positive option value)
    assert oas_hi_vol >= z_base and oas_lo_vol >= z_base
    # Lower volatility should reduce option value and bring OAS closer to Z
    assert abs(oas_lo_vol - z_base) <= abs(oas_hi_vol - z_base)

    # Extremely OTM: very high strike and low vol should make OAS ~ Z (within ~1 bp)
    K_far = 1000.0
    oas_far = compute_oas(
        payment_schedule,
        valuation_dt,
        zero_times,
        zero_rates,
        basis,
        clean_price,
        next_call_date=next_call_date,
        next_call_price=K_far,
        comp=comp,
        sigma=0.01,
    )
    assert oas_far is not None
    assert abs(oas_far - z_base) < 1e-4  # < 1 bp


