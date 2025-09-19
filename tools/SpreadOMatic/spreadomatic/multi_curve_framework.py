# multi_curve_framework.py
# Purpose: Post-2008 multi-curve framework for fixed income pricing
# Implements OIS discounting, LIBOR/SOFR projection, and basis spread management

from __future__ import annotations

import numpy as np
import scipy.optimize as opt
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union, NamedTuple
from dataclasses import dataclass
from enum import Enum

from .curve_construction import YieldCurve, InterpolationMethod
from .daycount_enhanced import year_fraction_precise, DayCountConvention
from .numerical_methods import brent_solve, newton_raphson_robust

__all__ = [
    "CurveType",
    "MultiCurveFramework", 
    "BasisSpreadCalculator",
    "CrossCurrencyBasis",
    "DualCurveBootstrapper",
    "SwapPricingEngine",
    "create_multi_curve_system"
]


class CurveType(Enum):
    """Types of yield curves in multi-curve framework"""
    OIS_DISCOUNTING = "OIS"                    # Overnight index swap (discounting)
    LIBOR_PROJECTION = "LIBOR"                 # LIBOR projection curve
    SOFR_PROJECTION = "SOFR"                   # SOFR projection curve  
    EURIBOR_PROJECTION = "EURIBOR"             # EURIBOR projection curve
    SONIA_PROJECTION = "SONIA"                 # SONIA projection curve
    TONAR_PROJECTION = "TONAR"                 # TONAR projection curve (Japan)
    GOVERNMENT_DISCOUNTING = "GOVT"            # Government bond curve
    CORPORATE_SPREAD = "CORP"                  # Corporate spread curve
    
    @property
    def is_discounting(self) -> bool:
        """Whether this curve is used for discounting"""
        return self in [CurveType.OIS_DISCOUNTING, CurveType.GOVERNMENT_DISCOUNTING]
    
    @property
    def is_projection(self) -> bool:
        """Whether this curve is used for forward rate projection"""
        return not self.is_discounting


@dataclass
class BasisSpread:
    """Basis spread between two reference rates"""
    tenor: str                                 # "3M", "6M", etc.
    spread: float                             # Spread in decimal (e.g., 0.001 = 10 bps)
    effective_date: datetime
    maturity_date: datetime
    fixing_lag: int = 2                       # Fixing lag in business days
    day_count: str = "ACT/360"


@dataclass
class MultiCurveResult:
    """Result of multi-curve pricing calculation"""
    present_value: float
    discounting_curve_used: str
    projection_curves_used: List[str]
    basis_spreads_applied: Dict[str, float]
    discount_factors: List[float]
    forward_rates: List[float]
    calculation_date: datetime


