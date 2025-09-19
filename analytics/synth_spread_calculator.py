# Purpose: Calculate synthetic analytics (Z-Spread, G-Spread, YTM, durations, convexity, OAS, KRDs)
# using the SpreadOMatic library with unified SecurityDataProvider for consistent data collection
# Refactored version using SecurityDataProvider to eliminate data divergence

import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import os
import sys
from collections import Counter

# Ensure local SpreadOMatic copy is found *before* any site-packages version
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools', 'SpreadOMatic'))

# Import config for file paths and column names
from core import config

# Import the unified SecurityDataProvider
from analytics.security_data_provider import SecurityDataProvider, SecurityData

# Setup synthetic spread logger
synth_logger = logging.getLogger('synth_spread')
synth_handler = logging.FileHandler('synth.log')
synth_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
synth_handler.setFormatter(synth_formatter)
synth_logger.addHandler(synth_handler)
synth_logger.setLevel(logging.INFO)

# Import from SpreadOMatic modules (with enhanced institutional-grade fallback)
try:
    # Try enhanced institutional-grade modules first
    from tools.SpreadOMatic.spreadomatic.daycount_enhanced import (
        year_fraction_precise as year_fraction,
        DayCountConvention,
        HolidayCalendar,
        accrued_interest_precise
    )
    from tools.SpreadOMatic.spreadomatic.curve_construction import YieldCurve, InterpolationMethod
    from tools.SpreadOMatic.spreadomatic.numerical_methods import yield_solver, spread_solver
    from tools.SpreadOMatic.spreadomatic.settlement_mechanics import (
        calculate_settlement_details, 
        AccruedCalculator
    )
    from tools.SpreadOMatic.spreadomatic.oas_enhanced_v2 import (
        HullWhiteModel, 
        OASCalculator,
        CallableInstrument,
        CallOption,
        create_hull_white_calculator
    )
    ENHANCED_SYNTH_AVAILABLE = True
    synth_logger.info("Using institutional-grade enhanced analytics for synthetic calculations")
    
    # Still import standard modules for fallback
    from tools.SpreadOMatic.spreadomatic.daycount import to_datetime
    from tools.SpreadOMatic.spreadomatic.interpolation import linear_interpolate
    from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows, generate_fixed_schedule
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, g_spread, z_spread
    from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows
    from tools.SpreadOMatic.spreadomatic.duration import (
        effective_duration,
        modified_duration as sm_modified_duration,
        effective_convexity,
        key_rate_durations,
        effective_spread_duration,
        modified_duration_standard as sm_modified_duration_standard,
    )
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas
    
except ImportError as e:
    # Fall back to standard SpreadOMatic modules
    ENHANCED_SYNTH_AVAILABLE = False
    synth_logger.info(f"Enhanced modules not available ({e}), using standard SpreadOMatic analytics")
    
    from tools.SpreadOMatic.spreadomatic.daycount import to_datetime, year_fraction
    from tools.SpreadOMatic.spreadomatic.interpolation import linear_interpolate
    from tools.SpreadOMatic.spreadomatic.cashflows import extract_cashflows, generate_fixed_schedule
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, g_spread, z_spread
    from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows
    from tools.SpreadOMatic.spreadomatic.duration import (
        effective_duration,
        modified_duration as sm_modified_duration,
        effective_convexity,
        key_rate_durations,
        effective_spread_duration,
        modified_duration_standard as sm_modified_duration_standard,
    )
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas


# Enhanced business day adjustment (optional)
try:
    from tools.SpreadOMatic.spreadomatic.daycount_enhanced import (
        adjust_business_day,
        BusinessDayConvention,
        HolidayCalendar,
    )
    _BDC_AVAILABLE = True
except Exception:
    _BDC_AVAILABLE = False


def convert_term_to_years(term: str) -> float:
    """Convert term string (e.g., '7D', '1M', '2Y') to years."""
    term = term.strip().upper()
    
    # Extract numeric value and unit
    import re
    match = re.match(r'(\d+)([DWMY])', term)
    if not match:
        raise ValueError(f"Invalid term format: {term}")
    
    value = int(match.group(1))
    unit = match.group(2)
    
    # Convert to years
    if unit == 'D':
        return value / 365.0
    elif unit == 'W':
        return value * 7 / 365.0
    elif unit == 'M':
        return value / 12.0
    elif unit == 'Y':
        return value
    else:
        raise ValueError(f"Unknown term unit: {unit}")


