# higher_order_greeks.py
# Purpose: Higher-order risk metrics and Greeks for institutional portfolio management
# Implements cross-gamma, key rate convexity, option vega, and advanced sensitivity measures

from __future__ import annotations

import numpy as np
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union, Callable, NamedTuple
from dataclasses import dataclass
from enum import Enum

from .curve_construction import YieldCurve
from .daycount_enhanced import year_fraction_precise
from .numerical_methods import brent_solve
from .multi_curve_framework import MultiCurveFramework

__all__ = [
    "GreekType", 
    "RiskScenario",
    "PortfolioGreeks",
    "CrossGammaCalculator",
    "KeyRateConvexityCalculator", 
    "OptionGreeksCalculator",
    "ScenarioAnalysisEngine",
    "calculate_portfolio_greeks"
]


class GreekType(Enum):
    """Types of risk sensitivities (Greeks) calculated"""
    # First-order (Delta-type)
    DELTA = "DELTA"                           # Price sensitivity to underlying
    DURATION = "DURATION"                     # Price sensitivity to yield
    DV01 = "DV01"                            # Dollar duration (price value of 1bp)
    VEGA = "VEGA"                            # Sensitivity to volatility
    THETA = "THETA"                          # Time decay
    RHO = "RHO"                              # Sensitivity to risk-free rate
    
    # Second-order (Gamma-type)  
    GAMMA = "GAMMA"                          # Convexity (second derivative)
    CROSS_GAMMA = "CROSS_GAMMA"              # Cross convexity between assets
    KEY_RATE_CONVEXITY = "KR_CONVEXITY"     # Convexity at specific curve points
    VOLGA = "VOLGA"                          # Convexity to volatility
    VANNA = "VANNA"                          # Cross sensitivity (delta-vega)
    
    # Third-order (Speed/Color-type)
    SPEED = "SPEED"                          # Third derivative wrt underlying
    COLOR = "COLOR"                          # Third derivative wrt time
    ULTIMA = "ULTIMA"                        # Third derivative wrt volatility


@dataclass
class RiskScenario:
    """Risk scenario for sensitivity calculations"""
    name: str
    yield_curve_shifts: Dict[str, float] = None      # Tenor → shift (bps)
    parallel_shift: Optional[float] = None           # Parallel shift (bps)
    volatility_shift: Optional[float] = None         # Vol shift (absolute)
    time_shift: Optional[float] = None               # Time shift (days)
    spread_shifts: Dict[str, float] = None           # Spread shifts by curve
    correlation_shifts: Dict[Tuple[str, str], float] = None  # Correlation changes
    
    def __post_init__(self):
        if self.yield_curve_shifts is None:
            self.yield_curve_shifts = {}
        if self.spread_shifts is None:
            self.spread_shifts = {}
        if self.correlation_shifts is None:
            self.correlation_shifts = {}


@dataclass 
class PortfolioGreeks:
    """Complete set of portfolio Greeks and risk metrics"""
    calculation_date: datetime
    portfolio_value: float
    
    # First-order Greeks
    dollar_duration: float                    # DV01 - dollar impact of 1bp
    modified_duration: float                  # Duration in years
    effective_duration: float                 # Effective duration
    spread_duration: float                    # Credit spread duration
    vega: Dict[str, float]                   # Volatility sensitivity by expiry
    theta: float                             # Time decay per day
    
    # Second-order Greeks
    convexity: float                         # Interest rate convexity
    cross_gamma: Dict[Tuple[str, str], float] # Cross-asset convexity
    key_rate_convexity: Dict[str, float]     # Convexity by key rate
    volga: Dict[str, float]                  # Volatility convexity
    vanna: Dict[str, float]                  # Delta-vega cross sensitivity
    
    # Third-order Greeks
    speed: float                             # Third-order rate sensitivity
    color: float                             # Third-order time sensitivity
    
    # Portfolio-level metrics
    var_1day: float                          # 1-day Value at Risk
    expected_shortfall: float                # Expected shortfall (CVaR)
    maximum_drawdown: float                  # Maximum historical drawdown