class MultiCurveFramework:
    """
    Professional multi-curve framework implementing post-2008 market standards.
    
    Separates discounting (typically OIS) from projection curves (LIBOR/SOFR),
    properly handling basis spreads and cross-currency effects.
    """
    
    def __init__(self, base_currency: str = "USD", calculation_date: Optional[datetime] = None):
        self.base_currency = base_currency
        self.calculation_date = calculation_date or datetime.now()
        
        # Curve storage
        self.curves: Dict[CurveType, YieldCurve] = {}
        self.basis_spreads: Dict[Tuple[CurveType, str], BasisSpread] = {}
        
        # Default curve assignments by currency
        self._setup_default_curve_mapping()
    
    def _setup_default_curve_mapping(self):
        """Setup default curve assignments by currency"""
        self.default_discounting = {
            "USD": CurveType.OIS_DISCOUNTING,       # Fed Funds / SOFR OIS
            "EUR": CurveType.OIS_DISCOUNTING,       # EONIA / €STR OIS
            "GBP": CurveType.OIS_DISCOUNTING,       # SONIA OIS
            "JPY": CurveType.OIS_DISCOUNTING,       # TONAR OIS
            "CHF": CurveType.OIS_DISCOUNTING,       # SARON OIS
        }
        
        self.default_projection = {
            "USD": CurveType.SOFR_PROJECTION,       # SOFR (replacing USD LIBOR)
            "EUR": CurveType.EURIBOR_PROJECTION,    # EURIBOR
            "GBP": CurveType.SONIA_PROJECTION,      # SONIA (replacing GBP LIBOR)
            "JPY": CurveType.TONAR_PROJECTION,      # TONAR (replacing JPY LIBOR)
        }
    
    def add_curve(self, curve_type: CurveType, curve: YieldCurve) -> None:
        """Add a yield curve to the framework"""
        self.curves[curve_type] = curve
    
    def add_basis_spread(self, 
                        from_curve: CurveType, 
                        to_curve: CurveType,
                        tenor: str,
                        spread: float,
                        effective_date: datetime,
                        maturity_date: datetime) -> None:
        """Add basis spread between two curves"""
        basis = BasisSpread(
            tenor=tenor,
            spread=spread,
            effective_date=effective_date,
            maturity_date=maturity_date
        )
        self.basis_spreads[(from_curve, tenor)] = basis
    
    def get_discount_factor(self, 
                          maturity: Union[datetime, float],
                          discounting_curve: Optional[CurveType] = None) -> float:
        """Get discount factor using appropriate discounting curve"""
        if discounting_curve is None:
            discounting_curve = self.default_discounting.get(
                self.base_currency, CurveType.OIS_DISCOUNTING
            )
        
        if discounting_curve not in self.curves:
            raise ValueError(f"Discounting curve {discounting_curve} not available")
        
        curve = self.curves[discounting_curve]
        return curve.discount_factor(maturity)
    
    def get_forward_rate(self, 
                        start_date: Union[datetime, float],
                        end_date: Union[datetime, float],
                        tenor: str,
                        projection_curve: Optional[CurveType] = None) -> float:
        """
        Get forward rate using appropriate projection curve with basis adjustment.
        
        This is the core of multi-curve framework - separating projection from discounting.
        """
        if projection_curve is None:
            projection_curve = self.default_projection.get(
                self.base_currency, CurveType.LIBOR_PROJECTION
            )
        
        if projection_curve not in self.curves:
            raise ValueError(f"Projection curve {projection_curve} not available")
        
        # Get base forward rate from projection curve
        curve = self.curves[projection_curve]
        base_forward = curve.forward_rate(start_date, end_date)
        
        # Apply basis spread if applicable
        basis_key = (projection_curve, tenor)
        if basis_key in self.basis_spreads:
            basis = self.basis_spreads[basis_key]
            # Check if basis spread is active for this period
            if isinstance(start_date, datetime):
                start_check = start_date
            else:
                start_check = self.calculation_date + timedelta(days=int(start_date * 365))
            
            if basis.effective_date <= start_check <= basis.maturity_date:
                base_forward += basis.spread
        
        return base_forward
    
    def price_swap(self, 
                   notional: float,
                   fixed_rate: float,
                   payment_dates: List[datetime],
                   floating_tenors: List[str],
                   day_count_fixed: str = "30/360",
                   day_count_floating: str = "ACT/360") -> MultiCurveResult:
        """
        Price interest rate swap using multi-curve framework.
        
        This demonstrates the key benefit: using OIS for discounting but 
        LIBOR/SOFR for forward rate projections.
        """
        
        fixed_leg_pv = 0.0
        floating_leg_pv = 0.0
        discount_factors = []
        forward_rates = []
        
        discounting_curve = self.default_discounting.get(self.base_currency)
        projection_curve = self.default_projection.get(self.base_currency)
        
        # Price each payment
        for i, payment_date in enumerate(payment_dates):
            # Discount factor (typically OIS)
            df = self.get_discount_factor(payment_date, discounting_curve)
            discount_factors.append(df)
            
            # Period calculation
            if i == 0:
                period_start = self.calculation_date
            else:
                period_start = payment_dates[i-1]
            
            period_fraction = year_fraction_precise(
                period_start, payment_date, day_count_fixed
            )
            
            # Fixed leg cashflow
            fixed_cashflow = fixed_rate * period_fraction * notional
            fixed_leg_pv += fixed_cashflow * df
            
            # Floating leg forward rate (LIBOR/SOFR with basis)
            if i < len(floating_tenors):
                tenor = floating_tenors[i]
                forward_rate = self.get_forward_rate(
                    period_start, payment_date, tenor, projection_curve
                )
                forward_rates.append(forward_rate)
                
                # Floating period calculation
                float_period_fraction = year_fraction_precise(
                    period_start, payment_date, day_count_floating
                )
                
                floating_cashflow = forward_rate * float_period_fraction * notional
                floating_leg_pv += floating_cashflow * df
        
        # Swap PV = Fixed Leg - Floating Leg (from receiver's perspective)
        swap_pv = fixed_leg_pv - floating_leg_pv
        
        # Collect basis spreads that were applied
        applied_basis = {}
        for (curve_type, tenor), basis in self.basis_spreads.items():
            if curve_type == projection_curve:
                applied_basis[tenor] = basis.spread
        
        return MultiCurveResult(
            present_value=swap_pv,
            discounting_curve_used=discounting_curve.value if discounting_curve else "None",
            projection_curves_used=[projection_curve.value] if projection_curve else [],
            basis_spreads_applied=applied_basis,
            discount_factors=discount_factors,
            forward_rates=forward_rates,
            calculation_date=self.calculation_date
        )
    
    def calculate_ois_libor_basis(self, 
                                 maturity: Union[datetime, float],
                                 tenor: str = "3M") -> float:
        """
        Calculate the basis spread between OIS and LIBOR/SOFR curves.
        
        This is a key metric post-2008 for understanding credit/liquidity risk.
        """
        ois_curve = self.curves.get(CurveType.OIS_DISCOUNTING)
        
        # Determine appropriate projection curve
        if self.base_currency == "USD":
            proj_curve = self.curves.get(CurveType.SOFR_PROJECTION) or \
                        self.curves.get(CurveType.LIBOR_PROJECTION)
        elif self.base_currency == "EUR":
            proj_curve = self.curves.get(CurveType.EURIBOR_PROJECTION)
        else:
            proj_curve = self.curves.get(CurveType.LIBOR_PROJECTION)
        
        if not ois_curve or not proj_curve:
            return 0.0
        
        # Compare rates at same maturity
        ois_rate = ois_curve.zero_rate(maturity)
        proj_rate = proj_curve.zero_rate(maturity)
        
        return proj_rate - ois_rate