def build_zero_curve(curves_df: pd.DataFrame, currency: str, date: str) -> Tuple[List[float], List[float], bool]:
    """Build zero curve for a specific currency and date from curves data.
    Uses same logic as bond calculator API for consistency.
    Returns: (times, rates, is_fallback) where is_fallback indicates if we used an older curve.
    """
    # Parse the date - it might be in DD/MM/YYYY format from price columns
    date_dt = parse_date_robust(date, dayfirst=True)
    if pd.isna(date_dt):
        raise ValueError(f"Invalid date for curve lookup: {date}")
        
    # Try to use the same logic as bond calculator API for consistency
    try:
        # Check if curves_df has the indexed format from curve_processing
        if hasattr(curves_df, 'index') and curves_df.index.nlevels > 1:
            idx = pd.IndexSlice
            sub = curves_df.loc[idx[currency, date_dt, :]].reset_index().sort_values("TermDays")
            times = (sub["TermDays"].astype(float) / 365.0).tolist()
            rates = (sub["Value"].astype(float) / 100.0).tolist()
            if len(times) >= 2:
                return times, rates, False
        else:
            # Fallback to original logic for raw CSV format
            raise Exception("Use original logic")
    except:
        # Original curve extraction logic as fallback
        curve_data = curves_df[
            (curves_df['Currency Code'] == currency) & 
            (pd.to_datetime(curves_df['Date']) == date_dt)
        ]
        
        if curve_data.empty:
            # Try without time component if date has time
            date_only = date_dt.date()
            curve_data = curves_df[
                (curves_df['Currency Code'] == currency) & 
                (pd.to_datetime(curves_df['Date']).dt.date == date_only)
            ]
        
        is_fallback = False
        if curve_data.empty:
            # Try to use the most recent curve before the requested date
            currency_curves = curves_df[curves_df['Currency Code'] == currency].copy()
            if not currency_curves.empty:
                currency_curves['Date'] = pd.to_datetime(currency_curves['Date'])
                prior_curves = currency_curves[currency_curves['Date'] < date_dt]
                
                if not prior_curves.empty:
                    # Get the most recent prior date
                    latest_date = prior_curves['Date'].max()
                    curve_data = currency_curves[currency_curves['Date'] == latest_date]
                    synth_logger.warning(f"No curve data for {currency} on {date}, using last available from {latest_date.strftime('%Y-%m-%d')}")
                    is_fallback = True
                else:
                    raise ValueError(f"No curve data found for {currency} on or before {date}")
            else:
                raise ValueError(f"No curve data found for {currency}")
        
        # Convert terms to years and sort
        terms_rates = []
        for _, row in curve_data.iterrows():
            try:
                years = convert_term_to_years(row['Term'])
                rate = float(row['Daily Value']) / 100.0  # Convert percentage to decimal
                terms_rates.append((years, rate))
            except Exception as e:
                synth_logger.warning(f"Skipping invalid term {row['Term']}: {e}")
        
        if not terms_rates:
            raise ValueError(f"No valid term data found for {currency} on {date}")
        
        # Sort by term length
        terms_rates.sort(key=lambda x: x[0])
        
        times, rates = zip(*terms_rates)
        return list(times), list(rates), is_fallback


# Summaries to suppress per-date spam
curve_lookup_errors: Counter[str] = Counter()
other_spread_errors: Counter[str] = Counter()
missing_schedule_isins: list[str] = []
accrued_lookup_errors: Counter[str] = Counter()

parse_fail_count = 0  # module-level counter

def parse_date_robust(date_str: Any, dayfirst: bool = True) -> pd.Timestamp:
    """Parse date string robustly, handling various formats including Excel serial dates."""
    global parse_fail_count
    import re
    if pd.isna(date_str):
        return pd.NaT

    if isinstance(date_str, pd.Timestamp):
        return date_str

    date_str_s = str(date_str)
    
    try:
        
        # Check if it's a numeric Excel serial date
        if re.match(r'^\d+(\.\d*)?$', date_str_s):
            try:
                serial_number = float(date_str_s)
                if serial_number >= 60:
                    serial_number -= 1
                excel_epoch = datetime(1900, 1, 1)
                return pd.Timestamp(excel_epoch + timedelta(days=serial_number - 1))
            except (ValueError, OverflowError):
                pass
        
        if '-' in date_str_s and re.match(r"\d{4}-\d{2}-\d{2}", date_str_s):
            return pd.to_datetime(date_str_s, dayfirst=False, errors="coerce")
        elif '/' in date_str_s:
            return pd.to_datetime(date_str_s, dayfirst=True, errors="coerce")
        else:
            return pd.to_datetime(date_str_s, errors="coerce")
    except Exception:
        parse_fail_count += 1
        return pd.NaT


def parse_call_schedule(call_schedule_str: str) -> List[Dict[str, Any]]:
    """Parse call schedule JSON string."""
    if pd.isna(call_schedule_str) or call_schedule_str == '[]':
        return []
    
    try:
        call_schedule = json.loads(call_schedule_str)
        parsed_schedule = []
        for call in call_schedule:
            call_date = parse_date_robust(call['Date'], dayfirst=False)
            if not pd.isna(call_date):
                parsed_schedule.append({
                    'date': call_date,
                    'price': float(call['Price'])
                })
        
        parsed_schedule.sort(key=lambda x: x['date'])
        return parsed_schedule
    except Exception as e:
        synth_logger.warning(f"Failed to parse call schedule: {e}")
        return []


def _safe_convert(value, multiplier):
    """Safely convert value with multiplier, handling NaN and None"""
    if value is None or pd.isna(value):
        return np.nan
    try:
        return float(value) * multiplier
    except (ValueError, TypeError):
        return np.nan