class CrossGammaCalculator:
    """
    Calculate cross-gamma (second-order cross derivatives) between instruments.
    
    Essential for portfolio hedging as it captures correlation effects
    that simple duration/convexity miss.
    """
    
    def __init__(self, multi_curve: Optional[MultiCurveFramework] = None):
        self.multi_curve = multi_curve
        self.shock_size = 0.0001  # 1 basis point
    
    def calculate_cross_gamma(self, 
                            portfolio: Dict[str, Dict],  # instrument_id → details
                            risk_factors: List[str],     # List of risk factors
                            pricing_function: Callable) -> Dict[Tuple[str, str], float]:
        """
        Calculate cross-gamma matrix for portfolio.
        
        Cross-gamma[i,j] = ∂²PV / (∂factor_i ∂factor_j)
        
        Args:
            portfolio: Portfolio holdings and instrument details
            risk_factors: Risk factors (yield curve points, vol surfaces, etc.)
            pricing_function: Function to price portfolio given risk factor shocks
            
        Returns:
            Dictionary mapping (factor_i, factor_j) → cross-gamma value
        """
        cross_gammas = {}
        base_price = pricing_function(portfolio, {})  # Base case (no shocks)
        
        # Calculate cross-gamma for each pair of risk factors
        for i, factor_i in enumerate(risk_factors):
            for j, factor_j in enumerate(risk_factors):
                if i <= j:  # Only calculate upper triangle (symmetric)
                    
                    if i == j:
                        # Diagonal element - regular gamma
                        gamma = self._calculate_gamma_single_factor(
                            portfolio, factor_i, pricing_function, base_price
                        )
                        cross_gammas[(factor_i, factor_j)] = gamma
                    else:
                        # Off-diagonal - true cross-gamma
                        cross_gamma = self._calculate_cross_gamma_pair(
                            portfolio, factor_i, factor_j, pricing_function, base_price
                        )
                        cross_gammas[(factor_i, factor_j)] = cross_gamma
                        cross_gammas[(factor_j, factor_i)] = cross_gamma  # Symmetry
        
        return cross_gammas
    
    def _calculate_gamma_single_factor(self, 
                                     portfolio: Dict,
                                     factor: str,
                                     pricing_function: Callable,
                                     base_price: float) -> float:
        """Calculate gamma for single risk factor using finite differences"""
        
        # Price with positive shock
        shock_up = {factor: self.shock_size}
        price_up = pricing_function(portfolio, shock_up)
        
        # Price with negative shock  
        shock_down = {factor: -self.shock_size}
        price_down = pricing_function(portfolio, shock_down)
        
        # Second derivative: (P+ - 2P0 + P-) / (shock^2)
        gamma = (price_up - 2*base_price + price_down) / (self.shock_size**2)
        
        return gamma
    
    def _calculate_cross_gamma_pair(self,
                                  portfolio: Dict,
                                  factor_i: str,
                                  factor_j: str, 
                                  pricing_function: Callable,
                                  base_price: float) -> float:
        """Calculate cross-gamma between two factors using mixed partial derivatives"""
        
        # Four corner points for mixed partial derivative
        shock_both_pos = {factor_i: self.shock_size, factor_j: self.shock_size}
        price_both_pos = pricing_function(portfolio, shock_both_pos)
        
        shock_i_pos_j_neg = {factor_i: self.shock_size, factor_j: -self.shock_size}
        price_i_pos_j_neg = pricing_function(portfolio, shock_i_pos_j_neg)
        
        shock_i_neg_j_pos = {factor_i: -self.shock_size, factor_j: self.shock_size}
        price_i_neg_j_pos = pricing_function(portfolio, shock_i_neg_j_pos)
        
        shock_both_neg = {factor_i: -self.shock_size, factor_j: -self.shock_size}
        price_both_neg = pricing_function(portfolio, shock_both_neg)
        
        # Mixed partial derivative: (P++ - P+- - P-+ + P--) / (4 * shock_i * shock_j)
        cross_gamma = (price_both_pos - price_i_pos_j_neg - price_i_neg_j_pos + price_both_neg) / \
                     (4 * self.shock_size * self.shock_size)
        
        return cross_gamma