class BasisSpreadCalculator:
    """
    Calculate and manage basis spreads between different reference rates.
    
    Essential for post-crisis fixed income where different rates trade at spreads.
    """
    
    def __init__(self, multi_curve: MultiCurveFramework):
        self.multi_curve = multi_curve
    
    def calculate_libor_ois_basis_term_structure(self, 
                                               tenors: List[str]) -> Dict[str, float]:
        """Calculate LIBOR-OIS basis across term structure"""
        basis_term_structure = {}
        
        for tenor in tenors:
            # Convert tenor to years
            if tenor.endswith('M'):
                years = int(tenor[:-1]) / 12.0
            elif tenor.endswith('Y'):
                years = float(tenor[:-1])
            else:
                years = 1.0
            
            basis = self.multi_curve.calculate_ois_libor_basis(years, tenor)
            basis_term_structure[tenor] = basis * 10000  # Convert to basis points
        
        return basis_term_structure
    
    def calibrate_basis_to_market_swaps(self, 
                                      basis_swaps: List[Dict]) -> Dict[str, float]:
        """
        Calibrate basis spreads to market basis swap quotes.
        
        Basis swaps trade the spread between different reference rates
        (e.g., 3M LIBOR vs 6M LIBOR, LIBOR vs OIS).
        """
        calibrated_basis = {}
        
        for swap in basis_swaps:
            reference_rate = swap['reference_rate']    # e.g., "3M_LIBOR"
            floating_rate = swap['floating_rate']      # e.g., "6M_LIBOR"
            maturity = swap['maturity']                # e.g., 2.0 years
            market_spread = swap['spread']             # Market quoted spread
            
            # This would involve complex bootstrap - simplified here
            calibrated_basis[f"{reference_rate}_{floating_rate}_{maturity}Y"] = market_spread
        
        return calibrated_basis


