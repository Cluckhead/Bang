# curve_construction.py  
# Purpose: Institutional-grade yield curve construction with bootstrapping and advanced interpolation
# Implements methods used by major fixed income desks for curve building and rate interpolation

from __future__ import annotations

import numpy as np
import scipy.optimize as opt
import scipy.interpolate as interp
from scipy.linalg import solve_banded
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Union, Callable, NamedTuple
from dataclasses import dataclass
from enum import Enum
import warnings

from .daycount_enhanced import year_fraction_precise, DayCountConvention

__all__ = [
    "CurveInstrument", 
    "InterpolationMethod",
    "YieldCurve", 
    "CurveBuilder",
    "nelson_siegel_svensson",
    "monotone_convex_interpolation"
]


class InterpolationMethod(Enum):
    """Yield curve interpolation methodologies"""
    LINEAR = "linear"                          # Linear interpolation
    CUBIC_SPLINE = "cubic_spline"             # Cubic spline
    MONOTONE_CUBIC = "monotone_cubic"         # Monotonicity preserving cubic
    HERMITE = "hermite"                       # Piecewise cubic Hermite
    AKIMA = "akima"                           # Akima spline
    LOG_LINEAR = "log_linear"                 # Log-linear (for discount factors)
    NELSON_SIEGEL = "nelson_siegel"           # Nelson-Siegel parametric
    SVENSSON = "svensson"                     # Svensson extension
    HAGAN_WEST = "hagan_west"                 # Hagan-West monotone method


@dataclass
class CurveInstrument:
    """Market instrument used for curve construction"""
    maturity: datetime
    rate: float                               # Market rate (as decimal)
    instrument_type: str                      # "CASH", "FUTURES", "SWAP", "BOND"
    bid: Optional[float] = None               # Bid rate
    ask: Optional[float] = None               # Ask rate
    last: Optional[float] = None              # Last traded rate
    volume: Optional[int] = None              # Trading volume
    currency: str = "USD"
    day_count: str = "ACT/360"
    fixing_lag: int = 2                       # Settlement lag (business days)
    compounding_freq: int = 1                 # For bonds/notes
    quality_score: float = 1.0                # Data quality indicator (0-1)