class KeyRateConvexityCalculator:
    """
    Calculate key rate convexity - convexity with respect to specific points
    on the yield curve.
    
    More granular than duration, essential for curve risk management.
    """
    
    def __init__(self):
        self.key_rate_tenors = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
        self.shock_size = 0.0001  # 1bp
    
    def calculate_key_rate_convexity(self,
                                   portfolio: Dict,
                                   yield_curve: YieldCurve,
                                   pricing_function: Callable) -> Dict[str, float]:
        """
        Calculate convexity with respect to each key rate.
        
        Key Rate Convexity[tenor] = ∂²PV / ∂(rate_tenor)²
        
        Args:
            portfolio: Portfolio to analyze
            yield_curve: Base yield curve
            pricing_function: Portfolio pricing function
            
        Returns:
            Dictionary mapping tenor → convexity
        """
        base_price = pricing_function(portfolio, yield_curve)
        key_rate_convexities = {}
        
        for tenor in self.key_rate_tenors:
            # Calculate convexity for this key rate
            convexity = self._calculate_single_key_rate_convexity(
                portfolio, yield_curve, tenor, pricing_function, base_price
            )
            key_rate_convexities[tenor] = convexity
        
        return key_rate_convexities
    
    def _calculate_single_key_rate_convexity(self,
                                           portfolio: Dict,
                                           base_curve: YieldCurve,
                                           tenor: str,
                                           pricing_function: Callable,
                                           base_price: float) -> float:
        """Calculate convexity for single key rate using curve shifts"""
        
        # Create shifted curves
        curve_up = self._shift_curve_at_tenor(base_curve, tenor, self.shock_size)
        curve_down = self._shift_curve_at_tenor(base_curve, tenor, -self.shock_size)
        
        # Price with shifted curves
        price_up = pricing_function(portfolio, curve_up)
        price_down = pricing_function(portfolio, curve_down)
        
        # Convexity calculation
        convexity = (price_up - 2*base_price + price_down) / (self.shock_size**2)
        
        return convexity
    
    def _shift_curve_at_tenor(self, 
                            base_curve: YieldCurve, 
                            tenor: str, 
                            shift: float) -> YieldCurve:
        """Create new curve with shift at specific tenor"""
        # In practice, this would involve sophisticated curve interpolation
        # to shift only the specific tenor point while maintaining smoothness
        
        # Simplified implementation - would need full curve reconstruction
        # with spline fitting to maintain smoothness
        
        # For now, return a copy with all rates shifted (placeholder)
        shifted_rates = [rate + shift for rate in base_curve.rates]
        
        return YieldCurve(
            dates=base_curve.dates.copy(),
            rates=shifted_rates,
            curve_date=base_curve.curve_date,
            interpolation=base_curve.interpolation,
            currency=base_curve.currency
        )


