# duration.py
# Purpose: Effective, modified, key-rate and convexity analytics.

from __future__ import annotations

from typing import List, Dict

from .discount import pv_cashflows, discount_factor, Compounding
from .interpolation import linear_interpolate

__all__ = [
    "effective_duration",
    "modified_duration",
    "effective_convexity",
    "key_rate_durations",
    "effective_spread_duration",
    # new helpers (non-breaking additions)
    "macaulay_duration",
    "modified_duration_standard",
]


# Discrete standard key tenors (years)
_KRD_TENORS = {
    "1M": 1 / 12,
    "3M": 0.25,
    "6M": 0.5,
    "1Y": 1.0,
    "2Y": 2.0,
    "3Y": 3.0,
    "4Y": 4.0,
    "5Y": 5.0,
    "7Y": 7.0,
    "10Y": 10.0,
    "20Y": 20.0,
    "30Y": 30.0,
    "50Y": 50.0,
}


def effective_duration(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    delta: float = 1e-4,
    comp: Compounding = "annual",
) -> float:
    zero_up = [r + delta for r in zero_rates]
    zero_down = [r - delta for r in zero_rates]
    p_up = pv_cashflows(times, cfs, zero_times, zero_up, comp=comp)
    p_down = pv_cashflows(times, cfs, zero_times, zero_down, comp=comp)
    return (p_down - p_up) / (2 * price * delta)


def modified_duration(eff_dur: float, ytm: float, frequency: int = 2) -> float:
    """Calculate modified duration from Macaulay duration.

    Args:
        eff_dur: Macaulay duration (not effective duration)
        ytm: Yield to maturity (as decimal, e.g., 0.05 for 5%)
        frequency: Coupon payment frequency (1=annual, 2=semi-annual, 4=quarterly, 12=monthly)

    Returns:
        Modified duration

    Note: Uses Macaulay duration as the base, not effective duration
    """
    return eff_dur / (1 + ytm / frequency)


def effective_convexity(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    # Use a smaller bump (10 bps) for higher-fidelity convexity
    delta: float = 0.001,
    comp: Compounding = "annual",
) -> float:
    zero_up = [r + delta for r in zero_rates]
    zero_down = [r - delta for r in zero_rates]
    p_up = pv_cashflows(times, cfs, zero_times, zero_up, comp=comp)
    p_down = pv_cashflows(times, cfs, zero_times, zero_down, comp=comp)
    return (p_down + p_up - 2 * price) / (price * delta ** 2)


def macaulay_duration(
    times: List[float],
    cfs: List[float],
    ytm: float,
    *,
    comp: Compounding = "annual",
) -> float:
    """Macaulay duration (weighted average time of PV cashflows).

    Notes
    - Uses the compounding convention supplied via ``comp`` and discounts with
      the given yield-to-maturity (ytm).
    - Returns 0.0 when there are no cashflows.
    """
    if not times or not cfs:
        return 0.0

    pv_sum = 0.0
    weighted_pv_sum = 0.0
    for t, cf in zip(times, cfs):
        df = discount_factor(ytm, t, comp)
        pv = cf * df
        pv_sum += pv
        weighted_pv_sum += t * pv
    return (weighted_pv_sum / pv_sum) if pv_sum > 0.0 else 0.0


def modified_duration_standard(
    times: List[float],
    cfs: List[float],
    ytm: float,
    *,
    comp: Compounding = "annual",
    frequency: int = 2,
) -> float:
    """Standard modified duration derived from Macaulay duration.

    Definition
    - Modified Duration = Macaulay Duration / (1 + ytm / frequency)

    This avoids re-scaling effective duration and aligns with vendor conventions
    for DV01/PVBP when paired with small yield bumps.
    """
    mac = macaulay_duration(times, cfs, ytm, comp=comp)
    return mac / (1.0 + (ytm / max(1, int(frequency))))


def key_rate_durations(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    delta: float = 1e-4,
    comp: Compounding = "annual",
) -> Dict[str, float]:
    import copy
    from bisect import bisect_left

    out: Dict[str, float] = {}
    for label, t_key in _KRD_TENORS.items():
        t_up, r_up = copy.deepcopy(zero_times), copy.deepcopy(zero_rates)
        t_dn, r_dn = copy.deepcopy(zero_times), copy.deepcopy(zero_rates)

        def _insert_or_shift(t_list, r_list, bump):
            idx = bisect_left(t_list, t_key)
            if idx < len(t_list) and abs(t_list[idx] - t_key) < 1e-9:
                r_list[idx] += bump
            else:
                base = linear_interpolate(t_list, r_list, t_key)
                t_list.insert(idx, t_key)
                r_list.insert(idx, base + bump)

        _insert_or_shift(t_up, r_up, delta)
        _insert_or_shift(t_dn, r_dn, -delta)

        p_up = pv_cashflows(times, cfs, t_up, r_up, comp=comp)
        p_dn = pv_cashflows(times, cfs, t_dn, r_dn, comp=comp)
        out[label] = (p_dn - p_up) / (2 * price * delta)
    return out


def effective_spread_duration(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    delta: float = 1e-4,
    comp: Compounding = "annual",
) -> float:
    p_up = 0.0
    p_dn = 0.0
    for cf, t in zip(cfs, times):
        r = linear_interpolate(zero_times, zero_rates, t)
        # Fixed: Use discount_factor directly instead of pv_cashflows with single points
        p_up += cf * discount_factor(r + delta, t, comp)
        p_dn += cf * discount_factor(r - delta, t, comp)
    return (p_dn - p_up) / (2 * price * delta) 