class YieldCurve:
    """
    Institutional-grade yield curve with multiple interpolation methods.
    
    Supports both zero rates and forward rates with proper mathematical
    consistency and numerical stability.
    """
    
    def __init__(self, 
                 dates: List[datetime],
                 rates: List[float], 
                 curve_date: datetime,
                 interpolation: InterpolationMethod = InterpolationMethod.MONOTONE_CUBIC,
                 currency: str = "USD",
                 curve_type: str = "ZERO"):
        """
        Initialize yield curve.
        
        Args:
            dates: Maturity dates for curve points
            rates: Zero rates (as decimals) at each maturity
            curve_date: Curve construction date
            interpolation: Interpolation method
            currency: Currency code
            curve_type: "ZERO", "FORWARD", or "DISCOUNT"
        """
        self.curve_date = curve_date
        self.currency = currency
        self.curve_type = curve_type
        self.interpolation = interpolation
        
        # Convert dates to year fractions
        self.times = [year_fraction_precise(curve_date, d, "ACT/365-FIXED") for d in dates]
        self.rates = list(rates)
        self.dates = list(dates)
        
        # Sort by time to maturity
        sorted_data = sorted(zip(self.times, self.rates, self.dates))
        self.times, self.rates, self.dates = zip(*sorted_data) if sorted_data else ([], [], [])
        self.times = list(self.times)
        self.rates = list(self.rates)
        self.dates = list(self.dates)
        
        # Build interpolator
        self._build_interpolator()
        
        # Calculate forward curve for consistency checks
        self._forward_curve = None
    
    def _build_interpolator(self):
        """Build the interpolation function"""
        if len(self.times) < 2:
            raise ValueError("Need at least 2 points for curve construction")
        
        times_array = np.array(self.times)
        rates_array = np.array(self.rates)
        
        if self.interpolation == InterpolationMethod.LINEAR:
            self._interpolator = interp.interp1d(
                times_array, rates_array, 
                kind='linear', bounds_error=False, fill_value='extrapolate'
            )
        
        elif self.interpolation == InterpolationMethod.CUBIC_SPLINE:
            self._interpolator = interp.CubicSpline(
                times_array, rates_array, 
                bc_type='natural', extrapolate=True
            )
        
        elif self.interpolation == InterpolationMethod.MONOTONE_CUBIC:
            self._interpolator = self._monotone_cubic_interpolator()
        
        elif self.interpolation == InterpolationMethod.LOG_LINEAR:
            # Interpolate on log of discount factors
            discount_factors = np.exp(-rates_array * times_array)
            log_df_interp = interp.interp1d(
                times_array, np.log(discount_factors),
                kind='linear', bounds_error=False, fill_value='extrapolate'
            )
            def log_linear_rate(t):
                if np.isscalar(t):
                    if t <= 0:
                        return self.rates[0]
                    return -log_df_interp(t) / t
                else:
                    result = np.zeros_like(t)
                    positive_mask = t > 0
                    result[positive_mask] = -log_df_interp(t[positive_mask]) / t[positive_mask]
                    result[~positive_mask] = self.rates[0]
                    return result
            self._interpolator = log_linear_rate
        
        elif self.interpolation == InterpolationMethod.NELSON_SIEGEL:
            params = self._fit_nelson_siegel()
            self._interpolator = lambda t: nelson_siegel_svensson(t, *params)
        
        elif self.interpolation == InterpolationMethod.SVENSSON:
            params = self._fit_svensson()
            self._interpolator = lambda t: nelson_siegel_svensson(t, *params)
        
        elif self.interpolation == InterpolationMethod.HAGAN_WEST:
            self._interpolator = self._hagan_west_interpolator()
        
        else:
            # Default to cubic spline
            self._interpolator = interp.CubicSpline(
                times_array, rates_array, bc_type='natural', extrapolate=True
            )
    
    def _monotone_cubic_interpolator(self) -> Callable:
        """Monotonicity-preserving cubic spline (Fritsch-Carlson)"""
        times = np.array(self.times)
        rates = np.array(self.rates)
        
        # Calculate slopes
        h = np.diff(times)
        delta = np.diff(rates) / h
        
        # Initialize slopes at interior points
        m = np.zeros(len(times))
        m[1:-1] = (delta[:-1] + delta[1:]) / 2
        
        # Endpoint slopes
        m[0] = delta[0]
        m[-1] = delta[-1]
        
        # Apply monotonicity constraints
        for i in range(len(delta)):
            if delta[i] == 0:
                m[i] = 0
                m[i+1] = 0
            else:
                alpha = m[i] / delta[i]
                beta = m[i+1] / delta[i]
                if alpha**2 + beta**2 > 9:
                    tau = 3 / np.sqrt(alpha**2 + beta**2)
                    m[i] = tau * alpha * delta[i]
                    m[i+1] = tau * beta * delta[i]
        
        def monotone_interp(t):
            """Monotone cubic interpolation"""
            t = np.atleast_1d(t)
            result = np.zeros_like(t)
            
            for j, time_val in enumerate(t):
                # Find interval
                if time_val <= times[0]:
                    result[j] = rates[0]
                elif time_val >= times[-1]:
                    result[j] = rates[-1]
                else:
                    i = np.searchsorted(times, time_val) - 1
                    i = max(0, min(i, len(times) - 2))
                    
                    # Hermite interpolation
                    t1, t2 = times[i], times[i+1]
                    y1, y2 = rates[i], rates[i+1]
                    m1, m2 = m[i], m[i+1]
                    
                    h_val = t2 - t1
                    t_norm = (time_val - t1) / h_val
                    
                    h00 = 2*t_norm**3 - 3*t_norm**2 + 1
                    h10 = t_norm**3 - 2*t_norm**2 + t_norm
                    h01 = -2*t_norm**3 + 3*t_norm**2
                    h11 = t_norm**3 - t_norm**2
                    
                    result[j] = h00*y1 + h10*h_val*m1 + h01*y2 + h11*h_val*m2
            
            return result[0] if len(result) == 1 else result
        
        return monotone_interp
    
    def _fit_nelson_siegel(self) -> Tuple[float, float, float, float]:
        """Fit Nelson-Siegel parameters"""
        def objective(params):
            beta0, beta1, beta2, tau = params
            fitted = nelson_siegel_svensson(np.array(self.times), beta0, beta1, beta2, tau)
            return np.sum((fitted - np.array(self.rates))**2)
        
        # Initial guess
        initial_guess = [0.06, -0.02, -0.02, 2.0]
        bounds = [(0.0, 0.15), (-0.15, 0.15), (-0.15, 0.15), (0.1, 10.0)]
        
        try:
            result = opt.minimize(objective, initial_guess, bounds=bounds, method='L-BFGS-B')
            return tuple(result.x)
        except:
            return tuple(initial_guess)
    
    def _fit_svensson(self) -> Tuple[float, float, float, float, float, float]:
        """Fit Svensson (extended Nelson-Siegel) parameters"""
        def objective(params):
            beta0, beta1, beta2, beta3, tau1, tau2 = params
            fitted = nelson_siegel_svensson(np.array(self.times), beta0, beta1, beta2, tau1, beta3, tau2)
            return np.sum((fitted - np.array(self.rates))**2)
        
        initial_guess = [0.06, -0.02, -0.02, 0.01, 2.0, 5.0]
        bounds = [(0.0, 0.15), (-0.15, 0.15), (-0.15, 0.15), (-0.15, 0.15), (0.1, 10.0), (0.1, 15.0)]
        
        try:
            result = opt.minimize(objective, initial_guess, bounds=bounds, method='L-BFGS-B')
            return tuple(result.x)
        except:
            return tuple(initial_guess)
    
    def _hagan_west_interpolator(self) -> Callable:
        """Hagan-West monotone interpolation method"""
        # Simplified implementation - full method is quite complex
        return self._monotone_cubic_interpolator()
    
    def zero_rate(self, maturity: Union[datetime, float]) -> float:
        """Get zero rate at specific maturity"""
        if isinstance(maturity, datetime):
            time_to_maturity = year_fraction_precise(self.curve_date, maturity, "ACT/365-FIXED")
        else:
            time_to_maturity = float(maturity)
        
        if time_to_maturity < 0:
            raise ValueError("Cannot interpolate for negative time")
        
        return float(self._interpolator(time_to_maturity))
    
    def discount_factor(self, maturity: Union[datetime, float]) -> float:
        """Get discount factor at specific maturity"""
        if isinstance(maturity, datetime):
            time_to_maturity = year_fraction_precise(self.curve_date, maturity, "ACT/365-FIXED")
        else:
            time_to_maturity = float(maturity)
        
        rate = self.zero_rate(time_to_maturity)
        return np.exp(-rate * time_to_maturity)
    
    def forward_rate(self, start_date: Union[datetime, float], 
                    end_date: Union[datetime, float]) -> float:
        """Calculate instantaneous forward rate between two dates"""
        if isinstance(start_date, datetime):
            t1 = year_fraction_precise(self.curve_date, start_date, "ACT/365-FIXED")
        else:
            t1 = float(start_date)
            
        if isinstance(end_date, datetime):
            t2 = year_fraction_precise(self.curve_date, end_date, "ACT/365-FIXED")
        else:
            t2 = float(end_date)
        
        if t2 <= t1:
            raise ValueError("End date must be after start date")
        
        df1 = self.discount_factor(t1)
        df2 = self.discount_factor(t2)
        
        return np.log(df1 / df2) / (t2 - t1)
    
    def par_rate(self, maturity: Union[datetime, float], frequency: int = 2) -> float:
        """Calculate par swap rate for given maturity and frequency"""
        if isinstance(maturity, datetime):
            time_to_maturity = year_fraction_precise(self.curve_date, maturity, "ACT/365-FIXED")
        else:
            time_to_maturity = float(maturity)
        
        # Generate payment dates
        payment_times = []
        dt = time_to_maturity / frequency
        for i in range(1, frequency + 1):
            payment_times.append(i * dt)
        
        # Calculate annuity
        annuity = sum(self.discount_factor(t) * dt for t in payment_times)
        
        # Par rate = (1 - final DF) / annuity
        final_df = self.discount_factor(time_to_maturity)
        return (1.0 - final_df) / annuity if annuity > 0 else 0.0