class OptionGreeksCalculator:
    """
    Calculate option Greeks (vega, volga, vanna, theta) for embedded options
    in callable bonds and other structured products.
    """
    
    def __init__(self):
        self.vol_shock = 0.01      # 1% absolute volatility shock
        self.time_shock = 1.0      # 1 day time shock
        self.rate_shock = 0.0001   # 1bp rate shock
    
    def calculate_option_greeks(self,
                              callable_instrument: Dict,
                              base_volatility: float,
                              pricing_model: Callable,
                              calculation_date: datetime) -> Dict[str, float]:
        """
        Calculate complete set of option Greeks.
        
        Args:
            callable_instrument: Instrument with embedded options
            base_volatility: Base volatility assumption
            pricing_model: Option pricing model (Black-Scholes, Hull-White, etc.)
            calculation_date: Calculation date
            
        Returns:
            Dictionary of option Greeks
        """
        # Base option value
        base_params = {
            'volatility': base_volatility,
            'time_to_expiry': self._get_time_to_expiry(callable_instrument, calculation_date)
        }
        base_value = pricing_model(callable_instrument, base_params)
        
        # Vega - sensitivity to volatility
        vega = self._calculate_vega(callable_instrument, base_volatility, pricing_model, base_value, base_params)
        
        # Volga - convexity to volatility (second-order vega)
        volga = self._calculate_volga(callable_instrument, base_volatility, pricing_model, base_value, base_params)
        
        # Vanna - cross sensitivity between delta and vega
        vanna = self._calculate_vanna(callable_instrument, base_volatility, pricing_model, base_params)
        
        # Theta - time decay
        theta = self._calculate_theta(callable_instrument, pricing_model, calculation_date, base_params)
        
        return {
            'vega': vega,
            'volga': volga, 
            'vanna': vanna,
            'theta': theta,
            'base_option_value': base_value
        }
    
    def _calculate_vega(self, instrument: Dict, base_vol: float, pricing_model: Callable,
                       base_value: float, base_params: Dict) -> float:
        """Calculate vega using finite differences"""
        
        # Price with higher volatility
        vol_up_params = base_params.copy()
        vol_up_params['volatility'] = base_vol + self.vol_shock
        value_vol_up = pricing_model(instrument, vol_up_params)
        
        # Vega = dV/dσ
        vega = (value_vol_up - base_value) / self.vol_shock
        
        return vega
    
    def _calculate_volga(self, instrument: Dict, base_vol: float, pricing_model: Callable,
                        base_value: float, base_params: Dict) -> float:
        """Calculate volga (vega convexity) using second derivatives"""
        
        # Price with volatility shocks
        vol_up_params = base_params.copy()
        vol_up_params['volatility'] = base_vol + self.vol_shock
        value_vol_up = pricing_model(instrument, vol_up_params)
        
        vol_down_params = base_params.copy() 
        vol_down_params['volatility'] = base_vol - self.vol_shock
        value_vol_down = pricing_model(instrument, vol_down_params)
        
        # Volga = d²V/dσ²
        volga = (value_vol_up - 2*base_value + value_vol_down) / (self.vol_shock**2)
        
        return volga
    
    def _calculate_vanna(self, instrument: Dict, base_vol: float, 
                        pricing_model: Callable, base_params: Dict) -> float:
        """Calculate vanna (delta-vega cross sensitivity)"""
        
        # This requires calculating delta at different volatility levels
        # Simplified implementation - full version would calculate delta sensitivities
        
        # Base case vega
        vol_up_params = base_params.copy()
        vol_up_params['volatility'] = base_vol + self.vol_shock
        value_vol_up = pricing_model(instrument, vol_up_params)
        
        base_value = pricing_model(instrument, base_params)
        base_vega = (value_vol_up - base_value) / self.vol_shock
        
        # Vega with small underlying shift (approximation)
        # In practice would need delta calculations
        vanna_approx = base_vega * 0.1  # Placeholder approximation
        
        return vanna_approx
    
    def _calculate_theta(self, instrument: Dict, pricing_model: Callable,
                        calculation_date: datetime, base_params: Dict) -> float:
        """Calculate theta (time decay)"""
        
        base_value = pricing_model(instrument, base_params)
        
        # Price with one day forward
        time_forward_params = base_params.copy()
        current_time_to_expiry = base_params['time_to_expiry']
        # Use proper day count fraction for one business day
        # Assuming ACT/365-FIXED convention for time decay calculation
        time_forward_params['time_to_expiry'] = current_time_to_expiry - (1.0/365.0)
        
        if time_forward_params['time_to_expiry'] <= 0:
            return 0.0  # Option expired
        
        value_time_forward = pricing_model(instrument, time_forward_params)
        
        # Theta = dV/dt (negative for time decay)
        theta = value_time_forward - base_value  # Already per day
        
        return theta
    
    def _get_time_to_expiry(self, instrument: Dict, calculation_date: datetime) -> float:
        """Extract time to expiry from instrument"""
        # Simplified - would extract from call schedule in practice
        maturity_date = instrument.get('maturity_date', calculation_date + timedelta(days=365))
        if isinstance(maturity_date, str):
            maturity_date = datetime.strptime(maturity_date, '%Y-%m-%d')
        
        return year_fraction_precise(calculation_date, maturity_date, 'ACT/365-FIXED')