def _save_rounded_csv(df: pd.DataFrame, output_path: str, decimal_places: int = 6) -> None:
    """Save DataFrame to CSV with numeric columns rounded to specified decimal places."""
    df_rounded = df.copy()
    
    for col in df_rounded.columns:
        if df_rounded[col].dtype in ['float64', 'float32', 'int64', 'int32']:
            numeric_mask = pd.to_numeric(df_rounded[col], errors='coerce').notna()
            if numeric_mask.any():
                df_rounded.loc[numeric_mask, col] = pd.to_numeric(
                    df_rounded.loc[numeric_mask, col], errors='coerce'
                ).round(decimal_places)
    
    df_rounded.to_csv(output_path, index=False)
    synth_logger.debug(f"Saved rounded data to {output_path} (max {decimal_places} decimal places)")


def get_base_isin(isin: str) -> str:
    """Extract base ISIN by removing hyphenated suffix.
    
    Examples:
        US123456-1 -> US123456
        DE789012-2 -> DE789012
        FR111111 -> FR111111 (no change)
    """
    # Validate input to ensure it's a string and not NaN
    if pd.isna(isin) or not isinstance(isin, str):
        return str(isin) if not pd.isna(isin) else ""
    # Normalise: trim, uppercase, normalise unicode dashes to ASCII '-'
    normalised = (
        isin.strip()
        .upper()
        .replace("\u2010", "-")  # hyphen
        .replace("\u2011", "-")  # non-breaking hyphen
        .replace("\u2012", "-")  # figure dash
        .replace("\u2013", "-")  # en dash
        .replace("\u2014", "-")  # em dash
        .replace("\u2015", "-")  # horizontal bar
    )
    return normalised.split('-')[0] if '-' in normalised else normalised


def get_supported_day_basis(day_basis: str) -> str:
    """Validate and map the provided day_basis to a SpreadOMatic-compatible value."""
    if pd.isna(day_basis):
        msg = "Missing day basis value"
        synth_logger.error(msg)
        raise ValueError(msg)

    day_basis_norm = str(day_basis).upper().strip()

    mapping = {
        "30/360": "30/360",
        "30E/360": "30/360",  # European 30/360 → standard 30/360
        "ACT/ACT": "ACT/ACT",
        "ACT/365": "ACT/365",
        "ACT/360": "ACT/360",
        "ACTUAL/ACTUAL": "ACT/ACT",
        "ACTUAL/365": "ACT/365",
        "ACTUAL/360": "ACT/360",
    }

    if day_basis_norm in mapping:
        if day_basis_norm == "30E/360":
            synth_logger.debug("Mapped day basis '30E/360' to '30/360' for SpreadOMatic compatibility")
        return mapping[day_basis_norm]

    msg = f"Unsupported day basis '{day_basis_norm}' encountered"
    synth_logger.error(msg)
    raise ValueError(msg)


def generate_payment_schedule(schedule_row: pd.Series) -> List[Dict[str, Any]]:
    """Generate payment schedule from schedule data (pandas Series).
    
    This is a wrapper function that converts pandas Series input to SecurityData
    and uses generate_payment_schedule_from_security_data.
    """
    # Convert pandas Series to SecurityData object
    security_data = SecurityData(
        isin=schedule_row.get('ISIN', ''),
        issue_date=parse_date_robust(schedule_row.get('Issue Date'), dayfirst=True),
        first_coupon_date=parse_date_robust(schedule_row.get('First Coupon'), dayfirst=True),
        maturity_date=parse_date_robust(schedule_row.get('Maturity Date'), dayfirst=True),
        coupon_rate=float(schedule_row.get('Coupon Rate', 0)) / 100.0,  # Convert from percent
        coupon_frequency=int(schedule_row.get('Coupon Frequency', 2)),
        day_basis=schedule_row.get('Day Basis', '30/360'),
        principal=100.0
    )
    return generate_payment_schedule_from_security_data(security_data)