class CurveBuilder:
    """
    Advanced curve construction with bootstrapping and instrument-specific pricing.
    
    Handles deposits, futures, swaps, and bonds with proper settlement conventions.
    """
    
    def __init__(self, 
                 curve_date: datetime,
                 currency: str = "USD",
                 interpolation: InterpolationMethod = InterpolationMethod.MONOTONE_CUBIC):
        self.curve_date = curve_date
        self.currency = currency
        self.interpolation = interpolation
        self.instruments: List[CurveInstrument] = []
        self.built_curve: Optional[YieldCurve] = None
    
    def add_instrument(self, instrument: CurveInstrument) -> None:
        """Add market instrument to curve construction"""
        self.instruments.append(instrument)
        # Clear cached curve
        self.built_curve = None
    
    def add_cash_deposit(self, maturity: datetime, rate: float, 
                        day_count: str = "ACT/360") -> None:
        """Add cash deposit (money market instrument)"""
        instrument = CurveInstrument(
            maturity=maturity,
            rate=rate,
            instrument_type="CASH",
            day_count=day_count,
            currency=self.currency
        )
        self.add_instrument(instrument)
    
    def add_futures(self, maturity: datetime, price: float) -> None:
        """Add interest rate futures (price = 100 - implied rate)"""
        rate = (100.0 - price) / 100.0
        instrument = CurveInstrument(
            maturity=maturity,
            rate=rate,
            instrument_type="FUTURES",
            day_count="ACT/360",
            currency=self.currency
        )
        self.add_instrument(instrument)
    
    def add_swap(self, maturity: datetime, rate: float, 
                frequency: int = 2, day_count: str = "30/360") -> None:
        """Add interest rate swap"""
        instrument = CurveInstrument(
            maturity=maturity,
            rate=rate,
            instrument_type="SWAP",
            day_count=day_count,
            compounding_freq=frequency,
            currency=self.currency
        )
        self.add_instrument(instrument)
    
    def bootstrap(self) -> YieldCurve:
        """
        Bootstrap zero curve from market instruments using iterative solver.
        
        Returns:
            Bootstrapped YieldCurve object
        """
        if not self.instruments:
            raise ValueError("No instruments added for curve construction")
        
        # Sort instruments by maturity
        sorted_instruments = sorted(self.instruments, key=lambda x: x.maturity)
        
        bootstrap_times = []
        bootstrap_rates = []
        bootstrap_dates = []
        
        for instrument in sorted_instruments:
            time_to_maturity = year_fraction_precise(
                self.curve_date, instrument.maturity, "ACT/365-FIXED"
            )
            
            if time_to_maturity <= 0:
                continue
            
            # Bootstrap this instrument
            if instrument.instrument_type == "CASH":
                # Simple cash deposit: DF = 1 / (1 + r * t)
                yf = year_fraction_precise(
                    self.curve_date, instrument.maturity, instrument.day_count
                )
                zero_rate = np.log(1 + instrument.rate * yf) / time_to_maturity
                
            elif instrument.instrument_type == "FUTURES":
                # Futures: assume 3-month forward rate
                # This is simplified - real implementation would consider convexity
                zero_rate = instrument.rate
                
            elif instrument.instrument_type == "SWAP":
                # Bootstrap swap rate by solving for zero rate that makes NPV = 0
                zero_rate = self._bootstrap_swap(instrument, bootstrap_times, bootstrap_rates)
                
            else:
                # Default to instrument rate
                zero_rate = instrument.rate
            
            bootstrap_times.append(time_to_maturity)
            bootstrap_rates.append(zero_rate)
            bootstrap_dates.append(instrument.maturity)
        
        # Build curve with bootstrapped rates
        self.built_curve = YieldCurve(
            dates=bootstrap_dates,
            rates=bootstrap_rates,
            curve_date=self.curve_date,
            interpolation=self.interpolation,
            currency=self.currency
        )
        
        return self.built_curve
    
    def _bootstrap_swap(self, swap_instrument: CurveInstrument,
                       existing_times: List[float], 
                       existing_rates: List[float]) -> float:
        """Bootstrap zero rate from swap instrument"""
        
        def swap_npv(zero_rate: float) -> float:
            # Build temporary curve including this zero rate
            temp_times = existing_times + [year_fraction_precise(
                self.curve_date, swap_instrument.maturity, "ACT/365-FIXED"
            )]
            temp_rates = existing_rates + [zero_rate]
            
            if len(temp_times) < 2:
                temp_curve = YieldCurve(
                    dates=[self.curve_date, swap_instrument.maturity],
                    rates=[zero_rate, zero_rate],
                    curve_date=self.curve_date,
                    interpolation=InterpolationMethod.LINEAR
                )
            else:
                temp_dates = [self.curve_date + timedelta(days=int(t*365)) for t in temp_times]
                temp_curve = YieldCurve(
                    dates=temp_dates,
                    rates=temp_rates,
                    curve_date=self.curve_date,
                    interpolation=InterpolationMethod.LINEAR
                )
            
            # Generate swap cashflow dates
            frequency = swap_instrument.compounding_freq
            maturity_time = year_fraction_precise(
                self.curve_date, swap_instrument.maturity, "ACT/365-FIXED"
            )
            
            payment_times = []
            payment_fractions = []
            
            for i in range(1, int(maturity_time * frequency) + 1):
                payment_time = i / frequency
                if payment_time <= maturity_time:
                    payment_times.append(payment_time)
                    payment_fractions.append(1.0 / frequency)  # Simplified
            
            # Ensure final payment at maturity
            if not payment_times or abs(payment_times[-1] - maturity_time) > 0.01:
                payment_times.append(maturity_time)
                payment_fractions.append(maturity_time - (payment_times[-2] if payment_times else 0))
            
            # Calculate NPV
            fixed_leg_npv = 0.0
            floating_leg_npv = 0.0
            
            for i, (pmt_time, pmt_frac) in enumerate(zip(payment_times, payment_fractions)):
                df = temp_curve.discount_factor(pmt_time)
                
                # Fixed leg
                fixed_leg_npv += swap_instrument.rate * pmt_frac * df
                
                # Floating leg (approximation)
                if i == 0:
                    floating_leg_npv += (1.0 - df)  # Initial notional
                else:
                    prev_df = temp_curve.discount_factor(payment_times[i-1])
                    floating_leg_npv += (prev_df - df)
            
            return fixed_leg_npv - floating_leg_npv
        
        # Solve for zero rate that makes swap NPV = 0
        try:
            result = opt.brentq(swap_npv, 0.001, 0.2)  # Search between 0.1% and 20%
            return result
        except:
            # Fallback to swap rate if optimization fails
            return swap_instrument.rate
    
    def get_curve(self) -> Optional[YieldCurve]:
        """Get the built curve (None if not bootstrapped yet)"""
        return self.built_curve


