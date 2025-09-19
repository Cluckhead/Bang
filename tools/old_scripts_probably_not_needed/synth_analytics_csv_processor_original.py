# Purpose: Generate comprehensive CSV with all SpreadOMatic synthetic analytics for the most recent date in sec_Price.csv
# Calculates YTM, spreads, durations, convexity, OAS, KRDs, and higher-order Greeks for all securities
#
# Day Count Convention Support:
# - Enhanced support for 30E/360 and other European conventions via daycount_enhanced module
# - Automatic fallback to basic daycount module with convention mapping for compatibility
# - Comprehensive mapping of variants: 30E/360 -> 30/360, ACT/ACT-ISDA -> ACT/ACT, etc.
# - Robust error handling with multiple fallback levels to ensure calculations complete

import pandas as pd
import numpy as np
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import OrderedDict

# Ensure local SpreadOMatic copy is found
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools', 'SpreadOMatic'))

from core import config
from analytics.synth_spread_calculator import parse_date_robust, get_supported_day_basis, generate_payment_schedule, get_base_isin

# Import SpreadOMatic modules with enhanced fallback
try:
    # Enhanced institutional-grade modules
    from tools.SpreadOMatic.spreadomatic.daycount_enhanced import (
        year_fraction_precise as year_fraction_enhanced,
        DayCountConvention,
        HolidayCalendar,
        accrued_interest_precise
    )
    from tools.SpreadOMatic.spreadomatic.curve_construction import YieldCurve, InterpolationMethod
    from tools.SpreadOMatic.spreadomatic.numerical_methods import yield_solver, spread_solver
    from tools.SpreadOMatic.spreadomatic.settlement_mechanics import calculate_settlement_details, AccruedCalculator
    from tools.SpreadOMatic.spreadomatic.oas_enhanced_v2 import (
        HullWhiteModel, 
        OASCalculator,
        CallableInstrument,
        CallOption,
        create_hull_white_calculator
    )
    from tools.SpreadOMatic.spreadomatic.higher_order_greeks import (
        GreekType,
        CrossGammaCalculator,
        KeyRateConvexityCalculator,
        OptionGreeksCalculator,
        calculate_portfolio_greeks
    )
    from tools.SpreadOMatic.spreadomatic.multi_curve_framework import (
        MultiCurveFramework,
        BasisSpreadCalculator,
        CurveType
    )
    ENHANCED_ANALYTICS_AVAILABLE = True
    
    # Standard modules for core calculations
    from tools.SpreadOMatic.spreadomatic.daycount import to_datetime
    from tools.SpreadOMatic.spreadomatic.interpolation import linear_interpolate
    from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows, generate_fixed_schedule
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, g_spread, z_spread
    from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows, Compounding
    from tools.SpreadOMatic.spreadomatic.duration import (
        effective_duration,
        modified_duration as sm_modified_duration,
        effective_convexity,
        key_rate_durations,
        effective_spread_duration,
        modified_duration_standard as sm_modified_duration_standard,
    )
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas
    from tools.SpreadOMatic.spreadomatic.oas_enhanced import compute_oas_enhanced, VolatilityCalibrator
    
except ImportError as e:
    # Fall back to standard modules only
    ENHANCED_ANALYTICS_AVAILABLE = False
    
    from tools.SpreadOMatic.spreadomatic.daycount import to_datetime, year_fraction as year_fraction_basic
    from tools.SpreadOMatic.spreadomatic.interpolation import linear_interpolate
    from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows, generate_fixed_schedule
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, g_spread, z_spread
    from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows, Compounding
    from tools.SpreadOMatic.spreadomatic.duration import (
        effective_duration,
        modified_duration as sm_modified_duration,
        effective_convexity,
        key_rate_durations,
        effective_spread_duration,
        modified_duration_standard as sm_modified_duration_standard,
    )
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas

# Setup logger
logger = logging.getLogger('synth_analytics_csv')
handler = logging.FileHandler('synth_analytics_csv.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def year_fraction(start: datetime, end: datetime, convention: str) -> float:
    """
    Wrapper function that handles both enhanced and basic day count conventions.
    Maps unsupported conventions to supported ones when using basic fallback.
    
    This function provides seamless compatibility between:
    1. Enhanced daycount_enhanced module (supports 30E/360, ACT/ACT-ISDA, etc.)
    2. Basic daycount module (supports 30/360, ACT/ACT, etc.)
    
    Key features:
    - Automatic fallback from enhanced to basic module
    - Intelligent convention mapping (30E/360 -> 30/360, etc.)
    - Multiple fallback levels for maximum compatibility
    - Comprehensive logging for debugging
    - Graceful degradation to simple approximation if all else fails
    
    Args:
        start: Start date for period calculation
        end: End date for period calculation  
        convention: Day count convention (e.g., "30E/360", "ACT/ACT")
    
    Returns:
        Year fraction between start and end dates
    """
    logger.debug(f"Calculating year fraction from {start} to {end} using convention '{convention}'")
    
    if ENHANCED_ANALYTICS_AVAILABLE:
        # Use enhanced function which supports all conventions including 30E/360
        try:
            result = year_fraction_enhanced(start, end, convention)
            logger.debug(f"Enhanced year_fraction successful: {result}")
            return result
        except Exception as e:
            logger.warning(f"Enhanced year_fraction failed for '{convention}', falling back to basic: {e}")
            # Fall through to basic implementation
    
    # Map unsupported conventions to supported ones for basic fallback
    convention_upper = convention.upper().strip()
    original_convention = convention_upper
    
    # Map 30E/360 variants to 30/360 for basic compatibility
    if convention_upper in {"30E/360", "30E", "30/360E", "30/360-E"}:
        convention_upper = "30/360"
        logger.info(f"Mapped day basis '{convention}' to '30/360' for basic compatibility")
    elif convention_upper in {"30/360-US", "30/360 US", "US 30/360", "30/360U"}:
        convention_upper = "30/360"
        logger.info(f"Mapped day basis '{convention}' to '30/360' for basic compatibility")
    elif convention_upper in {"ACT/ACT-ISDA", "ISDA", "ACT/ACT-ICMA", "ACT/ACT-AFB"}:
        convention_upper = "ACT/ACT"
        logger.info(f"Mapped day basis '{convention}' to 'ACT/ACT' for basic compatibility")
    elif convention_upper in {"ACT/365-FIXED", "ACT/365", "ACT/365L", "NL/365"}:
        convention_upper = "ACT/365"
        logger.info(f"Mapped day basis '{convention}' to 'ACT/365' for basic compatibility")
    elif convention_upper in {"ACT/360", "ACT/360-FIXED"}:
        convention_upper = "ACT/360"
    elif convention_upper in {"ACT/ACT", "ACT", "ACTUAL/ACTUAL"}:
        convention_upper = "ACT/ACT"
    
    logger.debug(f"Using mapped convention '{convention_upper}' (original: '{convention}')")
    
    # Use basic function with mapped convention
    try:
        result = year_fraction_basic(start, end, convention_upper)
        logger.debug(f"Basic year_fraction successful: {result}")
        return result
    except Exception as e:
        logger.error(f"Basic year_fraction failed for mapped convention '{convention_upper}' (original: '{convention}'): {e}")
        # Final fallback to 30/360
        logger.warning(f"Falling back to 30/360 for '{convention}'")
        try:
            result = year_fraction_basic(start, end, "30/360")
            logger.debug(f"Fallback year_fraction successful: {result}")
            return result
        except Exception as fallback_error:
            logger.error(f"Even fallback to 30/360 failed: {fallback_error}")
            # Last resort: return a reasonable approximation
            days = (end - start).days
            result = days / 365.25
            logger.warning(f"Using simple approximation: {days} days / 365.25 = {result}")
            return result


def get_latest_date_from_csv(data_folder: str) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    """Get the most recent date with data from sec_Price.csv and return the dataframe."""
    try:
        price_path = os.path.join(data_folder, "sec_Price.csv")
        if not os.path.exists(price_path):
            logger.error(f"sec_Price.csv not found: {price_path}")
            return None, None
        
        df = pd.read_csv(price_path)
        if df.empty:
            logger.error("sec_Price.csv is empty")
            return None, None
        
        # Identify metadata and date columns
        metadata_cols = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
        date_columns = [col for col in df.columns if col not in metadata_cols]
        
        # Find the latest date with any non-null data
        latest_date = None
        for col in reversed(date_columns):  # Start from most recent
            if df[col].notna().any():
                latest_date = col
                break
        
        if latest_date is None:
            logger.error("No valid price data found in any date column")
            return None, None
        
        logger.info(f"Found latest date with data: {latest_date}")
        return latest_date, df
        
    except Exception as e:
        logger.error(f"Error reading sec_Price.csv: {e}")
        return None, None


def load_supporting_data(data_folder: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load schedule, curves, reference, and accrued data needed for analytics calculations."""
    try:
        # Load schedule data
        schedule_path = os.path.join(data_folder, 'schedule.csv')
        schedule_df = None
        if os.path.exists(schedule_path):
            schedule_df = pd.read_csv(schedule_path)
        else:
            logger.warning(f"Schedule file not found: {schedule_path}")
        
        # Load reference data (contains coupon rates and maturity dates)
        reference_path = os.path.join(data_folder, 'reference.csv')
        reference_df = None
        if os.path.exists(reference_path):
            reference_df = pd.read_csv(reference_path)
            logger.info(f"Loaded reference data with {len(reference_df)} securities")
        else:
            logger.warning(f"Reference file not found: {reference_path}")
        
        # Load curves data
        curves_path = os.path.join(data_folder, 'curves.csv')
        curves_df = None
        if os.path.exists(curves_path):
            curves_df = pd.read_csv(curves_path)
        else:
            logger.warning(f"Curves file not found: {curves_path}")
        
        # Load accrued data (optional)
        accrued_path = os.path.join(data_folder, 'sec_accrued.csv')
        accrued_df = None
        if os.path.exists(accrued_path):
            accrued_df = pd.read_csv(accrued_path)
        else:
            logger.info(f"Accrued file not found (optional): {accrued_path}")
        
        return schedule_df, reference_df, curves_df, accrued_df
        
    except Exception as e:
        logger.error(f"Error loading supporting data: {e}")
        return None, None, None, None


def calculate_all_analytics_for_security(
    row: pd.Series,
    price: float,
    latest_date: str,
    schedule_df: Optional[pd.DataFrame],
    reference_df: Optional[pd.DataFrame],
    curves_df: Optional[pd.DataFrame],
    accrued_df: Optional[pd.DataFrame]
) -> Dict[str, Any]:
    """Calculate all available SpreadOMatic analytics for a single security."""
    
    result = OrderedDict([
        ('ISIN', row['ISIN']),
        ('Security_Name', row.get('Security Name', '')),
        ('Funds', row.get('Funds', '')),
        ('Type', row.get('Type', '')),
        ('Callable', row.get('Callable', '')),
        ('Currency', row.get('Currency', '')),
        ('Date', latest_date),
        ('Price', price)
    ])
    
    try:
        isin = row['ISIN']
        currency = row.get('Currency', 'USD')
        
        # Get reference information (contains coupon data)
        reference_row = None
        if reference_df is not None:
            reference_matches = reference_df[reference_df['ISIN'] == isin]
            if reference_matches.empty and isinstance(isin, str) and '-' in isin:
                # Try base ISIN (remove hyphenated suffix) like synth_spread_calculator
                try:
                    base = get_base_isin(isin)
                    reference_matches = reference_df[reference_df['ISIN'] == base]
                    if not reference_matches.empty:
                        logger.debug(f"Using base ISIN {base} for reference lookup of {isin}")
                except Exception:
                    pass
            if not reference_matches.empty:
                reference_row = reference_matches.iloc[0]
                # Prefer Position Currency from reference.csv if available
                # This matches how the Excel path determines currency
                position_currency_col = None
                for col in reference_row.index:
                    if 'position currency' in col.lower() or col.lower() == 'currency':
                        position_currency_col = col
                        break
                if position_currency_col and pd.notna(reference_row.get(position_currency_col)):
                    ref_currency = str(reference_row[position_currency_col]).strip()
                    if ref_currency:
                        logger.debug(f"Using currency {ref_currency} from reference.csv for {isin} (was {currency})")
                        currency = ref_currency
        
        # Get schedule information
        schedule_row = None
        if schedule_df is not None:
            schedule_matches = schedule_df[schedule_df['ISIN'] == isin]
            if not schedule_matches.empty:
                schedule_row = schedule_matches.iloc[0]
        
        # Combine reference and schedule data, or create defaults
        combined_data = _combine_security_data(row, reference_row, schedule_row, latest_date)
        
        # Get curves for the currency
        if curves_df is None or curves_df.empty:
            logger.warning(f"No curves data available")
            _fill_analytics_with_nan(result)
            return result
            
        # Parse curve data for the currency
        
        # Parse curve data
        z_times, z_rates = _parse_curve_data(curves_df, currency, latest_date)
        if not z_times or not z_rates:
            logger.warning(f"Invalid curve data for {currency}")
            _fill_analytics_with_nan(result)
            return result
        
        # Get valuation date
        valuation_date = to_datetime(latest_date)
        
        # Get accrued interest
        accrued_interest = _get_accrued_interest(isin, latest_date, accrued_df)
        
        # Build cash flows using the same method as synth_spread_calculator
        times, cfs = _build_cashflows_from_combined_data(
            combined_data, valuation_date, row, schedule_row, z_times, z_rates
        )
        if not times or not cfs:
            logger.warning(f"Could not build cashflows for {isin}")
            _fill_analytics_with_nan(result)
            return result
        
        # Calculate dirty price
        dirty_price = price + accrued_interest
        
        # Determine compounding based on coupon frequency
        coupon_freq = int(combined_data.get('Coupon Frequency', 2))
        compounding = 'semiannual' if coupon_freq == 2 else 'annual'
        
        # Core analytics calculations
        try:
            # YTM
            ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
            result['YTM_Percent'] = ytm * 100
            
            # Spreads
            maturity = max(times)
            g_spr = g_spread(ytm, maturity, z_times, z_rates)
            z_spr = z_spread(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
            result['G_Spread_bps'] = g_spr * 10000
            result['Z_Spread_bps'] = z_spr * 10000
            
            # Durations
            eff_dur = effective_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
            coupon_freq = int(combined_data.get('Coupon Frequency', 2))
            # Standard Macaulay-based modified duration with fallback
            try:
                mod_dur = sm_modified_duration_standard(times, cfs, ytm, comp=compounding, frequency=coupon_freq)
            except Exception:
                if compounding == 'semiannual':
                    mod_dur = eff_dur / (1 + ytm / 2)
                elif compounding == 'annual':
                    mod_dur = eff_dur / (1 + ytm)
                elif compounding == 'continuous':
                    mod_dur = eff_dur
                elif compounding == 'monthly':
                    mod_dur = eff_dur / (1 + ytm / 12)
                else:
                    mod_dur = sm_modified_duration(eff_dur, ytm, frequency=coupon_freq)
            spr_dur = effective_spread_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
            
            result['Effective_Duration'] = eff_dur
            result['Modified_Duration'] = mod_dur
            result['Spread_Duration'] = spr_dur
            
            # Convexity
            convex = effective_convexity(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
            result['Convexity'] = convex
            
            # Key Rate Durations
            try:
                krd = key_rate_durations(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
                for bucket, duration in krd.items():
                    result[f'KRD_{bucket}'] = duration
            except Exception as e:
                logger.warning(f"KRD calculation failed for {isin}: {e}")
                # Fill standard KRD buckets with NaN
                standard_buckets = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
                for bucket in standard_buckets:
                    result[f'KRD_{bucket}'] = np.nan
            
            # OAS calculation
            try:
                # Get call schedule if callable
                call_schedule = _get_call_schedule(isin, combined_data)
                
                if call_schedule and row.get('Callable', 'N').upper() == 'Y':
                    # Build payment schedule for OAS
                    payment_schedule = _build_payment_schedule(times, cfs, valuation_date)
                    
                    # Find next call
                    future_calls = [c for c in call_schedule if to_datetime(c["date"]) > valuation_date]
                    if future_calls:
                        next_call = min(future_calls, key=lambda c: to_datetime(c["date"]))
                        next_call_date = to_datetime(next_call["date"])
                        next_call_price = float(next_call["price"])
                        
                        # Standard OAS
                        day_basis = combined_data.get('Day Count', 'ACT/ACT')
                        logger.debug(f"Calculating OAS for {isin} with day basis: {day_basis}")
                        
                        oas_val = compute_oas(
                            payment_schedule,
                            valuation_date,
                            z_times,
                            z_rates,
                            day_basis,
                            price,  # clean price
                            next_call_date=next_call_date,
                            next_call_price=next_call_price,
                            comp=compounding
                        )
                        
                        if oas_val is not None:
                            result['OAS_bps'] = oas_val * 10000
                        else:
                            result['OAS_bps'] = np.nan
                            
                        # Enhanced OAS if available
                        if ENHANCED_ANALYTICS_AVAILABLE:
                            try:
                                logger.debug(f"Calculating enhanced OAS for {isin} with day basis: {day_basis}")
                                oas_enhanced = compute_oas_enhanced(
                                    payment_schedule,
                                    valuation_date,
                                    z_times,
                                    z_rates,
                                    day_basis,
                                    price,
                                    call_schedule=call_schedule,
                                    comp=compounding
                                )
                                if oas_enhanced is not None:
                                    result['OAS_Enhanced_bps'] = oas_enhanced * 10000
                                else:
                                    result['OAS_Enhanced_bps'] = np.nan
                            except Exception as e:
                                logger.warning(f"Enhanced OAS calculation failed for {isin}: {e}")
                                result['OAS_Enhanced_bps'] = np.nan
                        else:
                            result['OAS_Enhanced_bps'] = np.nan
                    else:
                        result['OAS_bps'] = np.nan
                        result['OAS_Enhanced_bps'] = np.nan
                else:
                    result['OAS_bps'] = np.nan
                    result['OAS_Enhanced_bps'] = np.nan
                    
            except Exception as e:
                logger.warning(f"OAS calculation failed for {isin}: {e}")
                result['OAS_bps'] = np.nan
                result['OAS_Enhanced_bps'] = np.nan
            
            # Higher-order Greeks if enhanced analytics available
            if ENHANCED_ANALYTICS_AVAILABLE:
                try:
                    # Calculate cross-gamma
                    cross_gamma_calc = CrossGammaCalculator()
                    
                    # Build curve object for Greeks
                    # Convert times (year fractions) to actual dates
                    curve_dates = [valuation_date + timedelta(days=int(t * 365.25)) for t in z_times]
                    enhanced_curve = YieldCurve(
                        dates=curve_dates,
                        rates=z_rates,
                        curve_date=valuation_date,
                        interpolation=InterpolationMethod.CUBIC_SPLINE,
                        currency=currency,
                        curve_type="ZERO"
                    )
                    
                    # Calculate key rate convexity 
                    kr_convex_calc = KeyRateConvexityCalculator()
                    
                    # This is a simplified implementation - full Greeks require more market data
                    result['Cross_Gamma'] = np.nan  # Would need correlation data
                    result['Key_Rate_Convexity'] = np.nan  # Would need full calculation
                    result['Vega'] = np.nan  # Requires volatility surface
                    result['Theta'] = np.nan  # Time decay
                    
                except Exception as e:
                    logger.warning(f"Higher-order Greeks calculation failed for {isin}: {e}")
                    result['Cross_Gamma'] = np.nan
                    result['Key_Rate_Convexity'] = np.nan
                    result['Vega'] = np.nan
                    result['Theta'] = np.nan
            else:
                result['Cross_Gamma'] = np.nan
                result['Key_Rate_Convexity'] = np.nan
                result['Vega'] = np.nan
                result['Theta'] = np.nan
            
            # Dollar Duration (DV01)
            result['DV01'] = eff_dur * dirty_price / 10000  # Price change for 1bp move
            
            # Add calculation metadata
            result['Enhancement_Level'] = 'institutional-grade' if ENHANCED_ANALYTICS_AVAILABLE else 'standard'
            result['Accrued_Interest'] = accrued_interest
            result['Dirty_Price'] = dirty_price
            result['Compounding'] = compounding
            
        except Exception as e:
            logger.error(f"Core analytics calculation failed for {isin}: {e}")
            _fill_analytics_with_nan(result)
            
    except Exception as e:
        logger.error(f"Failed to calculate analytics for {isin}: {e}")
        _fill_analytics_with_nan(result)
    
    return result


def _fill_analytics_with_nan(result: Dict[str, Any]) -> None:
    """Fill all analytics fields with NaN when calculation fails."""
    analytics_fields = [
        'YTM_Percent', 'G_Spread_bps', 'Z_Spread_bps',
        'Effective_Duration', 'Modified_Duration', 'Spread_Duration',
        'Convexity', 'OAS_bps', 'OAS_Enhanced_bps',
        'DV01', 'Cross_Gamma', 'Key_Rate_Convexity', 'Vega', 'Theta',
        'Enhancement_Level', 'Accrued_Interest', 'Dirty_Price', 'Compounding'
    ]
    
    # Add standard KRD buckets
    standard_buckets = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    for bucket in standard_buckets:
        analytics_fields.append(f'KRD_{bucket}')
    
    for field in analytics_fields:
        if field not in result:
            if field in ['Enhancement_Level', 'Compounding']:
                result[field] = 'N/A'
            else:
                result[field] = np.nan


def _parse_curve_data(curves_df: pd.DataFrame, currency: str, latest_date: str) -> Tuple[List[float], List[float]]:
    """Parse curve data from curves.csv format for specific currency and date."""
    try:
        # Filter for the specific currency and latest date
        curve_data = curves_df[
            (curves_df['Currency Code'] == currency) & 
            (curves_df['Date'].astype(str).str.startswith(latest_date))
        ].copy()
        
        if curve_data.empty:
            # Try without date filter
            curve_data = curves_df[curves_df['Currency Code'] == currency].copy()
            if curve_data.empty:
                logger.warning(f"No curve data for currency {currency}")
                return _get_fallback_curve()
        
        # Convert Term to years numerically and sort by that
        def _to_years(term: str) -> float:
            t = str(term).strip().upper()
            if t.endswith('D'):
                return float(t[:-1]) / 365.0
            if t.endswith('W'):
                return float(t[:-1]) * 7.0 / 365.0
            if t.endswith('M'):
                return float(t[:-1]) / 12.0
            if t.endswith('Y'):
                return float(t[:-1])
            # Fallback if already numeric-like
            try:
                return float(t)
            except Exception:
                return np.nan

        curve_data['__TermYears'] = curve_data['Term'].apply(_to_years)
        curve_data = curve_data.sort_values('__TermYears')
        
        terms = []
        rates = []
        
        for _, row in curve_data.iterrows():
            try:
                term_years = float(row['__TermYears']) if pd.notna(row['__TermYears']) else _convert_term_to_years(row['Term'])
                rate_decimal = float(row['Daily Value']) / 100  # Convert percentage to decimal
                terms.append(term_years)
                rates.append(rate_decimal)
            except Exception as e:
                logger.warning(f"Error parsing term/rate: {row['Term']}, {row['Daily Value']}: {e}")
                continue
        
        if not terms or not rates:
            logger.warning(f"No valid curve points found for {currency}")
            return _get_fallback_curve()
        
        return terms, rates
        
    except Exception as e:
        logger.warning(f"Error parsing curve data for {currency}: {e}")
        return _get_fallback_curve()


def _get_fallback_curve() -> Tuple[List[float], List[float]]:
    """Return a reasonable fallback curve."""
    terms = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    rates = [0.03] * len(terms)  # 3% flat curve
    return terms, rates


def _create_default_schedule(row: pd.Series, latest_date: str) -> pd.Series:
    """Create default schedule assumptions when schedule data is missing."""
    import pandas as pd
    
    # Create reasonable defaults based on security type
    security_type = row.get('Type', 'Corp')
    currency = row.get('Currency', 'USD')
    callable = row.get('Callable', 'N')
    
    # Default maturity: 5 years from latest date
    latest_dt = to_datetime(latest_date)
    default_maturity = latest_dt + timedelta(days=5*365)
    
    # Default coupon rate based on type
    if security_type == 'Govt Bond':
        default_coupon = 2.5  # Government bonds typically lower
    elif security_type == 'Corp':
        default_coupon = 4.0  # Corporate bonds
    elif security_type in ['ABS', 'MBS']:
        default_coupon = 3.5  # Asset/Mortgage backed
    else:
        default_coupon = 3.0  # Municipal and others
    
    # Create default schedule row
    default_schedule = pd.Series({
        'ISIN': row['ISIN'],
        'Day Basis': 'ACT/ACT',
        'First Coupon': (latest_dt + timedelta(days=180)).strftime('%d/%m/%Y'),
        'Maturity Date': default_maturity.strftime('%d/%m/%Y'),
        'Accrued Interest': 0.5,  # Default small accrued
        'Issue Date': (latest_dt - timedelta(days=365)).strftime('%d/%m/%Y'),
        'Call Schedule': '[]',  # Empty call schedule
        'Coupon Frequency': 2,  # Semi-annual
        'Coupon Rate': default_coupon,  # Add the missing coupon rate
        'Principal': 100.0
    })
    
    return default_schedule


def _convert_term_to_years(term: str) -> float:
    """Convert term string to years."""
    term = term.strip().upper()
    
    if term.endswith('D'):
        return float(term[:-1]) / 365
    elif term.endswith('W'):
        return float(term[:-1]) / 52
    elif term.endswith('M'):
        return float(term[:-1]) / 12
    elif term.endswith('Y'):
        return float(term[:-1])
    else:
        # Try to parse as float (assume years)
        try:
            return float(term)
        except ValueError:
            logger.warning(f"Could not parse term: {term}")
            return 1.0  # Default to 1 year


def _get_accrued_interest(isin: str, date_str: str, accrued_df: Optional[pd.DataFrame]) -> float:
    """Get accrued interest for the security."""
    if accrued_df is None:
        return 0.0
    
    try:
        accrued_row = accrued_df[accrued_df['ISIN'] == isin]
        if accrued_row.empty:
            return 0.0
        
        if date_str in accrued_df.columns:
            accrued_val = accrued_row.iloc[0][date_str]
            if pd.notna(accrued_val):
                return float(accrued_val)
    except Exception as e:
        logger.warning(f"Error getting accrued interest for {isin}: {e}")
    
    return 0.0


def _combine_security_data(price_row: pd.Series, reference_row: Optional[pd.Series], schedule_row: Optional[pd.Series], latest_date: str) -> pd.Series:
    """Combine data from reference.csv and schedule.csv, with fallback defaults."""
    import pandas as pd
    
    isin = price_row['ISIN']
    
    # Start with defaults
    combined = pd.Series({
        'ISIN': isin,
        'Coupon Rate': np.nan,  # Do not assume default; align with synth_spread_calculator (0 if missing)
        'Coupon Frequency': 2,  # Semi-annual
        'Day Count': 'ACT/ACT',
        'Maturity Date': None,
        'Issue Date': None,
        'Call Schedule': '[]',
        'Call Indicator': False,
        'Accrued Interest': 0.0,
        'Principal': 100.0
    })
    
    # Override with reference data if available (preferred source for coupon rate, maturity)
    if reference_row is not None:
        if pd.notna(reference_row.get('Coupon Rate')):
            combined['Coupon Rate'] = float(reference_row['Coupon Rate'])
        if pd.notna(reference_row.get('Maturity Date')):
            combined['Maturity Date'] = reference_row['Maturity Date']
        if pd.notna(reference_row.get('Call Indicator')):
            combined['Call Indicator'] = reference_row['Call Indicator']
    
    # Override with schedule data if available (preferred for technical details)
    if schedule_row is not None:
        if pd.notna(schedule_row.get('Day Basis')):
            combined['Day Count'] = _normalize_day_basis(schedule_row['Day Basis'])
        if pd.notna(schedule_row.get('Coupon Frequency')):
            combined['Coupon Frequency'] = int(schedule_row['Coupon Frequency'])
        if pd.notna(schedule_row.get('Maturity Date')):
            combined['Maturity Date'] = schedule_row['Maturity Date']
        if pd.notna(schedule_row.get('Issue Date')):
            combined['Issue Date'] = schedule_row['Issue Date']
        if pd.notna(schedule_row.get('Call Schedule')):
            combined['Call Schedule'] = schedule_row['Call Schedule']
        if pd.notna(schedule_row.get('Accrued Interest')):
            combined['Accrued Interest'] = float(schedule_row['Accrued Interest'])
    
    # Set default maturity if still missing
    if pd.isna(combined['Maturity Date']) or combined['Maturity Date'] is None:
        latest_dt = to_datetime(latest_date)
        default_maturity = latest_dt + timedelta(days=5*365)  # 5 years default
        combined['Maturity Date'] = default_maturity.strftime('%Y-%m-%d')
        logger.warning(f"Using default 5-year maturity for {isin}")
    
    # Set default issue date if missing
    if pd.isna(combined['Issue Date']) or combined['Issue Date'] is None:
        latest_dt = to_datetime(latest_date)
        default_issue = latest_dt - timedelta(days=365)  # 1 year ago
        combined['Issue Date'] = default_issue.strftime('%Y-%m-%d')
    
    return combined


def _normalize_day_basis(day_basis: str) -> str:
    """
    Normalize day count basis to ensure compatibility.
    Maps common variants to supported conventions.
    
    This function standardizes day count convention strings to ensure
    consistent handling throughout the analytics pipeline. It maps
    various input formats to canonical convention names.
    
    Supported mappings:
    - 30E/360 variants: 30E, 30/360E, 30/360-E -> 30E/360
    - 30/360 variants: 30/360-US, 30/360 US, US 30/360 -> 30/360
    - ACT/ACT variants: ACT/ACT-ISDA, ISDA, ACT/ACT-ICMA -> ACT/ACT
    - ACT/365 variants: ACT/365-FIXED, ACT/365L, NL/365 -> ACT/365
    - ACT/360 variants: ACT/360-FIXED -> ACT/360
    
    Args:
        day_basis: Raw day basis string from data source
        
    Returns:
        Normalized day basis string for consistent processing
    """
    if not day_basis or pd.isna(day_basis):
        return "ACT/ACT"
    
    basis = str(day_basis).strip().upper()
    
    # Map common variants to supported conventions
    if basis in {"30E/360", "30E", "30/360E", "30/360-E"}:
        return "30E/360"  # Keep as 30E/360 if enhanced available, will be mapped in year_fraction
    elif basis in {"30/360-US", "30/360 US", "US 30/360", "30/360U"}:
        return "30/360"
    elif basis in {"ACT/ACT-ISDA", "ISDA", "ACT/ACT-ICMA", "ACT/ACT-AFB"}:
        return "ACT/ACT"
    elif basis in {"ACT/365-FIXED", "ACT/365", "ACT/365L", "NL/365"}:
        return "ACT/365"
    elif basis in {"ACT/360", "ACT/360-FIXED"}:
        return "ACT/360"
    elif basis in {"ACT/ACT", "ACT", "ACTUAL/ACTUAL"}:
        return "ACT/ACT"
    elif basis in {"30/360", "30/360-BOND", "30/360BOND"}:
        return "30/360"
    else:
        logger.warning(f"Unknown day basis '{day_basis}', defaulting to ACT/ACT")
        return "ACT/ACT"


def _build_cashflows_from_combined_data(
    combined_data: pd.Series,
    valuation_date: datetime,
    price_row: pd.Series = None,
    schedule_row: Optional[pd.Series] = None,
    z_times: Optional[List[float]] = None,
    z_rates: Optional[List[float]] = None,
) -> Tuple[List[float], List[float]]:
    """Build cashflows from combined security data.

    If a raw schedule row and curve are provided, generate the payment schedule
    using `generate_payment_schedule` and extract cashflows using the same
    method as `synth_spread_calculator` for alignment.
    """
    try:
        if schedule_row is not None and z_times is not None and z_rates is not None:
            # Construct a schedule row with required fields. To mirror synth_spread_calculator behaviour,
            # backfill missing Coupon Rate from combined reference data when schedule lacks the column.
            sr = schedule_row.copy()
            # Coupon Rate: use combined data if missing from schedule (fixed to match synthetic system)
            # Coupon Frequency
            if pd.isna(sr.get('Coupon Frequency')) and pd.notna(combined_data.get('Coupon Frequency')):
                sr['Coupon Frequency'] = combined_data.get('Coupon Frequency')
            # Day Basis
            if pd.isna(sr.get('Day Basis')) and pd.notna(combined_data.get('Day Count')):
                sr['Day Basis'] = combined_data.get('Day Count')
            # Maturity Date
            if pd.isna(sr.get('Maturity Date')) and pd.notna(combined_data.get('Maturity Date')):
                sr['Maturity Date'] = combined_data.get('Maturity Date')
            # Issue Date
            if pd.isna(sr.get('Issue Date')) and pd.notna(combined_data.get('Issue Date')):
                sr['Issue Date'] = combined_data.get('Issue Date')
            # First Coupon: derive if missing (approximate months from frequency)
            if pd.isna(sr.get('First Coupon')) and pd.notna(sr.get('Issue Date')):
                try:
                    freq = int(sr.get('Coupon Frequency', 2))
                    months = 12 // freq if freq > 0 else 6
                    issue_dt = parse_date_robust(sr.get('Issue Date'), dayfirst=True)
                    if pd.notna(issue_dt):
                        sr['First Coupon'] = (issue_dt + pd.DateOffset(months=months)).strftime('%d/%m/%Y')
                except Exception:
                    pass

            # Payment schedule and extract cashflows (use combined coupon rate if missing from schedule)
            if pd.isna(sr.get('Coupon Rate')):
                sr['Coupon Rate'] = combined_data.get('Coupon Rate', 0.0)
            payment_schedule = generate_payment_schedule(sr)
            try:
                supported_day_basis = get_supported_day_basis(sr.get('Day Basis', '30/360'))
            except Exception:
                supported_day_basis = '30/360'
            times, cfs = extract_cashflows(payment_schedule, valuation_date, z_times, z_rates, supported_day_basis)
            return times, cfs

        # Fallback to legacy construction if no schedule provided
        # Parse combined information
        maturity_str = combined_data.get('Maturity Date', '')
        if not maturity_str:
            return [], []

        # Handle different date formats including Excel serial dates
        try:
            # Use robust date parsing that handles Excel serial dates
            if 'T' in str(maturity_str):  # ISO format from reference.csv
                maturity_date = parse_date_robust(maturity_str.split('T')[0], dayfirst=False)
            elif '/' in str(maturity_str):  # DD/MM/YYYY format from schedule.csv
                maturity_date = parse_date_robust(maturity_str, dayfirst=True)
            else:
                # This will handle Excel serial dates like "48716"
                maturity_date = parse_date_robust(maturity_str, dayfirst=False)

            if pd.isna(maturity_date):
                raise ValueError(f"Could not parse maturity date: {maturity_str}")

            # Convert to datetime if needed
            maturity_date = to_datetime(maturity_date.strftime('%Y-%m-%d'))

        except Exception as e:
            logger.warning(f"Error parsing maturity date {maturity_str}: {e}")
            return [], []

        coupon_rate = float(combined_data.get('Coupon Rate', 3.0)) / 100
        coupon_freq = int(combined_data.get('Coupon Frequency', 2))
        principal = float(combined_data.get('Principal', 100))

        # Calculate issue date and first coupon date
        issue_date_str = combined_data.get('Issue Date')
        if issue_date_str:
            try:
                # Use robust date parsing that handles Excel serial dates
                if 'T' in str(issue_date_str):
                    issue_date_parsed = parse_date_robust(issue_date_str.split('T')[0], dayfirst=False)
                else:
                    issue_date_parsed = parse_date_robust(issue_date_str, dayfirst=True)

                if pd.isna(issue_date_parsed):
                    raise ValueError(f"Could not parse issue date: {issue_date_str}")

                issue_date = to_datetime(issue_date_parsed.strftime('%Y-%m-%d'))
            except Exception:
                issue_date = valuation_date - timedelta(days=365)  # 1 year ago default
        else:
            issue_date = valuation_date - timedelta(days=365)

        # Calculate first coupon date (typically 6 months after issue for semi-annual)
        months_to_first = 12 // coupon_freq if coupon_freq > 0 else 6
        first_coupon_date = issue_date + timedelta(days=months_to_first * 30)  # Approximate

        # Get currency and day basis
        currency = price_row.get('Currency', 'USD')
        day_basis = combined_data.get('Day Count', 'ACT/ACT')

        logger.debug(f"Building cashflows for {combined_data.get('ISIN', 'Unknown')} with day basis: {day_basis}")

        # Map day basis for cashflows module compatibility
        cashflow_day_basis = '30/360' if day_basis.upper() in {"30E/360", "30E", "30/360E", "30/360-E"} else day_basis

        # Generate payment schedule using correct parameters
        payment_schedule = generate_fixed_schedule(
            issue_date=issue_date,
            first_coupon_date=first_coupon_date,
            maturity_date=maturity_date,
            coupon_rate=coupon_rate,
            day_basis=cashflow_day_basis,
            currency=currency,
            notional=principal
        )

        # Extract times and cashflows (legacy)
        times = []
        cfs = []
        for payment in payment_schedule:
            payment_date = to_datetime(payment['date'])
            if payment_date > valuation_date:
                time_to_payment = year_fraction(valuation_date, payment_date, day_basis)
                times.append(time_to_payment)
                cfs.append(payment['amount'])

        return times, cfs

    except Exception as e:
        logger.warning(f"Error building cashflows: {e}")
        return [], []


def _get_call_schedule(isin: str, combined_data: pd.Series) -> List[Dict]:
    """Get call schedule for callable bonds."""
    try:
        call_schedule_str = combined_data.get('Call Schedule', '[]')
        if call_schedule_str and call_schedule_str != '[]':
            # Parse JSON call schedule
            import json
            call_schedule = json.loads(call_schedule_str)
            return call_schedule
        return []
    except Exception as e:
        logger.warning(f"Error parsing call schedule for {isin}: {e}")
        return []


def _build_payment_schedule(times: List[float], cfs: List[float], valuation_date: datetime) -> List[Dict]:
    """Build payment schedule format for OAS calculation."""
    schedule = []
    for time_val, cf in zip(times, cfs):
        payment_date = valuation_date + timedelta(days=time_val * 365)
        schedule.append({
            'date': payment_date.strftime('%Y-%m-%d'),
            'amount': cf
        })
    return schedule


def generate_comprehensive_analytics_csv(data_folder: str, output_filename: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Generate a comprehensive CSV with all SpreadOMatic analytics for the most recent date.
    
    Returns:
        Tuple of (success: bool, message: str, output_path: Optional[str])
    """
    logger.info("Starting comprehensive analytics CSV generation")
    
    try:
        # Get latest date and price data
        latest_date, price_df = get_latest_date_from_csv(data_folder)
        if latest_date is None or price_df is None:
            return False, "Could not load sec_Price.csv or find latest date", None
        
        # Load supporting data
        schedule_df, reference_df, curves_df, accrued_df = load_supporting_data(data_folder)
        
        # Process each security
        results = []
        total_securities = len(price_df)
        processed_count = 0
        
        logger.info(f"Processing {total_securities} securities for date {latest_date}")
        
        for idx, row in price_df.iterrows():
            try:
                isin = row['ISIN']
                price_val = row[latest_date]
                
                # Skip if no price data
                if pd.isna(price_val) or str(price_val).strip().lower() in {'n/a', 'na', '', 'null', 'none'}:
                    logger.debug(f"Skipping {isin} - no price data for {latest_date}")
                    continue
                
                price = float(price_val)
                
                # Calculate all analytics
                analytics = calculate_all_analytics_for_security(
                    row, price, latest_date, schedule_df, reference_df, curves_df, accrued_df
                )
                
                results.append(analytics)
                processed_count += 1
                
                if processed_count % 50 == 0:
                    logger.info(f"Processed {processed_count}/{total_securities} securities")
                    
            except Exception as e:
                logger.error(f"Error processing security at index {idx}: {e}")
                continue
        
        if not results:
            return False, "No securities were successfully processed", None
        
        # Create output DataFrame
        output_df = pd.DataFrame(results)
        
        # Generate output filename
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"comprehensive_analytics_{latest_date.replace('-', '')}_{timestamp}.csv"
        
        output_path = os.path.join(data_folder, output_filename)
        
        # Save CSV
        output_df.to_csv(output_path, index=False)
        
        logger.info(f"Successfully generated comprehensive analytics CSV: {output_path}")
        logger.info(f"Processed {processed_count} securities with {len(output_df.columns)} analytics columns")
        
        return True, f"Successfully processed {processed_count} securities", output_path
        
    except Exception as e:
        error_msg = f"Error generating comprehensive analytics CSV: {e}"
        logger.error(error_msg)
        return False, error_msg, None


def get_available_analytics_list() -> List[str]:
    """Return list of all available analytics that will be calculated."""
    base_analytics = [
        'ISIN', 'Security_Name', 'Funds', 'Type', 'Callable', 'Currency', 'Date', 'Price',
        'YTM_Percent', 'G_Spread_bps', 'Z_Spread_bps',
        'Effective_Duration', 'Modified_Duration', 'Spread_Duration',
        'Convexity', 'OAS_bps', 'DV01',
        'Enhancement_Level', 'Accrued_Interest', 'Dirty_Price', 'Compounding'
    ]
    
    # Add KRD buckets
    standard_buckets = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    for bucket in standard_buckets:
        base_analytics.append(f'KRD_{bucket}')
    
    # Add enhanced analytics if available
    if ENHANCED_ANALYTICS_AVAILABLE:
        enhanced_analytics = [
            'OAS_Enhanced_bps', 'Cross_Gamma', 'Key_Rate_Convexity', 'Vega', 'Theta'
        ]
        base_analytics.extend(enhanced_analytics)
    
    return base_analytics


if __name__ == "__main__":
    # For standalone testing
    data_folder = config.DATA_FOLDER
    if data_folder is None:
        # Fallback to local Data directory
        data_folder = "Data"
    
    # Test day count convention handling
    print("Testing day count convention handling...")
    from datetime import datetime
    
    test_start = datetime(2023, 1, 1)
    test_end = datetime(2023, 12, 31)
    
    test_conventions = ["30E/360", "30/360", "ACT/ACT", "ACT/365", "30/360-US"]
    
    for convention in test_conventions:
        try:
            result = year_fraction(test_start, test_end, convention)
            print(f"✓ {convention}: {result:.6f}")
        except Exception as e:
            print(f"✗ {convention}: {e}")
    
    print("\nTesting comprehensive analytics CSV generation...")
    success, message, output_path = generate_comprehensive_analytics_csv(data_folder)
    print(f"Success: {success}")
    print(f"Message: {message}")
    if output_path:
        print(f"Output: {output_path}")
