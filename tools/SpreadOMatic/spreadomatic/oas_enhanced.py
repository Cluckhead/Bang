# oas_enhanced.py
# Purpose: Enhanced Option-Adjusted Spread calculator with market-calibrated volatility,
# multi-call support, and binomial tree pricing for improved accuracy

from __future__ import annotations

import math
import numpy as np
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timedelta
from bisect import bisect_left
from scipy.optimize import brentq

from .discount import discount_factor, pv_cashflows, Compounding
from .interpolation import linear_interpolate
from .cashflows import extract_cashflows
from .duration import effective_duration, modified_duration
from .yield_spread import solve_ytm, z_spread
from .daycount import year_fraction, to_datetime

__all__ = [
    "compute_oas_enhanced",
    "calibrate_volatility",
    "VolatilityCalibrator",
    "BinomialOASCalculator"
]


class VolatilityCalibrator:
    """
    Calibrates implied volatility from market data instead of using fixed 20%.
    Supports volatility term structure and smile effects.
    """
    
    def __init__(self, 
                 market_data_path: Optional[str] = None,
                 default_vol: float = 0.15):
        """
        Initialize volatility calibrator.
        
        Parameters
        ----------
        market_data_path : str, optional
            Path to market implied volatility data (swaptions, callable bonds)
        default_vol : float
            Default volatility if no market data available (15% more conservative than 20%)
        """
        self.default_vol = default_vol
        self.vol_surface = {}
        self.calibration_date = None
        
        if market_data_path:
            self._load_market_data(market_data_path)
    
    def _load_market_data(self, path: str):
        """Load and process market implied volatility data."""
        try:
            import pandas as pd
            vol_data = pd.read_csv(path)
            # Expected columns: Date, Tenor, Strike, ImpliedVol
            self.calibration_date = vol_data['Date'].max()
            
            for _, row in vol_data.iterrows():
                key = (float(row['Tenor']), float(row['Strike']))
                self.vol_surface[key] = float(row['ImpliedVol'])
        except Exception as e:
            print(f"Warning: Could not load volatility data: {e}")
    
    def get_volatility(self, 
                      time_to_call: float,
                      moneyness: float,
                      bond_characteristics: Optional[Dict] = None) -> float:
        """
        Get calibrated volatility for specific call option.
        
        Parameters
        ----------
        time_to_call : float
            Time to call date in years
        moneyness : float
            Forward price / Strike price ratio
        bond_characteristics : dict, optional
            Additional bond info (rating, sector, etc.) for vol adjustment
        
        Returns
        -------
        float
            Calibrated implied volatility
        """
        # Base volatility from term structure
        base_vol = self._interpolate_vol_surface(time_to_call, moneyness)
        
        # Adjustments based on bond characteristics
        if bond_characteristics:
            # Credit spread adjustment - higher spread = higher vol
            if 'credit_spread' in bond_characteristics:
                spread_bps = bond_characteristics['credit_spread'] * 10000
                vol_adjustment = min(0.10, spread_bps / 1000)  # Cap at 10% additional vol
                base_vol *= (1 + vol_adjustment)
            
            # Rating adjustment
            if 'rating' in bond_characteristics:
                rating = bond_characteristics['rating']
                rating_multipliers = {
                    'AAA': 0.8, 'AA': 0.9, 'A': 1.0,
                    'BBB': 1.2, 'BB': 1.5, 'B': 2.0
                }
                base_vol *= rating_multipliers.get(rating[:3], 1.0)
        
        # Apply volatility smile - OTM options have higher vol
        smile_adjustment = self._volatility_smile(moneyness)
        
        return base_vol * smile_adjustment
    
    def _interpolate_vol_surface(self, tenor: float, moneyness: float) -> float:
        """Interpolate volatility from surface data."""
        if not self.vol_surface:
            # No market data - use term structure estimate
            if tenor <= 1:
                return self.default_vol * 0.8  # Short-term lower vol
            elif tenor <= 5:
                return self.default_vol
            else:
                return self.default_vol * 1.2  # Long-term higher vol
        
        # 2D interpolation from surface
        # Simplified - in production use scipy.interpolate.griddata
        tenors = sorted(set(k[0] for k in self.vol_surface.keys()))
        strikes = sorted(set(k[1] for k in self.vol_surface.keys()))
        
        # Find surrounding points
        t_idx = bisect_left(tenors, tenor)
        s_idx = bisect_left(strikes, moneyness)
        
        # Simple bilinear interpolation
        if t_idx > 0 and t_idx < len(tenors) and s_idx > 0 and s_idx < len(strikes):
            t1, t2 = tenors[t_idx-1], tenors[t_idx]
            s1, s2 = strikes[s_idx-1], strikes[s_idx]
            
            v11 = self.vol_surface.get((t1, s1), self.default_vol)
            v12 = self.vol_surface.get((t1, s2), self.default_vol)
            v21 = self.vol_surface.get((t2, s1), self.default_vol)
            v22 = self.vol_surface.get((t2, s2), self.default_vol)
            
            # Bilinear interpolation
            w1 = (t2 - tenor) / (t2 - t1) if t2 != t1 else 0.5
            w2 = (s2 - moneyness) / (s2 - s1) if s2 != s1 else 0.5
            
            return (w1 * w2 * v11 + w1 * (1-w2) * v12 + 
                   (1-w1) * w2 * v21 + (1-w1) * (1-w2) * v22)
        
        return self.default_vol
    
    def _volatility_smile(self, moneyness: float) -> float:
        """Apply volatility smile adjustment based on moneyness."""
        # Typical smile: higher vol for OTM options
        if moneyness < 0.9:  # Deep OTM put (call from issuer perspective)
            return 1.2
        elif moneyness < 0.95:
            return 1.1
        elif moneyness > 1.1:  # Deep ITM
            return 1.15
        elif moneyness > 1.05:
            return 1.05
        else:  # ATM
            return 1.0