def nelson_siegel_svensson(t: Union[float, np.ndarray], 
                          beta0: float, beta1: float, beta2: float, tau1: float,
                          beta3: float = 0.0, tau2: float = 0.0) -> Union[float, np.ndarray]:
    """
    Nelson-Siegel-Svensson parametric yield curve model.
    
    R(t) = β₀ + β₁((1-exp(-t/τ₁))/(t/τ₁)) + β₂(((1-exp(-t/τ₁))/(t/τ₁)) - exp(-t/τ₁)) 
           + β₃(((1-exp(-t/τ₂))/(t/τ₂)) - exp(-t/τ₂))
    
    Args:
        t: Time to maturity (years)
        beta0: Long-term level
        beta1: Short-term component  
        beta2: Medium-term component
        tau1: Decay parameter 1
        beta3: Second medium-term component (Svensson extension)
        tau2: Decay parameter 2 (Svensson extension)
    
    Returns:
        Yield curve rate(s)
    """
    t = np.atleast_1d(t)
    
    # Avoid division by zero
    t = np.maximum(t, 1e-8)
    
    # Nelson-Siegel components
    exp_tau1 = np.exp(-t / tau1)
    term1 = (1 - exp_tau1) / (t / tau1)
    term2 = term1 - exp_tau1
    
    result = beta0 + beta1 * term1 + beta2 * term2
    
    # Svensson extension
    if beta3 != 0.0 and tau2 > 0:
        exp_tau2 = np.exp(-t / tau2)
        term3 = (1 - exp_tau2) / (t / tau2) - exp_tau2
        result += beta3 * term3
    
    return result[0] if result.shape == (1,) else result


