"""
Yield to Worst (YTW) calculations for bonds with embedded options.

This module provides functions to calculate the yield to worst for bonds,
considering all possible redemption scenarios including maturity and call dates.
YTW is the lowest yield an investor can receive assuming the issuer exercises
options optimally from their perspective (worst case for investor).
"""

import numpy as np
from typing import List, Tuple, Dict, Optional, Any
from datetime import datetime
import logging

from .yield_spread import solve_ytm
from .daycount import year_fraction, to_datetime
try:
    from .daycount_enhanced import adjust_business_day, BusinessDayConvention, HolidayCalendar
    _BDC_AVAILABLE = True
except Exception:
    _BDC_AVAILABLE = False

logger = logging.getLogger(__name__)


def calculate_ytw(
    cashflows: List[Tuple[float, float]],
    dirty_price: float = None,
    call_schedule: Optional[List[Dict[str, Any]]] = None,
    valuation_date: Optional[datetime] = None,
    settlement_date: Optional[datetime] = None,
    coupon_rate: float = None,
    frequency: int = 2,
    principal: float = 100.0,
    day_basis: str = "ACT/ACT",
    compounding: int = 2,
    *,
    # Optional inputs to construct dirty price from file when caller doesn't supply it
    clean_price: Optional[float] = None,
    accrued: Optional[float] = None,
    isin: Optional[str] = None,
    data_folder: Optional[str] = None,
    # Business-day plumbing
    business_day_convention: str = 'NONE',
    currency: str = 'USD',
) -> Dict[str, Any]:
    """
    Calculate Yield to Worst for a bond with optional call features.
    
    Price inputs
    - Prefer passing `dirty_price` directly. If not provided, you may pass
      `clean_price` together with either `accrued` or (`isin`, `data_folder`,
      and `settlement_date`) to construct a dirty price using sec_accrued.csv.
    - The CSV path is resolved as `data_folder/sec_accrued.csv` and matched by
      exact settlement date column `YYYY-MM-DD`.
    
    Parameters
    ----------
    dirty_price : float
        Current dirty price of the bond
    cashflows : List[Tuple[float, float]]
        List of (time_in_years, cashflow_amount) tuples to maturity
    call_schedule : Optional[List[Dict[str, Any]]]
        List of call options with 'date' and 'price' keys
    valuation_date : Optional[datetime]
        Valuation date for calculations
    settlement_date : Optional[datetime]
        Settlement date (defaults to valuation_date)
    coupon_rate : float
        Annual coupon rate as decimal (e.g., 0.05 for 5%)
    frequency : int
        Coupon payment frequency per year
    principal : float
        Bond principal/face value
    day_basis : str
        Day count convention
    compounding : int
        Compounding frequency for yield calculation
        
    Optional keyword-only parameters
    clean_price: float
        Clean price used to build dirty when `dirty_price` not supplied
    accrued: float
        Accrued interest used with `clean_price` to get dirty
    isin: str
        ISIN identifier to find accrued in CSV when `accrued` not given
    data_folder: str
        Folder containing `sec_accrued.csv` for accrued lookup
    
    Returns
    -------
    Dict[str, Any]
        Dictionary containing:
        - 'ytw': Yield to worst value
        - 'ytw_date': Date corresponding to worst yield
        - 'ytw_type': 'maturity' or 'call'
        - 'all_yields': List of all calculated yields with details
    """
    
    if settlement_date is None:
        settlement_date = valuation_date
    if valuation_date is None:
        valuation_date = datetime.now()
    
    # Build dirty price if not provided
    if dirty_price is None:
        try:
            dp = None
            if clean_price is not None and accrued is not None:
                dp = float(clean_price) + float(accrued)
            elif clean_price is not None and isin and data_folder:
                # Attempt to load accrued from sec_accrued.csv (exact date match)
                import os
                import pandas as pd
                accrued_path = os.path.join(data_folder, 'sec_accrued.csv')
                if os.path.exists(accrued_path):
                    adf = pd.read_csv(accrued_path)
                    row = adf[adf['ISIN'] == isin]
                    if not row.empty:
                        target = settlement_date.strftime('%Y-%m-%d')
                        if target in adf.columns:
                            val = row.iloc[0][target]
                            if pd.notna(val) and str(val).strip().lower() not in {"n/a","na","","null","none"}:
                                dp = float(clean_price) + float(val)
            if dp is not None:
                dirty_price = dp
        except Exception:
            # Leave dirty_price as None; downstream usage will error out clearly
            pass
        
    results = {
        'ytw': None,
        'ytw_date': None,
        'ytw_type': None,
        'ytw_price': dirty_price,
        'all_yields': []
    }
    
    # Calculate yield to maturity (requires a valid dirty price)
    times = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    
    try:
        if dirty_price is None:
            raise ValueError("calculate_ytw requires dirty_price or (clean_price + accrued/CSV) to compute dirty price")
        ytm = solve_ytm(dirty_price, times, amounts, comp=compounding)
        
        # Find maturity date from cashflows (last cashflow date)
        if cashflows:
            maturity_years = max(times)
            # Approximate maturity date (this is simplified; in production you'd track actual dates)
            from datetime import timedelta
            maturity_date = settlement_date + timedelta(days=int(maturity_years * 365))
            
            results['all_yields'].append({
                'type': 'maturity',
                'date': maturity_date,
                'yield': ytm,
                'price': dirty_price
            })
            
            # Initialize with YTM as the baseline
            results['ytw'] = ytm
            results['ytw_date'] = maturity_date
            results['ytw_type'] = 'maturity'
            
    except Exception as e:
        logger.warning(f"Failed to calculate YTM: {e}")
        return results
    
    # If no call schedule, YTW is just YTM
    if not call_schedule or not coupon_rate:
        return results
    
    # Calculate yield to each call date
    for call_option in call_schedule:
        try:
            call_date = call_option.get('date')
            call_price = float(call_option.get('price', 100.0))
            
            # Convert call_date to datetime if it's a string
            if isinstance(call_date, str):
                call_date = datetime.strptime(call_date, '%Y-%m-%d')
            
            # Skip past call dates
            if call_date <= settlement_date:
                continue
                
            # Calculate time to call
            time_to_call = year_fraction(settlement_date, call_date, day_basis)
            
            # Generate cashflows to call date with BDC and currency
            call_cashflows = generate_cashflows_to_call(
                settlement_date=settlement_date,
                call_date=call_date,
                call_price=call_price,
                coupon_rate=coupon_rate,
                frequency=frequency,
                principal=principal,
                day_basis=day_basis,
                business_day_convention=business_day_convention,
                currency=currency,
            )
            
            if not call_cashflows:
                continue
                
            # Calculate yield to this call date
            call_times = [cf[0] for cf in call_cashflows]
            call_amounts = [cf[1] for cf in call_cashflows]
            
            try:
                ytc = solve_ytm(dirty_price, call_times, call_amounts, comp=compounding)
                
                results['all_yields'].append({
                    'type': 'call',
                    'date': call_date,
                    'yield': ytc,
                    'price': call_price
                })
                
                # Update YTW if this yield is worse (lower)
                if ytc < results['ytw']:
                    results['ytw'] = ytc
                    results['ytw_date'] = call_date
                    results['ytw_type'] = 'call'
                    results['ytw_price'] = call_price
                    
            except Exception as e:
                logger.debug(f"Failed to calculate yield to call date {call_date}: {e}")
                continue
                
        except Exception as e:
            logger.warning(f"Error processing call option: {e}")
            continue
    
    return results