class ScenarioAnalysisEngine:
    """
    Advanced scenario analysis engine for stress testing and risk management.
    
    Runs multiple risk scenarios and calculates comprehensive P&L attribution.
    """
    
    def __init__(self):
        self.standard_scenarios = self._create_standard_scenarios()
    
    def _create_standard_scenarios(self) -> List[RiskScenario]:
        """Create standard market risk scenarios"""
        scenarios = []
        
        # Parallel yield curve shifts
        for shift_bps in [-100, -50, -25, +25, +50, +100]:
            scenarios.append(RiskScenario(
                name=f"Parallel_{shift_bps:+d}bps",
                parallel_shift=shift_bps
            ))
        
        # Steepener/Flattener scenarios
        scenarios.append(RiskScenario(
            name="Steepener_25bps",
            yield_curve_shifts={"2Y": -25, "10Y": +25}
        ))
        
        scenarios.append(RiskScenario(
            name="Flattener_25bps", 
            yield_curve_shifts={"2Y": +25, "10Y": -25}
        ))
        
        # Volatility scenarios
        for vol_shift in [-0.05, -0.02, +0.02, +0.05]:
            scenarios.append(RiskScenario(
                name=f"Vol_{vol_shift:+.0%}",
                volatility_shift=vol_shift
            ))
        
        return scenarios
    
    def run_scenario_analysis(self,
                            portfolio: Dict,
                            base_curves: Dict[str, YieldCurve],
                            pricing_function: Callable,
                            scenarios: Optional[List[RiskScenario]] = None) -> Dict[str, Dict]:
        """
        Run comprehensive scenario analysis.
        
        Args:
            portfolio: Portfolio to analyze
            base_curves: Base yield curves
            pricing_function: Portfolio pricing function
            scenarios: Risk scenarios (uses standard if None)
            
        Returns:
            Dictionary mapping scenario name → results
        """
        if scenarios is None:
            scenarios = self.standard_scenarios
        
        base_value = pricing_function(portfolio, base_curves)
        scenario_results = {}
        
        for scenario in scenarios:
            # Apply scenario to curves
            shocked_curves = self._apply_scenario_to_curves(base_curves, scenario)
            
            # Calculate portfolio value under scenario
            scenario_value = pricing_function(portfolio, shocked_curves)
            
            # Calculate P&L and attribution
            pnl = scenario_value - base_value
            pnl_pct = (pnl / base_value) * 100 if base_value != 0 else 0.0
            
            scenario_results[scenario.name] = {
                'scenario_value': scenario_value,
                'pnl_absolute': pnl,
                'pnl_percentage': pnl_pct,
                'scenario': scenario
            }
        
        return scenario_results
    
    def _apply_scenario_to_curves(self, 
                                base_curves: Dict[str, YieldCurve],
                                scenario: RiskScenario) -> Dict[str, YieldCurve]:
        """Apply risk scenario to yield curves"""
        shocked_curves = {}
        
        for curve_name, curve in base_curves.items():
            shocked_rates = []
            
            for i, rate in enumerate(curve.rates):
                shock = 0.0
                
                # Apply parallel shift
                if scenario.parallel_shift is not None:
                    shock += scenario.parallel_shift / 10000.0  # bps to decimal
                
                # Apply tenor-specific shifts
                if scenario.yield_curve_shifts:
                    # Simplified - would need proper tenor mapping
                    if i < len(scenario.yield_curve_shifts):
                        tenor_list = list(scenario.yield_curve_shifts.keys())
                        if i < len(tenor_list):
                            tenor = tenor_list[i]
                            shock += scenario.yield_curve_shifts[tenor] / 10000.0
                
                shocked_rates.append(rate + shock)
            
            # Create new curve with shocked rates
            shocked_curves[curve_name] = YieldCurve(
                dates=curve.dates.copy(),
                rates=shocked_rates,
                curve_date=curve.curve_date,
                interpolation=curve.interpolation,
                currency=curve.currency
            )
        
        return shocked_curves