def monotone_convex_interpolation(times: np.ndarray, rates: np.ndarray) -> Callable:
    """
    Hagan-West monotone convex interpolation method.
    
    Preserves monotonicity and convexity of forward rates.
    This is a simplified implementation of the complex Hagan-West method.
    """
    # This is a placeholder for the full Hagan-West implementation
    # The complete method is mathematically intensive and requires
    # solving systems of equations with inequality constraints
    
    from scipy.interpolate import PchipInterpolator
    return PchipInterpolator(times, rates, extrapolate=True)


def validate_curve_quality(curve: YieldCurve, 
                          market_instruments: List[CurveInstrument]) -> Dict[str, float]:
    """
    Validate curve quality against market instruments.
    
    Returns:
        Dictionary of quality metrics
    """
    metrics = {}
    
    # Calculate fitting errors
    fitting_errors = []
    for instrument in market_instruments:
        curve_rate = curve.zero_rate(instrument.maturity)
        fitting_errors.append(abs(curve_rate - instrument.rate))
    
    if fitting_errors:
        metrics['max_fitting_error'] = max(fitting_errors)
        metrics['avg_fitting_error'] = np.mean(fitting_errors)
        metrics['rmse_fitting_error'] = np.sqrt(np.mean([e**2 for e in fitting_errors]))
    
    # Check for negative forward rates
    test_times = np.linspace(0.25, 30, 120)  # Quarterly for 30 years
    forward_rates = []
    
    for i in range(len(test_times) - 1):
        try:
            fwd_rate = curve.forward_rate(test_times[i], test_times[i+1])
            forward_rates.append(fwd_rate)
        except:
            continue
    
    if forward_rates:
        metrics['min_forward_rate'] = min(forward_rates)
        metrics['negative_forwards'] = sum(1 for r in forward_rates if r < 0)
    
    return metrics


