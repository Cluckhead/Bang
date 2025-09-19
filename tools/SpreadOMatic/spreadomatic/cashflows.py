# cashflows.py
# Purpose: Cash-flow extraction / projection helpers, including holiday adjustments
#          and fixed-rate schedule generation.

from __future__ import annotations

import csv
from bisect import bisect_left
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Dict, Optional

from .daycount import year_fraction, to_datetime
from .interpolation import linear_interpolate, forward_rate

# Optional enhanced business-day conventions
try:
    from .daycount_enhanced import adjust_business_day as _bdc_adjust, BusinessDayConvention as _BDC, HolidayCalendar as _Cal
    _BDC_AVAILABLE = True
except Exception:
    _BDC_AVAILABLE = False

__all__ = [
    "extract_cashflows",
    "generate_fixed_schedule",
]


# ---------------------------------------------------------------------------
# Holiday calendar utils (lazy-loaded once per run)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _holiday_map(path: str = "holidays.csv") -> Dict[str, set]:
    holiday_map: Dict[str, set] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cur, iso = row.get("currency"), row.get("date")
                if cur and iso:
                    holiday_map.setdefault(cur, set()).add(to_datetime(iso).date())
    except FileNotFoundError:
        pass  # optional file
    return holiday_map


def _adjust_business_day(dt: datetime, currency: str) -> datetime:
    holidays = _holiday_map().get(currency, set())
    while dt.weekday() >= 5 or dt.date() in holidays:
        dt += timedelta(days=1)
    return dt


def _adjust_business_day_preceding(dt: datetime, currency: str) -> datetime:
    holidays = _holiday_map().get(currency, set())
    while dt.weekday() >= 5 or dt.date() in holidays:
        dt -= timedelta(days=1)
    return dt


def _get_calendar_for_currency(cur: str):
    if not _BDC_AVAILABLE:
        return None
    cur = (cur or 'USD').upper()
    country = 'US'
    if cur in {'USD'}:
        country = 'US'
    elif cur in {'EUR'}:
        country = 'EUR'
    elif cur in {'GBP'}:
        country = 'GB'
    elif cur in {'JPY'}:
        country = 'JP'
    return _Cal(country)


# ---------------------------------------------------------------------------
# Cash-flow helpers
# ---------------------------------------------------------------------------


def extract_cashflows(
    payment_schedule: List[Dict],
    valuation_date: datetime,
    zero_times: List[float],
    zero_rates: List[float],
    day_basis: str,
    *,
    last_date: Optional[datetime] = None,
) -> tuple[List[float], List[float]]:
    """Return times (years) and amounts for payments after *valuation_date*.

    If a row lacks an explicit ``amount`` the function interprets it as a
    floating-rate coupon descriptor with keys ``notional``, ``spread``,
    ``reset_date`` and optional ``basis`` and projects the cash-flow via the
    **forward rate** implied by the zero curve.
    """
    times: List[float] = []
    cfs: List[float] = []

    for item in payment_schedule:
        pay_dt = to_datetime(item["date"])
        if pay_dt <= valuation_date or (last_date and pay_dt > last_date):
            continue

        # Determine accrual basis for this item (allow per-item override)
        accr_basis = item.get("basis", day_basis)

        if "amount" in item:
            amount = float(item["amount"])
        else:
            notl = float(item.get("notional", 100.0))
            spread = float(item.get("spread", 0.0))
            reset_dt = to_datetime(item.get("reset_date", valuation_date.isoformat()))
            accr = year_fraction(reset_dt, pay_dt, accr_basis)
            t1 = year_fraction(valuation_date, reset_dt, accr_basis)
            t2 = year_fraction(valuation_date, pay_dt, accr_basis)
            fwd = forward_rate(zero_times, zero_rates, t1, t2)
            amount = notl * (fwd + spread) * accr

        times.append(year_fraction(valuation_date, pay_dt, accr_basis))
        cfs.append(amount)

    return times, cfs


# ---------------------------------------------------------------------------
# Schedule generator (fixed-rate, annual) – mirrors legacy logic
# ---------------------------------------------------------------------------


def _add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:  # Feb-29 fix
        return dt.replace(month=2, day=28, year=dt.year + years)