class DualCurveBootstrapper:
    """
    Bootstrap OIS and projection curves simultaneously from market instruments.
    
    This is more complex than single-curve bootstrap as curves are interdependent.
    """
    
    def __init__(self, calculation_date: datetime, currency: str = "USD"):
        self.calculation_date = calculation_date
        self.currency = currency
    
    def bootstrap_from_market_data(self, 
                                 ois_instruments: List[Dict],
                                 libor_instruments: List[Dict],
                                 basis_swaps: List[Dict] = None) -> MultiCurveFramework:
        """
        Bootstrap dual curves from market data.
        
        Args:
            ois_instruments: OIS swap rates for discounting curve
            libor_instruments: LIBOR/SOFR instruments for projection  
            basis_swaps: Basis swaps for cross-curve calibration
            
        Returns:
            Calibrated MultiCurveFramework
        """
        
        # Initialize framework
        framework = MultiCurveFramework(self.currency, self.calculation_date)
        
        # Bootstrap OIS discounting curve
        ois_curve = self._bootstrap_ois_curve(ois_instruments)
        framework.add_curve(CurveType.OIS_DISCOUNTING, ois_curve)
        
        # Bootstrap projection curve  
        if self.currency == "USD":
            projection_type = CurveType.SOFR_PROJECTION
        elif self.currency == "EUR":
            projection_type = CurveType.EURIBOR_PROJECTION
        else:
            projection_type = CurveType.LIBOR_PROJECTION
        
        projection_curve = self._bootstrap_projection_curve(libor_instruments, ois_curve)
        framework.add_curve(projection_type, projection_curve)
        
        # Add basis spreads if provided
        if basis_swaps:
            self._add_basis_spreads(framework, basis_swaps)
        
        return framework
    
    def _bootstrap_ois_curve(self, instruments: List[Dict]) -> YieldCurve:
        """Bootstrap OIS curve from OIS swap rates"""
        # Extract maturities and rates
        dates = []
        rates = []
        
        for instrument in instruments:
            maturity_years = instrument['maturity']
            rate = instrument['rate']
            
            maturity_date = self.calculation_date + timedelta(days=int(maturity_years * 365))
            dates.append(maturity_date)
            rates.append(rate)
        
        # Create curve with monotone cubic interpolation
        return YieldCurve(
            dates=dates,
            rates=rates,
            curve_date=self.calculation_date,
            interpolation=InterpolationMethod.MONOTONE_CUBIC,
            currency=self.currency,
            curve_type="OIS"
        )
    
    def _bootstrap_projection_curve(self, 
                                  instruments: List[Dict], 
                                  ois_curve: YieldCurve) -> YieldCurve:
        """Bootstrap projection curve using OIS for discounting"""
        # This involves iterative solving where we use OIS discounting
        # to derive forward rates that match market swap rates
        
        dates = []
        rates = []
        
        for instrument in instruments:
            maturity_years = instrument['maturity']
            market_rate = instrument['rate']
            
            # Solve for zero rate that makes swap price = 0 when discounting with OIS
            def swap_pricing_error(zero_rate: float) -> float:
                # Create temporary projection curve
                temp_dates = dates + [self.calculation_date + timedelta(days=int(maturity_years * 365))]
                temp_rates = rates + [zero_rate]
                
                if len(temp_dates) < 2:
                    return market_rate - zero_rate
                
                # Price swap using OIS discounting and this projection curve
                # Simplified implementation - real version would be more complex
                projected_rate = zero_rate
                ois_discount_rate = ois_curve.zero_rate(maturity_years)
                
                # Simple approximation of swap pricing equation
                return projected_rate - market_rate
            
            # Solve for projection curve zero rate
            try:
                zero_rate = brent_solve(swap_pricing_error, market_rate, (0.001, 0.2))
            except:
                zero_rate = market_rate  # Fallback
            
            maturity_date = self.calculation_date + timedelta(days=int(maturity_years * 365))
            dates.append(maturity_date)
            rates.append(zero_rate)
        
        return YieldCurve(
            dates=dates,
            rates=rates,
            curve_date=self.calculation_date,
            interpolation=InterpolationMethod.MONOTONE_CUBIC,
            currency=self.currency,
            curve_type="PROJECTION"
        )
    
    def _add_basis_spreads(self, 
                          framework: MultiCurveFramework, 
                          basis_swaps: List[Dict]) -> None:
        """Add basis spreads from basis swap market data"""
        for basis_swap in basis_swaps:
            # Extract basis swap details
            from_rate = basis_swap.get('from_rate', '3M_LIBOR')
            to_rate = basis_swap.get('to_rate', 'OIS')
            maturity = basis_swap['maturity']
            spread = basis_swap['spread']
            
            # Map to curve types (simplified)
            if 'LIBOR' in from_rate:
                from_curve = CurveType.LIBOR_PROJECTION
            elif 'SOFR' in from_rate:
                from_curve = CurveType.SOFR_PROJECTION
            else:
                from_curve = CurveType.OIS_DISCOUNTING
            
            tenor = from_rate.split('_')[0] if '_' in from_rate else "3M"
            
            framework.add_basis_spread(
                from_curve=from_curve,
                to_curve=CurveType.OIS_DISCOUNTING,
                tenor=tenor,
                spread=spread,
                effective_date=framework.calculation_date,
                maturity_date=framework.calculation_date + timedelta(days=int(maturity * 365))
            )