class BinomialOASCalculator:
    """
    Binomial tree implementation for American call option pricing.
    More accurate than Black model for multiple exercise dates.
    """
    
    def __init__(self, steps: int = 100):
        """
        Initialize binomial calculator.
        
        Parameters
        ----------
        steps : int
            Number of time steps in the tree (more = more accurate but slower)
        """
        self.steps = steps
    
    def calculate_option_value(self,
                              spot: float,
                              strikes: List[Tuple[float, float]],  # (time, strike) pairs
                              rate: float,
                              volatility: float,
                              time_to_maturity: float) -> float:
        """
        Calculate American call option value using binomial tree.
        
        Parameters
        ----------
        spot : float
            Current bond price
        strikes : list of tuples
            List of (time_in_years, strike_price) for each call date
        rate : float
            Risk-free rate
        volatility : float
            Calibrated volatility
        time_to_maturity : float
            Time to final maturity
        
        Returns
        -------
        float
            Option value
        """
        if not strikes:
            return 0.0
        
        dt = time_to_maturity / self.steps
        u = math.exp(volatility * math.sqrt(dt))  # Up factor
        d = 1 / u  # Down factor
        p = (math.exp(rate * dt) - d) / (u - d)  # Risk-neutral probability
        
        # Build price tree
        price_tree = np.zeros((self.steps + 1, self.steps + 1))
        price_tree[0, 0] = spot
        
        for i in range(1, self.steps + 1):
            for j in range(i + 1):
                price_tree[i, j] = spot * (u ** j) * (d ** (i - j))
        
        # Build option value tree (backward induction)
        option_tree = np.zeros((self.steps + 1, self.steps + 1))
        
        # Terminal payoff (no call at maturity, so value = 0)
        # This assumes bond is not called at maturity
        
        # Work backwards through tree
        for i in range(self.steps - 1, -1, -1):
            current_time = i * dt
            
            # Find applicable strike for this time
            applicable_strike = None
            for call_time, strike in strikes:
                if abs(current_time - call_time) < dt / 2:
                    applicable_strike = strike
                    break
            
            for j in range(i + 1):
                # Continuation value
                cont_value = math.exp(-rate * dt) * (
                    p * option_tree[i + 1, j + 1] + 
                    (1 - p) * option_tree[i + 1, j]
                )
                
                # Exercise value if call date
                if applicable_strike is not None:
                    exercise_value = max(0, price_tree[i, j] - applicable_strike)
                    option_tree[i, j] = max(cont_value, exercise_value)
                else:
                    option_tree[i, j] = cont_value
        
        return option_tree[0, 0]