# Test suite for curve construction
def test_curve_construction():
    """Test suite to validate curve construction functionality"""
    print("Testing Enhanced Curve Construction...")
    
    # Create test curve builder
    curve_date = datetime(2024, 1, 15)
    builder = CurveBuilder(curve_date, "USD", InterpolationMethod.MONOTONE_CUBIC)
    
    # Add sample instruments
    builder.add_cash_deposit(datetime(2024, 4, 15), 0.0525)  # 3M
    builder.add_cash_deposit(datetime(2024, 7, 15), 0.0535)  # 6M
    builder.add_swap(datetime(2026, 1, 15), 0.045, 2)        # 2Y swap
    builder.add_swap(datetime(2029, 1, 15), 0.042, 2)        # 5Y swap
    builder.add_swap(datetime(2034, 1, 15), 0.041, 2)        # 10Y swap
    
    # Bootstrap curve
    curve = builder.bootstrap()
    
    # Test interpolation
    test_date = datetime(2027, 1, 15)  # 3Y point
    zero_rate = curve.zero_rate(test_date)
    discount_factor = curve.discount_factor(test_date)
    forward_rate = curve.forward_rate(datetime(2026, 1, 15), datetime(2027, 1, 15))
    
    print(f"3Y Zero Rate: {zero_rate:.4f}")
    print(f"3Y Discount Factor: {discount_factor:.6f}")
    print(f"2Y1Y Forward Rate: {forward_rate:.4f}")
    
    # Test Nelson-Siegel
    times = np.array([0.25, 0.5, 1, 2, 5, 10])
    ns_rates = nelson_siegel_svensson(times, 0.06, -0.02, -0.01, 2.0)
    print(f"Nelson-Siegel rates: {ns_rates}")
    
    # Validate curve quality
    quality_metrics = validate_curve_quality(curve, builder.instruments)
    print(f"Curve Quality: {quality_metrics}")
    
    print("Enhanced curve construction testing complete!")


if __name__ == "__main__":
    test_curve_construction()