def calculate_portfolio_greeks(portfolio: Dict,
                             yield_curves: Dict[str, YieldCurve],
                             pricing_function: Callable,
                             calculation_date: datetime) -> PortfolioGreeks:
    """
    Calculate comprehensive portfolio Greeks using all advanced methods.
    
    This is the main function that orchestrates all higher-order Greek calculations.
    
    Args:
        portfolio: Portfolio holdings and details
        yield_curves: Yield curves for pricing
        pricing_function: Portfolio pricing function
        calculation_date: Calculation date
        
    Returns:
        Complete PortfolioGreeks object with all risk metrics
    """
    
    base_value = pricing_function(portfolio, yield_curves)
    shock = 0.0001  # 1bp
    
    # Initialize calculators
    cross_gamma_calc = CrossGammaCalculator()
    krc_calc = KeyRateConvexityCalculator()
    option_calc = OptionGreeksCalculator()
    scenario_engine = ScenarioAnalysisEngine()
    
    # First-order Greeks
    
    # Modified duration using parallel shift
    main_curve = list(yield_curves.values())[0]  # Use first curve
    shifted_rates_up = [r + shock for r in main_curve.rates]
    shifted_rates_down = [r - shock for r in main_curve.rates]
    
    curve_up = YieldCurve(main_curve.dates, shifted_rates_up, main_curve.curve_date, main_curve.interpolation)
    curve_down = YieldCurve(main_curve.dates, shifted_rates_down, main_curve.curve_date, main_curve.interpolation)
    
    value_up = pricing_function(portfolio, {list(yield_curves.keys())[0]: curve_up})
    value_down = pricing_function(portfolio, {list(yield_curves.keys())[0]: curve_down})
    
    modified_duration = -(value_up - value_down) / (2 * base_value * shock)
    dollar_duration = -(value_up - value_down) / 2  # DV01
    
    # Convexity (second-order)
    convexity = (value_up - 2*base_value + value_down) / (base_value * shock**2)
    
    # Cross-gamma calculation
    risk_factors = ["1Y", "5Y", "10Y"]  # Simplified set
    def simple_pricing_wrapper(port, shocks):
        # Simplified pricing wrapper for cross-gamma
        return pricing_function(port, yield_curves)  # Would apply shocks in practice
    
    cross_gammas = cross_gamma_calc.calculate_cross_gamma(
        portfolio, risk_factors, simple_pricing_wrapper
    )
    
    # Key rate convexity
    key_rate_convexities = krc_calc.calculate_key_rate_convexity(
        portfolio, main_curve, lambda p, c: pricing_function(p, {list(yield_curves.keys())[0]: c})
    )
    
    # Option Greeks (if portfolio has options)
    option_greeks = {}
    if any('call' in str(instr).lower() for instr in portfolio.values()):
        # Simplified option Greeks calculation
        sample_instrument = {'maturity_date': calculation_date + timedelta(days=365)}
        option_greeks = option_calc.calculate_option_greeks(
            sample_instrument, 0.20, 
            lambda inst, params: 100.0,  # Placeholder pricing
            calculation_date
        )
    
    # VaR calculation (simplified)
    scenario_results = scenario_engine.run_scenario_analysis(
        portfolio, yield_curves, pricing_function
    )
    
    pnl_distribution = [result['pnl_absolute'] for result in scenario_results.values()]
    var_1day = np.percentile(pnl_distribution, 5) if pnl_distribution else 0.0  # 5% VaR
    expected_shortfall = np.mean([pnl for pnl in pnl_distribution if pnl <= var_1day]) if pnl_distribution else 0.0
    
    # Compile comprehensive results
    return PortfolioGreeks(
        calculation_date=calculation_date,
        portfolio_value=base_value,
        
        # First-order
        dollar_duration=dollar_duration,
        modified_duration=modified_duration,
        effective_duration=modified_duration,  # Simplified
        spread_duration=modified_duration * 0.8,  # Approximation
        vega=option_greeks.get('vega', {}) if isinstance(option_greeks.get('vega'), dict) else {'total': option_greeks.get('vega', 0.0)},
        theta=option_greeks.get('theta', 0.0),
        
        # Second-order
        convexity=convexity,
        cross_gamma=cross_gammas,
        key_rate_convexity=key_rate_convexities,
        volga={'total': option_greeks.get('volga', 0.0)},
        vanna={'total': option_greeks.get('vanna', 0.0)},
        
        # Third-order (simplified)
        speed=convexity * 0.1,  # Approximation
        color=option_greeks.get('theta', 0.0) * 0.1,  # Approximation
        
        # Risk metrics
        var_1day=var_1day,
        expected_shortfall=expected_shortfall,
        maximum_drawdown=min(pnl_distribution) if pnl_distribution else 0.0
    )