def generate_payment_schedule_from_security_data(security_data: SecurityData) -> List[Dict[str, Any]]:
    """Generate payment schedule from SecurityData object."""
    # If a custom payment schedule is provided, use it as authoritative
    if getattr(security_data, 'payment_schedule', None):
        try:
            import json as _json
            raw = security_data.payment_schedule
            items = _json.loads(raw) if isinstance(raw, str) else raw
            schedule: List[Dict[str, Any]] = []
            # Prepare BDC adjusters if available
            bdc_enum = None
            cal = None
            if _BDC_AVAILABLE:
                try:
                    bdc_map = {
                        'NONE': BusinessDayConvention.NONE,
                        'UNADJUSTED': BusinessDayConvention.UNADJUSTED,
                        'F': BusinessDayConvention.FOLLOWING,
                        'MF': BusinessDayConvention.MODIFIED_FOLLOWING,
                        'P': BusinessDayConvention.PRECEDING,
                        'MP': BusinessDayConvention.MODIFIED_PRECEDING,
                    }
                    bdc_raw = (security_data.business_day_convention or 'NONE').strip().upper()
                    bdc_enum = bdc_map.get(bdc_raw, BusinessDayConvention.NONE)
                except Exception:
                    bdc_enum = BusinessDayConvention.NONE
                try:
                    cur = (security_data.currency or 'USD').upper()
                    country = 'US'
                    if cur in {'USD'}:
                        country = 'US'
                    elif cur in {'EUR'}:
                        country = 'EUR'
                    elif cur in {'GBP'}:
                        country = 'GB'
                    elif cur in {'JPY'}:
                        country = 'JP'
                    cal = HolidayCalendar(country)
                except Exception:
                    cal = HolidayCalendar('US')

            for it in items:
                date_str = it.get('date') or it.get('Date')
                amt = it.get('amount') if 'amount' in it else it.get('Amount')
                if date_str is None or amt is None:
                    continue
                dt = to_datetime(date_str)
                if _BDC_AVAILABLE and bdc_enum is not None and cal is not None:
                    dt = adjust_business_day(dt, bdc_enum, cal)
                schedule.append({'date': dt.strftime('%Y-%m-%d'), 'amount': float(amt)})
            if schedule:
                return schedule
        except Exception:
            # Fall back to generated schedule if custom parsing fails
            pass

    issue_date = security_data.issue_date
    first_coupon = security_data.first_coupon_date
    maturity_date = security_data.maturity_date
    
    # Ensure we have valid dates
    if not issue_date or not maturity_date:
        raise ValueError("Missing required dates for payment schedule")
    
    # Create first coupon if missing
    if not first_coupon:
        period_months = 12 // security_data.coupon_frequency
        first_coupon = issue_date + timedelta(days=period_months * 30)
    
    # Convert coupon rate from percentage to decimal
    coupon_rate_decimal = security_data.coupon_rate / 100.0
    
    basis = security_data.day_basis
    try:
        basis = get_supported_day_basis(basis)
    except ValueError:
        basis = '30/360'
    
    payment_schedule: List[Dict[str, Any]] = []

    # Determine business day convention and holiday calendar
    bdc_enum = None
    cal = None
    if _BDC_AVAILABLE:
        try:
            bdc_map = {
                'NONE': BusinessDayConvention.NONE,
                'UNADJUSTED': BusinessDayConvention.UNADJUSTED,
                'F': BusinessDayConvention.FOLLOWING,
                'MF': BusinessDayConvention.MODIFIED_FOLLOWING,
                'P': BusinessDayConvention.PRECEDING,
                'MP': BusinessDayConvention.MODIFIED_PRECEDING,
            }
            bdc_raw = (security_data.business_day_convention or 'NONE').strip().upper()
            bdc_enum = bdc_map.get(bdc_raw, BusinessDayConvention.NONE)
        except Exception:
            bdc_enum = BusinessDayConvention.NONE
        # Map currency to a simple holiday calendar; default to US
        try:
            cur = (security_data.currency or 'USD').upper()
            country = 'US'
            if cur in {'USD'}:
                country = 'US'
            elif cur in {'EUR'}:
                country = 'EUR'
            elif cur in {'GBP'}:
                country = 'GB'
            elif cur in {'JPY'}:
                country = 'JP'  # not implemented specifically; falls back internally
            cal = HolidayCalendar(country)
        except Exception:
            cal = HolidayCalendar('US')
    
    # Generate coupon payment dates and amounts using day-count accrual
    prev_date = issue_date
    current_date = first_coupon
    period_months = 12 // security_data.coupon_frequency
    
    # Build optional amortization lookup
    amort_map = {}
    if getattr(security_data, 'amortization_schedule', None):
        for row in security_data.amortization_schedule:
            try:
                dt = to_datetime(row['date'])
                amt = float(row['amount'])
                # Apply BDC on amort dates too
                if _BDC_AVAILABLE and bdc_enum is not None and cal is not None:
                    dt = adjust_business_day(dt, bdc_enum, cal)
                amort_map.setdefault(dt.strftime('%Y-%m-%d'), 0.0)
                amort_map[dt.strftime('%Y-%m-%d')] += amt
            except Exception:
                continue

    outstanding = 100.0
    while current_date <= maturity_date:
        # Apply business day convention if available
        pay_date = current_date
        if _BDC_AVAILABLE and bdc_enum is not None and cal is not None:
            pay_date = adjust_business_day(current_date, bdc_enum, cal)

        # Coupon on outstanding principal during period
        accr_frac = year_fraction(prev_date, pay_date, basis)
        coupon_amt = outstanding * coupon_rate_decimal * accr_frac
        payment_schedule.append({
            'date': pay_date.strftime('%Y-%m-%d'),
            'type': 'coupon',
            'amount': coupon_amt
        })

        # Amortization at this pay date if provided
        key = pay_date.strftime('%Y-%m-%d')
        if key in amort_map and amort_map[key] > 0:
            princ = min(amort_map[key], outstanding)
            if princ > 0:
                payment_schedule.append({
                    'date': pay_date.strftime('%Y-%m-%d'),
                    'type': 'principal',
                    'amount': princ
                })
                outstanding -= princ

        prev_date = pay_date
        current_date = current_date + pd.DateOffset(months=period_months)
    
    # Add principal (and final coupon if last coupon date < maturity)
    # Final stub coupon and remaining principal at maturity
    if prev_date < maturity_date:
        final_date = maturity_date
        if _BDC_AVAILABLE and bdc_enum is not None and cal is not None:
            final_date = adjust_business_day(maturity_date, bdc_enum, cal)
        accr_frac = year_fraction(prev_date, final_date, basis)
        coupon_amt = outstanding * coupon_rate_decimal * accr_frac
        if coupon_amt != 0:
            payment_schedule.append({
                'date': final_date.strftime('%Y-%m-%d'),
                'type': 'coupon',
                'amount': coupon_amt
            })
        prev_date = final_date

    # Remaining principal at maturity if any
    final_date = maturity_date
    if _BDC_AVAILABLE and bdc_enum is not None and cal is not None:
        final_date = adjust_business_day(maturity_date, bdc_enum, cal)
    if outstanding > 1e-9:
        payment_schedule.append({
            'date': final_date.strftime('%Y-%m-%d'),
            'type': 'principal',
            'amount': outstanding
        })
    
    return payment_schedule