def generate_cashflows_to_call(
    settlement_date: datetime,
    call_date: datetime,
    call_price: float,
    coupon_rate: float,
    frequency: int,
    principal: float,
    day_basis: str,
    *,
    business_day_convention: str = 'NONE',
    currency: str = 'USD',
) -> List[Tuple[float, float]]:
    """
    Generate cashflows from settlement to a specific call date.
    
    Parameters
    ----------
    settlement_date : datetime
        Settlement date
    call_date : datetime
        Call date
    call_price : float
        Call price as percentage of par
    coupon_rate : float
        Annual coupon rate as decimal
    frequency : int
        Payment frequency per year
    principal : float
        Bond principal amount
    day_basis : str
        Day count convention
        
    Returns
    -------
    List[Tuple[float, float]]
        List of (time_in_years, cashflow_amount) tuples
    """
    
    cashflows = []

    # Prepare business day convention and calendar
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
            bdc_code = (business_day_convention or 'NONE').strip().upper()
            bdc_enum = bdc_map.get(bdc_code, BusinessDayConvention.NONE)
        except Exception:
            bdc_enum = BusinessDayConvention.NONE
        try:
            cur = (currency or 'USD').upper()
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
    
    # Calculate coupon payment amount
    coupon_payment = principal * coupon_rate / frequency
    
    # Generate coupon payment dates between settlement and call
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta
    
    # Start from a coupon date before or at settlement
    # This is simplified - in production you'd use actual schedule
    months_per_period = 12 // frequency
    current_date = settlement_date
    
    # Find next coupon date (then apply BDC)
    next_coupon = current_date + relativedelta(months=months_per_period)
    next_coupon_adj = adjust_business_day(next_coupon, bdc_enum, cal) if _BDC_AVAILABLE and bdc_enum and cal else next_coupon
    
    # Generate coupons up to call date
    while next_coupon_adj <= call_date:
        time_years = year_fraction(settlement_date, next_coupon_adj, day_basis)
        cashflows.append((time_years, coupon_payment))
        next_coupon = next_coupon + relativedelta(months=months_per_period)
        next_coupon_adj = adjust_business_day(next_coupon, bdc_enum, cal) if _BDC_AVAILABLE and bdc_enum and cal else next_coupon
    
    # Add final payment at call date (principal at call price plus any accrued interest)
    # Adjust call date per BDC
    call_date_adj = adjust_business_day(call_date, bdc_enum, cal) if _BDC_AVAILABLE and bdc_enum and cal else call_date
    time_to_call = year_fraction(settlement_date, call_date_adj, day_basis)
    
    # Find the last coupon date before call and next coupon after call
    # More precise: track actual coupon dates
    last_coupon_date = None
    next_coupon_after_call = None
    
    # Find the actual last coupon before the call date
    temp_date = settlement_date
    while temp_date < call_date_adj:
        prev_date = temp_date
        temp_date = temp_date + relativedelta(months=months_per_period)
        temp_date_adj = adjust_business_day(temp_date, bdc_enum, cal) if _BDC_AVAILABLE and bdc_enum and cal else temp_date
        if temp_date_adj >= call_date_adj:
            last_coupon_date = prev_date
            next_coupon_after_call = temp_date_adj
            break
    
    # Calculate precise accrued interest
    if last_coupon_date and next_coupon_after_call:
        last_coupon_adj = adjust_business_day(last_coupon_date, bdc_enum, cal) if _BDC_AVAILABLE and bdc_enum and cal else last_coupon_date
        
        # Check if call is exactly on a coupon date
        if abs((call_date_adj - last_coupon_adj).days) < 2:  # Within 2 days considered same date
            # Call on coupon date: include full coupon
            final_payment = (call_price / 100.0) * principal + coupon_payment
        else:
            # Calculate precise accrued interest using actual day count
            days_in_period = (next_coupon_after_call - last_coupon_adj).days
            days_accrued = (call_date_adj - last_coupon_adj).days
            
            # Use precise day count fraction based on convention
            if days_in_period > 0:
                # More accurate: use year fraction directly for the accrual
                accrual_fraction = year_fraction(last_coupon_adj, call_date_adj, day_basis)
                full_period_fraction = year_fraction(last_coupon_adj, next_coupon_after_call, day_basis)
                
                if full_period_fraction > 0:
                    # Precise accrued interest calculation
                    accrued_interest = coupon_payment * (accrual_fraction / full_period_fraction)
                else:
                    accrued_interest = 0.0
            else:
                accrued_interest = 0.0
                
            final_payment = (call_price / 100.0) * principal + accrued_interest
    else:
        # Fallback: if we can't determine coupon dates, use simple calculation
        final_payment = (call_price / 100.0) * principal

    cashflows.append((time_to_call, final_payment))
    
    return cashflows