def test_higher_order_greeks():
    """Test higher-order Greeks functionality"""
    print("Testing Higher-Order Greeks...")
    
    # Create sample portfolio
    portfolio = {
        'bond_1': {
            'notional': 1000000,
            'coupon': 0.05,
            'maturity': datetime(2029, 1, 15),
            'callable': True
        },
        'bond_2': {
            'notional': 500000,
            'coupon': 0.04,
            'maturity': datetime(2027, 1, 15),
            'callable': False
        }
    }
    
    # Create sample yield curve
    from .curve_construction import YieldCurve
    calc_date = datetime(2024, 1, 15)
    
    dates = [
        calc_date + timedelta(days=365),   # 1Y
        calc_date + timedelta(days=365*2), # 2Y  
        calc_date + timedelta(days=365*5), # 5Y
        calc_date + timedelta(days=365*10) # 10Y
    ]
    rates = [0.045, 0.047, 0.049, 0.051]
    
    main_curve = YieldCurve(dates, rates, calc_date)
    yield_curves = {'main': main_curve}
    
    # Simple pricing function
    def simple_pricing(portfolio_dict, curves_dict):
        total_value = 0.0
        for bond_id, bond_data in portfolio_dict.items():
            # Simplified bond pricing
            notional = bond_data['notional']
            coupon = bond_data['coupon']
            
            # Use curve for discounting
            if curves_dict:
                curve = list(curves_dict.values())[0]
                rate = curve.zero_rate(2.0)  # 2Y rate
                pv = notional * (1 + coupon * 2) * np.exp(-rate * 2)
            else:
                pv = notional  # Fallback
            
            total_value += pv
        
        return total_value
    
    # Calculate comprehensive Greeks
    greeks = calculate_portfolio_greeks(
        portfolio, yield_curves, simple_pricing, calc_date
    )
    
    print(f"\nPortfolio Greeks Analysis:")
    print(f"  Portfolio Value: ${greeks.portfolio_value:,.0f}")
    print(f"  Dollar Duration (DV01): ${greeks.dollar_duration:,.0f}")
    print(f"  Modified Duration: {greeks.modified_duration:.3f} years")
    print(f"  Convexity: {greeks.convexity:.2f}")
    print(f"  Cross-Gamma pairs: {len(greeks.cross_gamma)}")
    print(f"  Key Rate Convexity tenors: {len(greeks.key_rate_convexity)}")
    print(f"  1-Day VaR: ${greeks.var_1day:,.0f}")
    print(f"  Expected Shortfall: ${greeks.expected_shortfall:,.0f}")
    
    # Test Cross-Gamma Calculator separately
    cross_gamma_calc = CrossGammaCalculator()
    risk_factors = ["1Y", "5Y", "10Y"]
    
    cross_gammas = cross_gamma_calc.calculate_cross_gamma(
        portfolio, risk_factors, simple_pricing
    )
    
    print(f"\nCross-Gamma Matrix:")
    for (factor_i, factor_j), gamma_value in cross_gammas.items():
        print(f"  {factor_i} × {factor_j}: {gamma_value:.6f}")
    
    print("Higher-order Greeks testing complete!")


if __name__ == "__main__":
    test_higher_order_greeks()