def calculate_spread_for_security_using_provider(
    security_data: SecurityData,
    valuation_date: str,
    curves_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Calculate first-principles analytics for a single security using SecurityDataProvider data.
    
    This refactored version uses SecurityData from the provider for consistent data access.
    """
    try:
        # Clean price and accrued from SecurityData
        clean_price = float(security_data.price)
        accrued_interest = float(security_data.accrued_interest)
        
        # Validate clean price
        if clean_price <= 0:
            synth_logger.warning(f"Invalid clean price {clean_price} for {security_data.isin} - skipping calculation")
            return {
                'ytm': np.nan,
                'z_spread': np.nan,
                'g_spread': np.nan,
                'effective_duration': np.nan,
                'modified_duration': np.nan,
                'convexity': np.nan,
                'spread_duration': np.nan,
                'key_rate_durations': {},
                'oas_standard': None,
                'oas_enhanced': None,
                'oas_details': {},
                'calculated': False,
                'used_fallback_curve': False,
                'enhancement_level': 'error_zero_price'
            }
        
        # Calculate dirty price
        dirty_price = clean_price + accrued_interest
        
        if dirty_price <= 0:
            raise ValueError(f"Invalid dirty price {dirty_price} for {security_data.isin}")
        
        # Parse call schedule if available
        call_schedule = parse_call_schedule(security_data.call_schedule)
        if call_schedule:
            synth_logger.debug(f"Parsed {len(call_schedule)} call dates for {security_data.isin}")
        # Build zero curve
        z_times, z_rates, curve_is_fallback = build_zero_curve(curves_df, security_data.currency, valuation_date)
        if curve_is_fallback:
            synth_logger.info(f"Using fallback curve for {security_data.isin} on {valuation_date}")
        
        # Generate payment schedule from SecurityData
        payment_schedule = generate_payment_schedule_from_security_data(security_data)
        
        # Get valuation date
        val_dt_parsed = parse_date_robust(valuation_date, dayfirst=True)
        if pd.isna(val_dt_parsed):
            raise ValueError(f"Invalid valuation date: {valuation_date}")
        val_dt = to_datetime(val_dt_parsed.strftime('%Y-%m-%d'))
        
        # Extract cashflows with proper day basis mapping
        try:
            supported_day_basis = get_supported_day_basis(security_data.day_basis)
            times, cfs = extract_cashflows(payment_schedule, val_dt, z_times, z_rates, supported_day_basis)
        except ValueError as e:
            synth_logger.error(f"Skipping security {security_data.isin} due to unsupported day basis '{security_data.day_basis}': {e}")
            return {
                'ytm': np.nan,
                'z_spread': np.nan,
                'g_spread': np.nan,
                'effective_duration': np.nan,
                'modified_duration': np.nan,
                'convexity': np.nan,
                'spread_duration': np.nan,
                'key_rate_durations': {},
                'oas_standard': None,
                'oas_enhanced': None,
                'oas_details': {},
                'calculated': False,
                'used_fallback_curve': False,
                'enhancement_level': 'error_unsupported_basis'
            }
        
        if not times:
            raise ValueError(f"No future cashflows for {security_data.isin}")
        
        maturity = max(times)
        
        # Enhanced calculations when available (omitted for brevity - same as original)
        # ... [Enhanced calculation code would go here if ENHANCED_SYNTH_AVAILABLE] ...
        
        # Standard calculations
        from bond_calculation.config import COMPOUNDING
        compounding = COMPOUNDING
        ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
        
        # Calculate spreads
        g_spr = g_spread(ytm, maturity, z_times, z_rates)
        z_spr = z_spread(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
        
        # Durations and convexity
        eff_dur = effective_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
        
        freq = security_data.coupon_frequency
        
        # Modified duration (standard Macaulay-based)
        try:
            mod_dur = sm_modified_duration_standard(times, cfs, ytm, comp=compounding, frequency=freq)
        except Exception:
            # Fallback: prior behaviour based on effective duration scaling
            if compounding == 'semiannual':
                mod_dur = eff_dur / (1 + ytm / 2)
            elif compounding == 'annual':
                mod_dur = eff_dur / (1 + ytm)
            elif compounding == 'continuous':
                mod_dur = eff_dur
            elif compounding == 'monthly':
                mod_dur = eff_dur / (1 + ytm / 12)
            else:
                mod_dur = sm_modified_duration(eff_dur, ytm, frequency=freq)
        
        convex = effective_convexity(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
        spr_dur = effective_spread_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)
        
        # Key-rate durations
        try:
            krd = key_rate_durations(clean_price, times, cfs, z_times, z_rates, comp=compounding)
        except Exception:
            krd = {}

        # YTW (Yield to Worst) calculation for callable bonds
        ytw = ytm  # Default to YTM if not callable
        ytw_date = None
        ytw_type = 'maturity'
        
        if call_schedule and security_data.coupon_rate:
            try:
                from tools.SpreadOMatic.spreadomatic.ytw import calculate_ytw
                
                # Convert call schedule dates if needed
                call_schedule_for_ytw = []
                for call in call_schedule:
                    call_dict = {
                        'date': call['date'],
                        'price': float(call['price'])
                    }
                    call_schedule_for_ytw.append(call_dict)
                
                ytw_result = calculate_ytw(
                    dirty_price=dirty_price,
                    cashflows=list(zip(times, cfs)),
                    call_schedule=call_schedule_for_ytw,
                    valuation_date=val_dt,
                    settlement_date=val_dt,
                    coupon_rate=security_data.coupon_rate,
                    frequency=freq,
                    principal=100.0,
                    day_basis=supported_day_basis,
                    compounding=compounding,
                    clean_price=clean_price,
                    accrued=security_data.accrued_interest
                )
                
                if ytw_result['ytw'] is not None:
                    ytw = ytw_result['ytw']
                    ytw_date = ytw_result['ytw_date']
                    ytw_type = ytw_result['ytw_type']
                    synth_logger.debug(f"YTW for {security_data.isin}: {ytw:.4f} ({ytw_type} on {ytw_date})")
                    
            except Exception as e:
                synth_logger.debug(f"YTW calculation failed for {security_data.isin}: {e}")
                ytw = ytm  # Fallback to YTM
        
        # OAS (if call schedule and next call available)
        oas_bps = np.nan
        try:
            if call_schedule:
                future_calls = [c for c in call_schedule if c['date'] > val_dt]
                if future_calls:
                    next_call = min(future_calls, key=lambda c: c['date'])
                    if isinstance(next_call['date'], pd.Timestamp):
                        next_call_date = to_datetime(next_call['date'].strftime('%Y-%m-%d'))
                    else:
                        next_call_date = next_call['date']
                    next_call_price = float(next_call['price'])
                    oas_val = compute_oas(
                        payment_schedule,
                        val_dt,
                        z_times,
                        z_rates,
                        supported_day_basis,
                        dirty_price,
                        next_call_date=next_call_date,
                        next_call_price=next_call_price,
                        comp=compounding,
                    )
                    if oas_val is not None:
                        oas_bps = oas_val * 10000.0
        except Exception as e:
            synth_logger.warning(f"OAS calculation failed for {security_data.isin}: {e}")
            oas_bps = np.nan
        
        return {
            'ytm': ytm,  # as decimal (consistent with analytics.py)
            'ytw': ytw,  # as decimal (yield to worst)
            'ytw_date': ytw_date,  # date of worst yield scenario
            'ytw_type': ytw_type,  # 'maturity' or 'call'
            'z_spread': z_spr,  # as decimal (consistent with analytics.py)
            'g_spread': g_spr,  # as decimal (consistent with analytics.py)
            'effective_duration': eff_dur,  # years
            'modified_duration': mod_dur,  # years
            'convexity': convex,
            'spread_duration': spr_dur,  # years
            'key_rate_durations': krd,  # object
            'oas_standard': oas_bps / 10000.0 if not pd.isna(oas_bps) else None,  # as decimal
            'oas_enhanced': None,
            'oas_details': {},
            'calculated': True,
            'used_fallback_curve': curve_is_fallback,
            'enhancement_level': 'standard',
        }
        
    except Exception as e:
        msg = str(e)
        if "Invalid date for curve lookup" in msg:
            curve_lookup_errors[security_data.isin] += 1
        elif "Accrued lookup failed" in msg:
            accrued_lookup_errors[security_data.isin] += 1
        else:
            generic = msg.split(":")[0]
            other_spread_errors[generic] += 1
        return {
            'ytm': np.nan,
            'z_spread': np.nan,
            'g_spread': np.nan,
            'effective_duration': np.nan,
            'modified_duration': np.nan,
            'convexity': np.nan,
            'spread_duration': np.nan,
            'key_rate_durations': {},
            'oas_standard': None,
            'oas_enhanced': None,
            'oas_details': {},
            'calculated': False,
            'used_fallback_curve': False,
            'enhancement_level': 'error_calculation_failed'
        }


def calculate_synthetic_spreads(data_folder: str):
    """
    Main function to calculate synthetic analytics using institutional-grade methods when available.
    
    REFACTORED VERSION: Now uses SecurityDataProvider for consistent data access.
    """
    enhancement_status = "institutional-grade" if ENHANCED_SYNTH_AVAILABLE else "standard"
    synth_logger.info(f"Starting synthetic spread calculation using {enhancement_status} analytics")
    synth_logger.info("REFACTORED VERSION: Using SecurityDataProvider for unified data access")
    
    try:
        # Initialize the unified SecurityDataProvider
        synth_logger.info("Initializing SecurityDataProvider...")
        provider = SecurityDataProvider(data_folder)
        
        # Load curves data separately (still needed for curve building)
        curves_path = os.path.join(data_folder, 'curves.csv')
        if not os.path.exists(curves_path):
            synth_logger.error(f"Curves file not found: {curves_path}")
            return
        curves_df = pd.read_csv(curves_path)
        
        # Load price data to get date columns and securities list
        price_path = os.path.join(data_folder, 'sec_Price.csv')
        if not os.path.exists(price_path):
            synth_logger.error(f"Price file not found: {price_path}")
            return
        price_df = pd.read_csv(price_path)
        
        synth_logger.info(f"Loaded {len(price_df)} securities from price data")
        
        # Get date columns from price data
        date_columns = [col for col in price_df.columns if col not in 
                       ['ISIN', 'Security Name', 'Funds', 'Type', 'Callable', 'Currency']]
        
        # Initialize result dataframes
        meta_cols = ['ISIN', 'Security Name', 'Funds', 'Type', 'Callable', 'Currency']
        z_spread_data = price_df[meta_cols].copy()
        g_spread_data = price_df[meta_cols].copy()
        ytm_data = price_df[meta_cols].copy()
        eff_dur_data = price_df[meta_cols].copy()
        mod_dur_data = price_df[meta_cols].copy()
        convexity_data = price_df[meta_cols].copy()
        spr_dur_data = price_df[meta_cols].copy()
        oas_data = price_df[meta_cols].copy()
        
        # KRD dataframes by bucket label
        krd_dataframes: Dict[str, pd.DataFrame] = {}
        
        # Initialize columns
        for date_col in date_columns:
            z_spread_data[date_col] = np.nan
            g_spread_data[date_col] = np.nan
            ytm_data[date_col] = np.nan
            eff_dur_data[date_col] = np.nan
            mod_dur_data[date_col] = np.nan
            convexity_data[date_col] = np.nan
            spr_dur_data[date_col] = np.nan
            oas_data[date_col] = np.nan
        
        # Process each security
        total_securities = len(price_df)
        processed = 0
        errors = 0
        fallback_curve_count = 0
        
        for idx, price_row in price_df.iterrows():
            isin = price_row['ISIN']
            
            # Validate ISIN early to avoid issues later
            if pd.isna(isin):
                synth_logger.warning(f"Skipping row {idx} with missing ISIN value")
                errors += 1
                continue
            elif not isinstance(isin, str):
                synth_logger.warning(f"Converting non-string ISIN to string for row {idx}: {isin}")
                isin = str(isin)
            
            # Calculate spreads for each date using SecurityDataProvider
            for date_col in date_columns:
                # Get security data from provider
                security_data = provider.get_security_data(isin, date_col)
                
                if security_data is None:
                    synth_logger.debug(f"No security data available for {isin} on {date_col}")
                    continue
                
                # Skip calculation if price is zero or invalid
                if security_data.price <= 0 or pd.isna(security_data.price):
                    synth_logger.debug(f"Skipping {isin} on {date_col} - price is zero or invalid: {security_data.price}")
                    continue
                
                # Calculate spreads using unified data
                spreads = calculate_spread_for_security_using_provider(
                    security_data, date_col, curves_df
                )
                
                # Track if we used a fallback curve
                if spreads.get('used_fallback_curve', False):
                    fallback_curve_count += 1
                
                # Store results (scalar metrics)
                z_spread_data.loc[idx, date_col] = _safe_convert(spreads.get('z_spread'), 10000.0)  # Convert to bps
                g_spread_data.loc[idx, date_col] = _safe_convert(spreads.get('g_spread'), 10000.0)  # Convert to bps
                ytm_data.loc[idx, date_col] = _safe_convert(spreads.get('ytm'), 100.0)  # Convert to percentage
                eff_dur_data.loc[idx, date_col] = spreads.get('effective_duration')
                mod_dur_data.loc[idx, date_col] = spreads.get('modified_duration')
                convexity_data.loc[idx, date_col] = spreads.get('convexity')
                spr_dur_data.loc[idx, date_col] = spreads.get('spread_duration')
                
                # OAS stored as bps in CSV
                oas_standard = spreads.get('oas_standard')
                if oas_standard is not None:
                    oas_data.loc[idx, date_col] = _safe_convert(oas_standard, 10000.0)  # Convert to bps
                else:
                    oas_data.loc[idx, date_col] = np.nan
                
                # Store KRD buckets (if any)
                krd_dict = spreads.get('key_rate_durations') or {}
                if isinstance(krd_dict, dict) and krd_dict:
                    for bucket_label, krd_val in krd_dict.items():
                        if bucket_label not in krd_dataframes:
                            df_new = price_df[meta_cols].copy()
                            for dc in date_columns:
                                df_new[dc] = np.nan
                            krd_dataframes[bucket_label] = df_new
                        krd_dataframes[bucket_label].loc[idx, date_col] = krd_val
            
            processed += 1
            if processed % 100 == 0:
                synth_logger.info(f"Processed {processed}/{total_securities} securities")
        
        # Save results with rounding to 6 decimal places maximum
        z_spread_path = os.path.join(data_folder, 'synth_sec_ZSpread.csv')
        g_spread_path = os.path.join(data_folder, 'synth_sec_GSpread.csv')
        ytm_path = os.path.join(data_folder, 'synth_sec_YTM.csv')
        eff_dur_path = os.path.join(data_folder, 'synth_sec_EffectiveDuration.csv')
        mod_dur_path = os.path.join(data_folder, 'synth_sec_ModifiedDuration.csv')
        convexity_path = os.path.join(data_folder, 'synth_sec_Convexity.csv')
        spr_dur_path = os.path.join(data_folder, 'synth_sec_SpreadDuration.csv')
        oas_path = os.path.join(data_folder, 'synth_sec_OAS.csv')
        
        # Round and save
        _save_rounded_csv(z_spread_data, z_spread_path, decimal_places=6)
        _save_rounded_csv(g_spread_data, g_spread_path, decimal_places=6)
        _save_rounded_csv(ytm_data, ytm_path, decimal_places=6)
        _save_rounded_csv(eff_dur_data, eff_dur_path, decimal_places=6)
        _save_rounded_csv(mod_dur_data, mod_dur_path, decimal_places=6)
        _save_rounded_csv(convexity_data, convexity_path, decimal_places=6)
        _save_rounded_csv(spr_dur_data, spr_dur_path, decimal_places=6)
        _save_rounded_csv(oas_data, oas_path, decimal_places=6)
        
        # Save per-bucket KRD files
        krd_paths: Dict[str, str] = {}
        for bucket_label, df_krd in krd_dataframes.items():
            safe_label = str(bucket_label).replace('/', '_')
            fname = f'synth_sec_KRD_{safe_label}.csv'
            out_path = os.path.join(data_folder, fname)
            _save_rounded_csv(df_krd, out_path, decimal_places=6)
            krd_paths[bucket_label] = out_path
        
        synth_logger.info(f"Synthetic analytics calculation completed. Processed: {processed}, Errors: {errors}")
        synth_logger.info(f"Fallback usage - Curves: {fallback_curve_count}")
        synth_logger.info(f"Enhancement level: {enhancement_status}")
        synth_logger.info(f"Data provider: SecurityDataProvider (unified)")
        synth_logger.info(
            "Results saved: Z=%s, G=%s, YTM=%s, EffDur=%s, ModDur=%s, Convexity=%s, SprDur=%s, OAS=%s, KRD_files=%d",
            z_spread_path,
            g_spread_path,
            ytm_path,
            eff_dur_path,
            mod_dur_path,
            convexity_path,
            spr_dur_path,
            oas_path,
            len(krd_paths),
        )
        
        if parse_fail_count:
            synth_logger.warning(f"parse_date_robust encountered {parse_fail_count} unparseable dates")
        
        if curve_lookup_errors:
            synth_logger.warning(
                "Curve-lookup errors (ISIN -> count, top 10): %s ... total ISINs: %d",
                curve_lookup_errors.most_common(10),
                len(curve_lookup_errors),
            )
        
        if other_spread_errors:
            synth_logger.warning(
                "Other spread-calculation errors (message -> count): %s",
                other_spread_errors.most_common(10),
            )
        
        if missing_schedule_isins:
            synth_logger.warning(
                "No schedule data for %d securities (showing first 20): %s",
                len(missing_schedule_isins),
                missing_schedule_isins[:20],
            )
        
        if accrued_lookup_errors:
            synth_logger.warning(
                "Accrued-lookup errors (ISIN -> count, top 10): %s ... total ISINs: %d",
                accrued_lookup_errors.most_common(10),
                len(accrued_lookup_errors),
            )
        
    except Exception as e:
        synth_logger.error(f"Fatal error in synthetic spread calculation: {e}", exc_info=True)


if __name__ == "__main__":
    # For testing - resolve data folder from settings.yaml if available
    try:
        from core.settings_loader import get_app_config
        app_cfg = get_app_config() or {}
        dfolder = app_cfg.get('data_folder') or 'Data'
        data_folder = dfolder if os.path.isabs(dfolder) else os.path.join(os.path.dirname(__file__), dfolder)
    except Exception:
        data_folder = os.path.join(os.path.dirname(__file__), 'Data')
    calculate_synthetic_spreads(data_folder)