def calculate_yield_to_date(
    dirty_price: float,
    target_date: datetime,
    settlement_date: datetime,
    redemption_price: float,
    coupon_rate: float,
    frequency: int,
    principal: float,
    day_basis: str,
    compounding: int,
    *,
    business_day_convention: str = 'NONE',
    currency: str = 'USD'
) -> Optional[float]:
    """
    Calculate yield to a specific redemption date.
    
    Parameters
    ----------
    dirty_price : float
        Current dirty price
    target_date : datetime
        Target redemption date
    settlement_date : datetime
        Settlement date
    redemption_price : float
        Redemption price as percentage of par
    coupon_rate : float
        Annual coupon rate as decimal
    frequency : int
        Payment frequency
    principal : float
        Principal amount
    day_basis : str
        Day count convention
    compounding : int
        Compounding frequency
        
    Returns
    -------
    Optional[float]
        Yield to the target date, or None if calculation fails
    """
    
    # Generate cashflows to target date
    if target_date <= settlement_date:
        return None
        
    cashflows = generate_cashflows_to_call(
        settlement_date=settlement_date,
        call_date=target_date,
        call_price=redemption_price,
        coupon_rate=coupon_rate,
        frequency=frequency,
        principal=principal,
        day_basis=day_basis,
        business_day_convention=business_day_convention,
        currency=currency,
    )
    
    if not cashflows:
        return None
        
    times = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    
    try:
        return solve_ytm(dirty_price, times, amounts, comp=compounding)
    except Exception as e:
        logger.debug(f"Failed to calculate yield to date {target_date}: {e}")
        return None