def compute_oas_enhanced(
    payment_schedule: List[Dict],
    valuation_date: datetime,
    zero_times: List[float],
    zero_rates: List[float],
    day_basis: str,
    clean_price: float,
    *,
    call_schedule: Optional[List[Dict]] = None,
    comp: Compounding = "annual",
    volatility_calibrator: Optional[VolatilityCalibrator] = None,
    use_binomial: bool = True,
    bond_characteristics: Optional[Dict] = None
) -> Optional[float]:
    """
    Enhanced OAS calculation with market-calibrated volatility and multi-call support.
    
    Parameters
    ----------
    payment_schedule : list[dict]
        Full bond cash-flow schedule
    valuation_date : datetime
        Valuation date
    zero_times, zero_rates : list[float]
        Zero curve (times in years, rates as decimals)
    day_basis : str
        Day-count convention
    clean_price : float
        Clean price of the bond (per 100)
    call_schedule : list[dict], optional
        Full call schedule with dates and prices
    comp : Compounding
        Compounding convention
    volatility_calibrator : VolatilityCalibrator, optional
        Calibrated volatility model (uses default if not provided)
    use_binomial : bool
        Use binomial tree (True) or Black model (False)
    bond_characteristics : dict, optional
        Additional bond info for volatility adjustment
    
    Returns
    -------
    float or None
        Option-adjusted spread in decimal form
    """
    
    # Filter future calls only
    if not call_schedule:
        return None
    
    future_calls = []
    for call in call_schedule:
        call_date = to_datetime(call["date"])
        if call_date > valuation_date:
            call_time = year_fraction(valuation_date, call_date, day_basis)
            future_calls.append((call_time, float(call["price"])))
    
    if not future_calls:
        return None
    
    # Sort by time
    future_calls.sort(key=lambda x: x[0])
    
    # Calculate bond value without embedded option (straight bond)
    times, cfs = extract_cashflows(
        payment_schedule, valuation_date, zero_times, zero_rates, day_basis
    )
    
    if not times:
        return None
    
    # Get YTM and duration for PV01 calculation
    ytm = solve_ytm(clean_price, times, cfs, comp=comp)
    dur = effective_duration(clean_price, times, cfs, zero_times, zero_rates, comp=comp)
    # Determine frequency from compounding convention
    frequency = {'annual': 1, 'semiannual': 2, 'quarterly': 4, 'continuous': 1}.get(comp, 2)
    pv01 = clean_price * modified_duration(dur, ytm, frequency) / 100.0
    
    if pv01 <= 0:
        return None
    
    # Initialize volatility calibrator if not provided
    if volatility_calibrator is None:
        volatility_calibrator = VolatilityCalibrator()
    
    # Calculate option value
    if use_binomial and len(future_calls) > 1:
        # Use binomial tree for multiple calls
        calculator = BinomialOASCalculator(steps=100)
        
        # Calculate forward bond price at first call
        first_call_time = future_calls[0][0]
        pv_to_first_call = 0.0
        
        for cf_time, cf_amount in zip(times, cfs):
            if cf_time <= first_call_time:
                r = linear_interpolate(zero_times, zero_rates, cf_time)
                pv_to_first_call += cf_amount * discount_factor(r, cf_time, comp)
        
        # Remaining value at first call
        pv_after_call = 0.0
        for cf_time, cf_amount in zip(times, cfs):
            if cf_time > first_call_time:
                r = linear_interpolate(zero_times, zero_rates, cf_time)
                pv_after_call += cf_amount * discount_factor(r, cf_time, comp)
        
        r_first = linear_interpolate(zero_times, zero_rates, first_call_time)
        df_first = discount_factor(r_first, first_call_time, comp)
        forward_price = pv_after_call / df_first if df_first > 0 else 0
        
        # Get calibrated volatility
        moneyness = forward_price / future_calls[0][1] if future_calls[0][1] > 0 else 1.0
        volatility = volatility_calibrator.get_volatility(
            first_call_time, moneyness, bond_characteristics
        )
        
        # Calculate option value using binomial tree
        option_value = calculator.calculate_option_value(
            forward_price,
            future_calls,
            r_first,
            volatility,
            times[-1] if times else first_call_time
        )
        
        # Discount back to today
        option_value *= df_first
        
    else:
        # Use enhanced Black model for single call or if binomial not requested
        first_call_time, first_call_price = future_calls[0]
        
        # Calculate forward price of bond at call date
        pv_remaining = 0.0
        for item in payment_schedule:
            dt_item = to_datetime(item["date"])
            if dt_item <= to_datetime(valuation_date):
                continue
            if dt_item <= to_datetime(valuation_date) + timedelta(days=int(first_call_time * 365)):
                continue
            
            t_item = year_fraction(valuation_date, dt_item, day_basis)
            r_item = linear_interpolate(zero_times, zero_rates, t_item)
            pv_remaining += float(item["amount"]) * discount_factor(r_item, t_item, comp)
        
        r_call = linear_interpolate(zero_times, zero_rates, first_call_time)
        df_call = discount_factor(r_call, first_call_time, comp)
        
        if df_call <= 0:
            return None
        
        forward_price = pv_remaining / df_call
        
        if forward_price <= 0:
            return None
        
        # Get calibrated volatility
        moneyness = forward_price / first_call_price
        volatility = volatility_calibrator.get_volatility(
            first_call_time, moneyness, bond_characteristics
        )
        
        # Black model with calibrated volatility
        std_dev = volatility * math.sqrt(first_call_time)
        d1 = (math.log(forward_price / first_call_price) + 
              0.5 * volatility ** 2 * first_call_time) / std_dev
        d2 = d1 - std_dev
        
        option_value = df_call * (
            forward_price * _normal_cdf(d1) - 
            first_call_price * _normal_cdf(d2)
        )
    
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

        # Calculate embedded option value with adjusted rates
        # This is a simplified approach - in practice would need full option revaluation
        # For now, use the previously calculated option_value as approximation
        model_price = pv_cfs + option_value
        return model_price - clean_price

    # Use root-finding to solve for OAS where model price = market price
    try:
        # Search for OAS in reasonable bounds (-5% to +5%)
        oas_result = brentq(_model_price_error, -0.05, 0.05, xtol=1e-8)
        return oas_result
    except ValueError:
        # If root-finding fails, fall back to approximation method
        z_base = z_spread(clean_price, times, cfs, zero_times, zero_rates, comp=comp)
        return z_base + option_value / pv01


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def calibrate_volatility(
    market_prices: List[Dict],
    reference_data: Dict,
    initial_vol: float = 0.15
) -> float:
    """
    Calibrate implied volatility from market prices of callable bonds.
    
    Parameters
    ----------
    market_prices : list[dict]
        Market prices of callable bonds with known characteristics
    reference_data : dict
        Bond reference data for calculations
    initial_vol : float
        Initial volatility guess
    
    Returns
    -------
    float
        Calibrated implied volatility
    """
    # Simplified calibration - in production use optimization
    # to minimize pricing errors across multiple bonds
    
    total_error = 0.0
    count = 0
    
    for bond in market_prices:
        try:
            # Calculate theoretical OAS with current vol
            theoretical_oas = compute_oas_enhanced(
                bond['schedule'],
                bond['valuation_date'],
                bond['zero_times'],
                bond['zero_rates'],
                bond['day_basis'],
                bond['clean_price'],
                call_schedule=bond['call_schedule'],
                volatility_calibrator=VolatilityCalibrator(default_vol=initial_vol)
            )
            
            # Compare with market OAS
            market_oas = bond.get('market_oas', 0)
            error = abs(theoretical_oas - market_oas) if theoretical_oas else 0
            
            total_error += error
            count += 1
            
        except Exception as e:
            print(f"Calibration error for bond: {e}")
            continue
    
    # Adjust volatility based on average error
    if count > 0:
        avg_error = total_error / count
        # Simple adjustment - in production use proper optimizer
        if avg_error > 0.001:  # OAS error > 10bps
            return initial_vol * 1.1  # Increase vol
        elif avg_error < -0.001:
            return initial_vol * 0.9  # Decrease vol
    
    return initial_vol
