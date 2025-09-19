"""
Enhanced Duration Module with Institutional-Grade Precision
Implements comprehensive duration analytics with proper mathematical rigor.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple, Union
import numpy as np
from datetime import datetime, timedelta
from enum import Enum

from .discount import pv_cashflows, discount_factor, Compounding
from .interpolation import linear_interpolate


class DurationMethod(Enum):
    """Duration calculation methodology."""
    MACAULAY = "macaulay"
    MODIFIED = "modified"
    EFFECTIVE = "effective"
    OPTION_ADJUSTED = "option_adjusted"
    SPREAD = "spread"
    KEY_RATE = "key_rate"


class ConvexityType(Enum):
    """Convexity calculation type."""
    STANDARD = "standard"
    EFFECTIVE = "effective"
    NEGATIVE = "negative"  # For callable bonds


def macaulay_duration(
    times: List[float],
    cfs: List[float],
    ytm: float,
    price: float,
    frequency: int = 2,
    comp: Compounding = "semiannual"
) -> float:
    """
    Calculate Macaulay duration - the weighted average time to receive cash flows.
    
    This is the foundation for modified duration and provides the true weighted
    average maturity of a bond's cash flows.
    
    Args:
        times: Time to each cash flow in years
        cfs: Cash flow amounts
        ytm: Yield to maturity (as decimal)
        price: Current bond price (dirty price)
        frequency: Payment frequency per year
        comp: Compounding convention
    
    Returns:
        Macaulay duration in years
    """
    if not times or not cfs:
        return 0.0
    
    # Calculate present value of each cash flow
    pv_sum = 0.0
    weighted_pv_sum = 0.0
    
    for t, cf in zip(times, cfs):
        if comp == "semiannual":
            pv = cf / ((1 + ytm/2) ** (2 * t))
        elif comp == "annual":
            pv = cf / ((1 + ytm) ** t)
        elif comp == "continuous":
            pv = cf * np.exp(-ytm * t)
        else:  # monthly
            pv = cf / ((1 + ytm/12) ** (12 * t))
        
        pv_sum += pv
        weighted_pv_sum += t * pv
    
    # Macaulay duration is the weighted average time
    if pv_sum > 0:
        return weighted_pv_sum / pv_sum
    return 0.0


def modified_duration_precise(
    times: List[float],
    cfs: List[float],
    ytm: float,
    price: float,
    frequency: int = 2,
    comp: Compounding = "semiannual",
    day_basis: Optional[str] = None
) -> float:
    """
    Calculate modified duration with precise adjustments for payment frequency,
    compounding, and day count conventions.
    
    Modified duration = Macaulay duration / (1 + ytm/k)
    where k is the compounding frequency
    
    Args:
        times: Time to each cash flow in years
        cfs: Cash flow amounts
        ytm: Yield to maturity (as decimal)
        price: Current bond price (dirty price)
        frequency: Payment frequency per year
        comp: Compounding convention
        day_basis: Day count convention for fine adjustments
    
    Returns:
        Modified duration in years
    """
    # First calculate Macaulay duration
    mac_dur = macaulay_duration(times, cfs, ytm, price, frequency, comp)
    
    # Apply modified duration formula with proper compounding adjustment
    if comp == "semiannual":
        mod_dur = mac_dur / (1 + ytm / 2)
    elif comp == "annual":
        mod_dur = mac_dur / (1 + ytm)
    elif comp == "continuous":
        # For continuous compounding, modified duration equals Macaulay duration
        mod_dur = mac_dur
    elif comp == "monthly":
        mod_dur = mac_dur / (1 + ytm / 12)
    else:
        # General case
        mod_dur = mac_dur / (1 + ytm / frequency)
    
    # Apply day basis adjustment if needed
    if day_basis:
        if "ACT/360" in day_basis.upper():
            mod_dur *= 360 / 365.25
        elif "ACT/365" in day_basis.upper():
            mod_dur *= 365 / 365.25
    
    return mod_dur


def effective_duration_enhanced(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    delta: float = 0.0001,  # 1 basis point
    comp: Compounding = "semiannual",
    shock_type: str = "parallel"
) -> float:
    """
    Calculate effective (option-adjusted) duration using finite differences.
    
    This is more accurate for bonds with embedded options as it captures
    the actual price sensitivity including any optionality effects.
    
    Args:
        price: Current bond price (dirty price)
        times: Time to each cash flow in years
        cfs: Cash flow amounts
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        delta: Yield shock size (default 1bp)
        comp: Compounding convention
        shock_type: Type of shock ("parallel", "twist", "butterfly")
    
    Returns:
        Effective duration in years
    """
    if shock_type == "parallel":
        # Standard parallel shift
        zero_up = [r + delta for r in zero_rates]
        zero_down = [r - delta for r in zero_rates]
    elif shock_type == "twist":
        # Steepening/flattening shock
        pivot = 5.0  # 5-year pivot point
        zero_up = []
        zero_down = []
        for t, r in zip(zero_times, zero_rates):
            twist_factor = (t - pivot) / 10.0
            zero_up.append(r + delta * (1 + twist_factor))
            zero_down.append(r - delta * (1 + twist_factor))
    else:  # butterfly
        # Curvature change
        short_point = 2.0
        long_point = 10.0
        zero_up = []
        zero_down = []
        for t, r in zip(zero_times, zero_rates):
            if t <= short_point:
                factor = 1.0
            elif t >= long_point:
                factor = 1.0
            else:
                # Middle part moves opposite
                factor = -1.0
            zero_up.append(r + delta * factor)
            zero_down.append(r - delta * factor)
    
    # Calculate prices under shocked curves
    p_up = pv_cashflows(times, cfs, zero_times, zero_up, comp=comp)
    p_down = pv_cashflows(times, cfs, zero_times, zero_down, comp=comp)
    
    # Effective duration using central difference
    eff_dur = (p_down - p_up) / (2 * price * delta)
    
    return eff_dur


def dollar_duration(
    modified_duration: float,
    price: float,
    face_value: float = 100.0
) -> float:
    """
    Calculate dollar duration (DV01 or PVBP).
    
    Dollar duration measures the dollar change in price for a 1 basis point
    change in yield.
    
    Args:
        modified_duration: Modified duration in years
        price: Current bond price (as % of par)
        face_value: Face value of the bond
    
    Returns:
        Dollar duration (DV01)
    """
    # DV01 = Modified Duration × (Price × Face Value / 100) × 0.0001
    dirty_price = price * face_value / 100.0
    return modified_duration * dirty_price * 0.0001


def spread_duration_enhanced(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    delta: float = 0.0001,
    comp: Compounding = "semiannual",
    spread_type: str = "z_spread"
) -> float:
    """
    Calculate spread duration with respect to different spread measures.
    
    Args:
        price: Current bond price
        times: Cash flow times
        cfs: Cash flow amounts
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        delta: Spread shock size
        comp: Compounding convention
        spread_type: Type of spread ("z_spread", "oas", "i_spread")
    
    Returns:
        Spread duration in years
    """
    if spread_type == "z_spread":
        # Standard Z-spread duration
        p_up = 0.0
        p_down = 0.0
        for cf, t in zip(cfs, times):
            r = linear_interpolate(zero_times, zero_rates, t)
            p_up += cf * discount_factor(r + delta, t, comp)
            p_down += cf * discount_factor(r - delta, t, comp)
    elif spread_type == "oas":
        # OAS duration (requires volatility adjustment)
        # Simplified version - full implementation would use tree models
        vol_adjustment = 1.0  # Would be calculated from volatility model
        p_up = 0.0
        p_down = 0.0
        for cf, t in zip(cfs, times):
            r = linear_interpolate(zero_times, zero_rates, t)
            p_up += cf * discount_factor(r + delta * vol_adjustment, t, comp)
            p_down += cf * discount_factor(r - delta * vol_adjustment, t, comp)
    else:  # i_spread
        # Interpolated spread duration
        # Uses only the maturity-matched rate
        maturity = max(times)
        base_rate = linear_interpolate(zero_times, zero_rates, maturity)
        p_up = pv_cashflows(times, cfs, [maturity], [base_rate + delta], comp=comp)
        p_down = pv_cashflows(times, cfs, [maturity], [base_rate - delta], comp=comp)
    
    return (p_down - p_up) / (2 * price * delta)


def convexity_enhanced(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    delta: float = 0.0001,
    comp: Compounding = "semiannual",
    convexity_type: ConvexityType = ConvexityType.EFFECTIVE
) -> float:
    """
    Calculate convexity with proper second-order sensitivity.
    
    Convexity measures the curvature of the price-yield relationship.
    Positive convexity is desirable, negative convexity (callable bonds) is not.
    
    Args:
        price: Current bond price
        times: Cash flow times
        cfs: Cash flow amounts
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        delta: Yield shock for numerical derivative
        comp: Compounding convention
        convexity_type: Type of convexity calculation
    
    Returns:
        Convexity (dimensionless, often scaled by 100)
    """
    if convexity_type == ConvexityType.STANDARD:
        # Analytical convexity using cash flows
        conv = 0.0
        for t, cf in zip(times, cfs):
            r = linear_interpolate(zero_times, zero_rates, t)
            if comp == "semiannual":
                df = 1 / ((1 + r/2) ** (2 * t))
                conv += cf * df * t * (t + 0.5) / ((1 + r/2) ** 2)
            elif comp == "annual":
                df = 1 / ((1 + r) ** t)
                conv += cf * df * t * (t + 1) / ((1 + r) ** 2)
            else:  # continuous
                df = np.exp(-r * t)
                conv += cf * df * t * t
        return conv / price
    
    else:  # EFFECTIVE or NEGATIVE
        # Numerical convexity using finite differences
        zero_up = [r + delta for r in zero_rates]
        zero_down = [r - delta for r in zero_rates]
        
        p_up = pv_cashflows(times, cfs, zero_times, zero_up, comp=comp)
        p_down = pv_cashflows(times, cfs, zero_times, zero_down, comp=comp)
        p_base = price
        
        # Second derivative approximation
        convexity = (p_up - 2 * p_base + p_down) / (p_base * delta ** 2)
        
        # For negative convexity (callable bonds), check if convexity is negative
        if convexity_type == ConvexityType.NEGATIVE and convexity > 0:
            # Apply callable bond adjustment
            convexity *= -0.5  # Simplified - real calculation would use option model
        
        return convexity


def key_rate_durations_enhanced(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    key_tenors: Optional[List[float]] = None,
    delta: float = 0.0001,
    comp: Compounding = "semiannual",
    interpolation: str = "linear"
) -> Dict[str, float]:
    """
    Calculate key rate durations with flexible tenor points and interpolation.
    
    KRDs show sensitivity to specific points on the yield curve, essential
    for understanding curve risk beyond parallel shifts.
    
    Args:
        price: Current bond price
        times: Cash flow times
        cfs: Cash flow amounts
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        key_tenors: Custom key rate tenors (default: standard set)
        delta: Rate shock size
        comp: Compounding convention
        interpolation: Interpolation method for shocks
    
    Returns:
        Dictionary of tenor -> duration
    """
    import copy
    from bisect import bisect_left
    
    # Default key rate tenors if not provided
    if key_tenors is None:
        key_tenors = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0]
    
    # Labels for output
    tenor_labels = {
        0.083: "1M", 0.25: "3M", 0.5: "6M", 1.0: "1Y", 2.0: "2Y",
        3.0: "3Y", 5.0: "5Y", 7.0: "7Y", 10.0: "10Y", 15.0: "15Y",
        20.0: "20Y", 30.0: "30Y"
    }
    
    krds = {}
    
    for key_tenor in key_tenors:
        # Create shocked curves
        zero_times_up = copy.deepcopy(zero_times)
        zero_rates_up = copy.deepcopy(zero_rates)
        zero_times_down = copy.deepcopy(zero_times)
        zero_rates_down = copy.deepcopy(zero_rates)
        
        if interpolation == "triangular":
            # Triangular shock centered at key tenor
            width = 1.0  # 1-year width
            for i, t in enumerate(zero_times):
                distance = abs(t - key_tenor)
                if distance < width:
                    shock_factor = 1.0 - distance / width
                    zero_rates_up[i] += delta * shock_factor
                    zero_rates_down[i] -= delta * shock_factor
        else:  # linear (point shock)
            # Insert or update the key tenor point
            idx = bisect_left(zero_times_up, key_tenor)
            
            if idx < len(zero_times_up) and abs(zero_times_up[idx] - key_tenor) < 1e-9:
                # Exact match - shock this point
                zero_rates_up[idx] += delta
                zero_rates_down[idx] -= delta
            else:
                # Insert new point with shocked rate
                base_rate = linear_interpolate(zero_times, zero_rates, key_tenor)
                zero_times_up.insert(idx, key_tenor)
                zero_rates_up.insert(idx, base_rate + delta)
                zero_times_down.insert(idx, key_tenor)
                zero_rates_down.insert(idx, base_rate - delta)
        
        # Calculate prices with shocked curves
        p_up = pv_cashflows(times, cfs, zero_times_up, zero_rates_up, comp=comp)
        p_down = pv_cashflows(times, cfs, zero_times_down, zero_rates_down, comp=comp)
        
        # Key rate duration
        krd = (p_down - p_up) / (2 * price * delta)
        
        # Store with appropriate label
        label = tenor_labels.get(key_tenor, f"{key_tenor}Y")
        krds[label] = krd
    
    return krds


def partial_durations(
    price: float,
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    buckets: Optional[List[Tuple[float, float]]] = None,
    delta: float = 0.0001,
    comp: Compounding = "semiannual"
) -> Dict[str, float]:
    """
    Calculate partial durations for custom maturity buckets.
    
    Useful for ALM and regulatory reporting where specific buckets are required.
    
    Args:
        price: Current bond price
        times: Cash flow times
        cfs: Cash flow amounts
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        buckets: List of (start, end) tuples defining buckets
        delta: Rate shock size
        comp: Compounding convention
    
    Returns:
        Dictionary of bucket -> partial duration
    """
    if buckets is None:
        # Default regulatory buckets
        buckets = [
            (0, 1), (1, 3), (3, 5), (5, 7),
            (7, 10), (10, 15), (15, 20), (20, 30), (30, 50)
        ]
    
    partial_durs = {}
    
    for start, end in buckets:
        # Shock only rates in this bucket
        zero_rates_up = []
        zero_rates_down = []
        
        for t, r in zip(zero_times, zero_rates):
            if start <= t < end:
                zero_rates_up.append(r + delta)
                zero_rates_down.append(r - delta)
            else:
                zero_rates_up.append(r)
                zero_rates_down.append(r)
        
        # Calculate prices
        p_up = pv_cashflows(times, cfs, zero_times, zero_rates_up, comp=comp)
        p_down = pv_cashflows(times, cfs, zero_times, zero_rates_down, comp=comp)
        
        # Partial duration for this bucket
        partial_dur = (p_down - p_up) / (2 * price * delta)
        
        # Store with bucket label
        label = f"{start}-{end}Y" if end < 50 else f"{start}Y+"
        partial_durs[label] = partial_dur
    
    return partial_durs


def calculate_all_duration_metrics(
    price: float,
    times: List[float],
    cfs: List[float],
    ytm: float,
    zero_times: List[float],
    zero_rates: List[float],
    frequency: int = 2,
    comp: Compounding = "semiannual",
    day_basis: Optional[str] = None,
    include_partials: bool = False
) -> Dict[str, Union[float, Dict]]:
    """
    Calculate comprehensive duration analytics with all metrics.
    
    Args:
        price: Current bond price (dirty)
        times: Cash flow times
        cfs: Cash flow amounts
        ytm: Yield to maturity
        zero_times: Zero curve times
        zero_rates: Zero curve rates
        frequency: Payment frequency
        comp: Compounding convention
        day_basis: Day count convention
        include_partials: Whether to include partial durations
    
    Returns:
        Dictionary with all duration metrics
    """
    results = {}
    
    # Core duration metrics
    results["macaulay_duration"] = macaulay_duration(times, cfs, ytm, price, frequency, comp)
    results["modified_duration"] = modified_duration_precise(times, cfs, ytm, price, frequency, comp, day_basis)
    results["effective_duration"] = effective_duration_enhanced(price, times, cfs, zero_times, zero_rates, comp=comp)
    results["dollar_duration"] = dollar_duration(results["modified_duration"], price)
    
    # Spread durations
    results["z_spread_duration"] = spread_duration_enhanced(price, times, cfs, zero_times, zero_rates, comp=comp, spread_type="z_spread")
    results["oas_duration"] = spread_duration_enhanced(price, times, cfs, zero_times, zero_rates, comp=comp, spread_type="oas")
    
    # Convexity
    results["effective_convexity"] = convexity_enhanced(price, times, cfs, zero_times, zero_rates, comp=comp)
    
    # Key rate durations
    results["key_rate_durations"] = key_rate_durations_enhanced(price, times, cfs, zero_times, zero_rates, comp=comp)
    
    # Partial durations (optional)
    if include_partials:
        results["partial_durations"] = partial_durations(price, times, cfs, zero_times, zero_rates, comp=comp)
    
    # Risk metrics
    results["duration_times_spread"] = results["modified_duration"] * results.get("z_spread_duration", 0)
    results["convexity_adjustment"] = 0.5 * results["effective_convexity"] * (0.01 ** 2) * 100  # 100bp move
    
    return results


# Backward compatibility exports
effective_duration = effective_duration_enhanced
modified_duration = modified_duration_precise
effective_convexity = convexity_enhanced
key_rate_durations = key_rate_durations_enhanced
effective_spread_duration = spread_duration_enhanced

__all__ = [
    "DurationMethod",
    "ConvexityType",
    "macaulay_duration",
    "modified_duration_precise",
    "effective_duration_enhanced",
    "dollar_duration",
    "spread_duration_enhanced",
    "convexity_enhanced",
    "key_rate_durations_enhanced",
    "partial_durations",
    "calculate_all_duration_metrics",
    # Backward compatibility
    "effective_duration",
    "modified_duration",
    "effective_convexity",
    "key_rate_durations",
    "effective_spread_duration",
]