def find_worst_to_call(
    dirty_price: float,
    call_schedule: List[Dict[str, Any]],
    settlement_date: datetime,
    coupon_rate: float,
    frequency: int,
    principal: float,
    day_basis: str,
    compounding: int,
    *,
    business_day_convention: str = 'NONE',
    currency: str = 'USD'
) -> Tuple[Optional[float], Optional[datetime], Optional[float]]:
    """
    Find the worst (lowest) yield among all call dates.
    
    Parameters
    ----------
    dirty_price : float
        Current dirty price
    call_schedule : List[Dict[str, Any]]
        List of call options
    settlement_date : datetime
        Settlement date
    coupon_rate : float
        Annual coupon rate
    frequency : int
        Payment frequency
    principal : float
        Principal amount
    day_basis : str
        Day count convention
    compounding : int
        Compounding frequency
        
    Returns
    -------
    Tuple[Optional[float], Optional[datetime], Optional[float]]
        (worst_yield, worst_date, call_price) or (None, None, None) if no valid calls
    """
    
    worst_yield = None
    worst_date = None
    worst_price = None
    
    for call_option in call_schedule:
        call_date = call_option.get('date')
        call_price = float(call_option.get('price', 100.0))
        
        if isinstance(call_date, str):
            call_date = datetime.strptime(call_date, '%Y-%m-%d')
            
        if call_date <= settlement_date:
            continue
            
        ytc = calculate_yield_to_date(
            dirty_price=dirty_price,
            target_date=call_date,
            settlement_date=settlement_date,
            redemption_price=call_price,
            coupon_rate=coupon_rate,
            frequency=frequency,
            principal=principal,
            day_basis=day_basis,
            compounding=compounding,
            business_day_convention=business_day_convention,
            currency=currency,
        )
        
        if ytc is not None:
            if worst_yield is None or ytc < worst_yield:
                worst_yield = ytc
                worst_date = call_date
                worst_price = call_price
    
    return worst_yield, worst_date, worst_price