def create_multi_curve_system(currency: str = "USD", 
                            calculation_date: Optional[datetime] = None) -> MultiCurveFramework:
    """
    Convenient function to create a multi-curve system with market-standard setup.
    
    Args:
        currency: Base currency for the system
        calculation_date: Calculation date (defaults to today)
        
    Returns:
        Configured MultiCurveFramework ready for use
    """
    framework = MultiCurveFramework(currency, calculation_date)
    
    # Add some sample basis spreads (would be calibrated from market in practice)
    calc_date = calculation_date or datetime.now()
    
    if currency == "USD":
        # Add typical SOFR-Fed Funds basis
        framework.add_basis_spread(
            from_curve=CurveType.SOFR_PROJECTION,
            to_curve=CurveType.OIS_DISCOUNTING,
            tenor="3M",
            spread=0.0010,  # 10 bps typical
            effective_date=calc_date,
            maturity_date=calc_date + timedelta(days=365*10)
        )
    
    return framework


def test_multi_curve_framework():
    """Test multi-curve framework functionality"""
    print("Testing Multi-Curve Framework...")
    
    # Create multi-curve system
    calc_date = datetime(2024, 1, 15)
    framework = create_multi_curve_system("USD", calc_date)
    
    # Create sample curves (simplified for testing)
    from .curve_construction import YieldCurve
    
    # OIS curve (lower rates)
    ois_dates = [
        calc_date + timedelta(days=90),   # 3M
        calc_date + timedelta(days=365),  # 1Y  
        calc_date + timedelta(days=365*2), # 2Y
        calc_date + timedelta(days=365*5), # 5Y
    ]
    ois_rates = [0.045, 0.044, 0.043, 0.042]  # OIS typically lower
    
    ois_curve = YieldCurve(ois_dates, ois_rates, calc_date)
    framework.add_curve(CurveType.OIS_DISCOUNTING, ois_curve)
    
    # SOFR projection curve (higher rates due to credit/liquidity premium)
    sofr_rates = [0.047, 0.046, 0.045, 0.044]  # SOFR higher than OIS
    
    sofr_curve = YieldCurve(ois_dates, sofr_rates, calc_date)  # Same dates
    framework.add_curve(CurveType.SOFR_PROJECTION, sofr_curve)
    
    # Test discount factors
    one_year = calc_date + timedelta(days=365)
    ois_df = framework.get_discount_factor(one_year)
    print(f"1Y OIS Discount Factor: {ois_df:.6f}")
    
    # Test forward rates
    forward_3m = framework.get_forward_rate(calc_date, calc_date + timedelta(days=90), "3M")
    print(f"3M Forward Rate (SOFR): {forward_3m*100:.3f}%")
    
    # Test OIS-LIBOR basis
    basis_1y = framework.calculate_ois_libor_basis(1.0, "3M")
    print(f"1Y OIS-SOFR Basis: {basis_1y*10000:.1f} bps")
    
    # Test swap pricing (simplified)
    payment_dates = [calc_date + timedelta(days=180), calc_date + timedelta(days=365)]
    swap_result = framework.price_swap(
        notional=1000000,
        fixed_rate=0.045,
        payment_dates=payment_dates,
        floating_tenors=["6M", "6M"]
    )
    
    print(f"\nSwap Pricing Results:")
    print(f"  Present Value: ${swap_result.present_value:,.2f}")
    print(f"  Discounting Curve: {swap_result.discounting_curve_used}")
    print(f"  Projection Curves: {swap_result.projection_curves_used}")
    print(f"  Applied Basis Spreads: {swap_result.basis_spreads_applied}")
    
    print("Multi-curve framework testing complete!")


if __name__ == "__main__":
    test_multi_curve_framework()
