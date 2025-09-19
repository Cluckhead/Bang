# yield_spread.py
# Purpose: Yield-to-Maturity, G-Spread and Z-Spread calculations.

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .discount import discount_factor, pv_cashflows, Compounding
try:
    # Prefer robust Brent solver; fallback to legacy if unavailable
    from .numerical_methods import BrentMethod, NumericalConfig  # type: ignore
    _ROBUST_AVAILABLE = True
except Exception:
    _ROBUST_AVAILABLE = False
from .interpolation import linear_interpolate

from .cashflows import extract_cashflows
from .daycount import to_datetime, year_fraction

__all__ = ["solve_ytm", "z_spread", "g_spread", "discount_margin"]


def solve_ytm(
    price: float,
    times: List[float],
    cfs: List[float],
    *,
    comp: Compounding = "annual",
    guess: float = 0.05,
    tol: float = 1e-10,
    max_iter: int = 100,
    robust: bool = True,
    bounds: Optional[Tuple[float, float]] = None,
) -> float:
    """Solve for YTM given *price* and cash-flows.

    Uses a robust Brent bracketing solver by default. Set ``robust=False`` to
    use the legacy damped-Newton method.
    """
    def _npv(y: float) -> float:
        return sum(cf * discount_factor(y, t, comp) for cf, t in zip(cfs, times)) - price

    # Robust path (default)
    if robust and _ROBUST_AVAILABLE:
        try:
            bm = BrentMethod(NumericalConfig(tolerance=tol, max_iterations=max_iter))
            lo, hi = bounds if bounds else (-0.5, 2.0)
            return bm.solve(_npv, guess, (lo, hi))
        except Exception:
            # Fall back to legacy method if robust fails
            pass

    # Legacy damped-Newton with simple bracketing fallback
    y = guess
    for iteration in range(max_iter):
        f = _npv(y)
        if abs(f) < tol:
            return y
        h = max(1e-8, abs(y) * 1e-6) if abs(y) > 0 else 1e-6
        d = (_npv(y + h) - f) / h
        if abs(d) < 1e-12:
            if iteration > max_iter // 2:
                lower, upper = -0.5, 2.0
                while _npv(lower) * _npv(upper) > 0 and upper < 10:
                    upper *= 2
                for _ in range(20):
                    mid = (lower + upper) / 2
                    fm = _npv(mid)
                    if abs(fm) < tol:
                        return mid
                    if fm * _npv(lower) < 0:
                        upper = mid
                    else:
                        lower = mid
                return (lower + upper) / 2
            break
        step = f / d
        max_step = 0.5 if abs(y) < 1 else abs(y) * 0.5
        if abs(step) > max_step:
            step = max_step if step > 0 else -max_step
        y -= step
    raise RuntimeError("Yield solver did not converge")


def z_spread(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    comp: Compounding = "annual",
    guess: float = 0.0,
    robust: bool = True,
    bounds: Optional[Tuple[float, float]] = None,
    interp: str = "linear",
) -> float:
    """Constant additive spread over the zero curve matching *price*.

    Uses a robust Brent solver by default. Set ``robust=False`` to use the
    legacy damped-Newton method.
    """
    def _npv(spread: float) -> float:
        return pv_cashflows(
            times, cfs, zero_times, zero_rates, spread=spread, comp=comp, interp=interp
        ) - price

    if robust and _ROBUST_AVAILABLE:
        try:
            bm = BrentMethod(NumericalConfig(tolerance=1e-10, max_iterations=100))
            lo, hi = bounds if bounds else (-0.1, 0.5)
            return bm.solve(_npv, guess, (lo, hi))
        except Exception:
            pass

    s = guess
    for iteration in range(100):
        f = _npv(s)
        if abs(f) < 1e-10:
            return s
        h = max(1e-8, abs(s) * 1e-6) if abs(s) > 0 else 1e-6
        d = (_npv(s + h) - f) / h
        if abs(d) < 1e-12:
            if f > 0:
                s += 0.0001
            else:
                s -= 0.0001
            continue
        step = f / d
        max_step = 0.01
        if abs(step) > max_step:
            step = max_step if step > 0 else -max_step
        s -= step
    raise RuntimeError("Z-spread solver did not converge")