def _add_period(dt: datetime, frequency: int) -> datetime:
    """Add one coupon period based on frequency (1=annual, 2=semi-annual, 4=quarterly, 12=monthly)"""
    months_to_add = 12 // frequency
    
    # Calculate new month and year
    new_month = dt.month + months_to_add
    new_year = dt.year
    
    while new_month > 12:
        new_month -= 12
        new_year += 1
    
    # Try to keep the same day, but handle month-end cases
    try:
        return dt.replace(year=new_year, month=new_month)
    except ValueError:
        # Day doesn't exist in new month (e.g., Jan 31 -> Feb 31)
        # Move to last day of the month
        import calendar
        last_day = calendar.monthrange(new_year, new_month)[1]
        return dt.replace(year=new_year, month=new_month, day=last_day)


def generate_fixed_schedule(
    issue_date: datetime,
    first_coupon_date: datetime,
    maturity_date: datetime,
    coupon_rate: float,
    day_basis: str,
    currency: str,
    *,
    notional: float = 100.0,
    coupon_frequency: int = 1,  # Added frequency parameter (default annual)
    business_day_convention: str = 'NONE',
) -> List[Dict]:
    schedule: List[Dict] = []
    prev, nxt = issue_date, first_coupon_date

    # Resolve business day adjuster
    bdc_code = (business_day_convention or 'NONE').strip().upper()
    cal = _get_calendar_for_currency(currency)

    while nxt < maturity_date:
        # Apply BDC using enhanced engine if available
        if _BDC_AVAILABLE and cal is not None:
            try:
                bdc_map = {
                    'NONE': _BDC.NONE,
                    'UNADJUSTED': _BDC.UNADJUSTED,
                    'F': _BDC.FOLLOWING,
                    'MF': _BDC.MODIFIED_FOLLOWING,
                    'P': _BDC.PRECEDING,
                    'MP': _BDC.MODIFIED_PRECEDING,
                }
                bdc_enum = bdc_map.get(bdc_code, _BDC.NONE)
                pay_dt = _bdc_adjust(nxt, bdc_enum, cal)
            except Exception:
                pay_dt = _adjust_business_day(nxt, currency)
        else:
            # Fallback: simple adjustment
            if bdc_code in {'P', 'MP'}:
                pay_dt = _adjust_business_day_preceding(nxt, currency)
            elif bdc_code in {'F', 'MF'}:
                pay_dt = _adjust_business_day(nxt, currency)
            else:
                pay_dt = nxt
        
        # Check if this is a regular period
        is_regular_period = True
        if prev == issue_date:
            # First coupon might be irregular
            expected_period = 1.0 / coupon_frequency
            accr = year_fraction(prev, pay_dt, day_basis)
            if abs(accr - expected_period) > 0.01:  # Tightened to 1% tolerance for better accuracy
                is_regular_period = False
        
        if is_regular_period:
            # Regular coupon: use standard formula
            amount = notional * coupon_rate / coupon_frequency
        else:
            # Irregular period: use actual day count
            accr = year_fraction(prev, pay_dt, day_basis)
            amount = notional * coupon_rate * accr
            
        schedule.append({"date": pay_dt.isoformat(), "amount": round(amount, 6)})
        prev, nxt = nxt, _add_period(nxt, coupon_frequency)

    # Final payment (might be irregular if maturity doesn't align)
    # Final payment date with BDC
    if _BDC_AVAILABLE and cal is not None:
        try:
            bdc_map = {
                'NONE': _BDC.NONE,
                'UNADJUSTED': _BDC.UNADJUSTED,
                'F': _BDC.FOLLOWING,
                'MF': _BDC.MODIFIED_FOLLOWING,
                'P': _BDC.PRECEDING,
                'MP': _BDC.MODIFIED_PRECEDING,
            }
            bdc_enum = bdc_map.get(bdc_code, _BDC.NONE)
            pay_dt = _bdc_adjust(maturity_date, bdc_enum, cal)
        except Exception:
            pay_dt = _adjust_business_day(maturity_date, currency)
    else:
        if bdc_code in {'P', 'MP'}:
            pay_dt = _adjust_business_day_preceding(maturity_date, currency)
        elif bdc_code in {'F', 'MF'}:
            pay_dt = _adjust_business_day(maturity_date, currency)
        else:
            pay_dt = maturity_date
    
    # Check if final period is regular
    expected_period = 1.0 / coupon_frequency
    accr = year_fraction(prev, pay_dt, day_basis)
    if abs(accr - expected_period) > 0.01:  # Tightened to 1% tolerance for better accuracy
        # Irregular final period
        coupon_amount = notional * coupon_rate * accr
    else:
        # Regular final period
        coupon_amount = notional * coupon_rate / coupon_frequency
    
    schedule.append({"date": pay_dt.isoformat(), "amount": round(coupon_amount + notional, 6)})
    return schedule 