def g_spread(
    ytm: float,
    maturity: float,
    zero_times: List[float],
    zero_rates: List[float],
    ytm_compounding: int = 2,
    zero_compounding: str = "annual",
    *,
    interp: str = "linear",
) -> float:
    """Govt-spread = YTM minus govt zero yield at maturity on same compounding basis.

    - Interpolates the govt curve at ``maturity`` (using ``interp``), converts both
      YTM and zero yield to a common continuous basis, then returns the spread
      re-expressed on the YTM compounding basis for comparability.
    """
    # Interpolate government zero yield at maturity
    zero_rate = linear_interpolate(zero_times, zero_rates, maturity, method=interp)

    # Helpers to convert between compounding conventions
    def to_cont(r: float, comp: str | int) -> float:
        if comp == "continuous" or comp == 0:
            return r
        if comp == "annual" or comp == 1:
            return math.log(1.0 + r)
        if comp == "semiannual" or comp == 2:
            return 2.0 * math.log(1.0 + r / 2.0)
        if comp == "quarterly" or comp == 4:
            return 4.0 * math.log(1.0 + r / 4.0)
        if comp == "monthly" or comp == 12:
            return 12.0 * math.log(1.0 + r / 12.0)
        m = float(comp) if isinstance(comp, int) else 1.0
        return m * math.log(1.0 + r / m)

    def cont_to_nominal(r_cont: float, comp: int) -> float:
        if comp == 0:
            return r_cont
        if comp == 1:
            return math.exp(r_cont) - 1.0
        m = float(comp)
        return m * (math.exp(r_cont / m) - 1.0)

    # Convert both to continuous compounding
    ytm_c = to_cont(ytm, ytm_compounding)
    zero_c = to_cont(zero_rate, zero_compounding)

    # Continuous spread
    spread_c = ytm_c - zero_c

    # Return spread expressed on the YTM compounding basis
    return cont_to_nominal(spread_c, ytm_compounding)


def discount_margin(
    price: float,
    payment_schedule: List[dict],
    valuation_date,
    proj_zero_times: List[float],
    proj_zero_rates: List[float],
    disc_zero_times: List[float],
    disc_zero_rates: List[float],
    day_basis: str,
    *,
    comp: Compounding = "annual",
) -> float:
    """Solve FRN discount margin (constant add-on to projected coupons).

    Definition
    - Finds ``dm`` such that PV of the FRN using coupons projected as
      ``(forward + spread + dm) * accrual * notional`` matches the target
      ``price`` when discounted on the discount curve.

    Inputs
    - ``payment_schedule``: list of items where floating coupons are rows
      without an explicit ``amount`` (see ``cashflows.extract_cashflows``).
    - ``proj_zero_times/rates``: projection curve for forward rates (e.g. SOFR/EURIBOR).
    - ``disc_zero_times/rates``: discounting curve (e.g. OIS).
    - ``price``: target dirty price (per 100 notionals).

    Returns
    - Discount margin in decimal (e.g., 0.0035 for 35 bps).

    Notes
    - Uses an analytic closed-form because PV is linear in the margin:
        PV(dm) = PV_base + dm * sum_i(DF_i * accr_i * notional_i)
      where the sum runs over floating coupons only with DF from the
      discount curve.
    """
    # 1) Base PV using projected coupons (dm = 0), discounted on discount curve
    times, cfs = extract_cashflows(
        payment_schedule, valuation_date, proj_zero_times, proj_zero_rates, day_basis
    )
    pv_base = pv_cashflows(times, cfs, disc_zero_times, disc_zero_rates, comp=comp)

    # 2) Compute PV weight of a 1.0 margin add-on applied to all floating coupons
    pv_weight = 0.0
    for item in payment_schedule:
        # Only floating rows (no explicit amount)
        if "amount" in item:
            continue
        pay_dt = to_datetime(item["date"])
        if pay_dt <= valuation_date:
            continue

        accr_basis = item.get("basis", day_basis)
        reset_dt = to_datetime(item.get("reset_date", valuation_date.isoformat()))
        notional = float(item.get("notional", 100.0))

        # Accrual for the floating period and discount factor to payment date
        accr = year_fraction(reset_dt, pay_dt, accr_basis)
        t_pay = year_fraction(valuation_date, pay_dt, accr_basis)
        r_disc = linear_interpolate(disc_zero_times, disc_zero_rates, t_pay)
        df = discount_factor(r_disc, t_pay, comp)
        pv_weight += notional * accr * df

    if abs(pv_weight) < 1e-14:
        # No floating coupons or degenerate schedule
        raise ValueError("Cannot solve discount margin: zero PV weight (no floating coupons?)")

    # 3) Closed-form solution
    dm = (price - pv_base) / pv_weight
    return dm
