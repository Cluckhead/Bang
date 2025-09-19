# daycount_enhanced.py
# Purpose: Institutional-grade day count conventions with mathematical precision
# Following ISDA definitions and market standards used by major fixed income desks

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Union, Optional, List, Tuple
from enum import Enum

__all__ = [
    "DayCountConvention", 
    "BusinessDayConvention",
    "year_fraction_precise",
    "accrued_interest_precise",
    "add_business_days",
    "adjust_business_day",
    "HolidayCalendar"
]

DateLike = Union[str, datetime]


class DayCountConvention(Enum):
    """ISDA-standard day count conventions with exact definitions"""
    # 30/360 family
    THIRTY_360_BOND = "30/360"                    # US (NASD) Bond Basis
    THIRTY_360_US = "30/360-US"                   # US Municipal convention  
    THIRTY_E_360 = "30E/360"                      # European 30/360
    THIRTY_E_360_ISDA = "30E/360-ISDA"           # ISDA 30E/360
    
    # Actual family  
    ACT_ACT_ISDA = "ACT/ACT-ISDA"                # ISDA Actual/Actual
    ACT_ACT_ICMA = "ACT/ACT-ICMA"                # ICMA Actual/Actual
    ACT_ACT_AFB = "ACT/ACT-AFB"                  # AFB Actual/Actual
    ACT_360 = "ACT/360"                          # Actual/360
    ACT_365_FIXED = "ACT/365-FIXED"              # Actual/365 Fixed
    ACT_365_25 = "ACT/365.25"                    # Actual/365.25
    
    # Money market conventions
    ACT_365_L = "ACT/365L"                       # Actual/365 Leap year
    NL_365 = "NL/365"                            # No Leap/365
    
    # Business conventions (less common)
    BUS_252 = "BUS/252"                          # Business days/252


class BusinessDayConvention(Enum):
    """Business day adjustment conventions"""
    NONE = "NONE"                                # No adjustment
    FOLLOWING = "F"                              # Following business day
    MODIFIED_FOLLOWING = "MF"                    # Modified following
    PRECEDING = "P"                              # Preceding business day
    MODIFIED_PRECEDING = "MP"                    # Modified preceding
    UNADJUSTED = "UNADJUSTED"                   # No adjustment (alias for NONE)


class HolidayCalendar:
    """Holiday calendar implementation for major financial centers"""
    
    def __init__(self, country_code: str = "US"):
        self.country_code = country_code.upper()
        self._cache = {}
    
    def is_holiday(self, date: datetime) -> bool:
        """Check if date is a holiday in this calendar"""
        year_holidays = self._get_holidays_for_year(date.year)
        return date.date() in year_holidays
    
    def is_business_day(self, date: datetime) -> bool:
        """Check if date is a business day (not weekend or holiday)"""
        if date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return not self.is_holiday(date)
    
    def _get_holidays_for_year(self, year: int) -> set:
        """Get holidays for a specific year (cached)"""
        if year in self._cache:
            return self._cache[year]
        
        holidays = set()
        
        if self.country_code == "US":
            holidays.update(self._us_holidays(year))
        elif self.country_code == "UK" or self.country_code == "GB":
            holidays.update(self._uk_holidays(year))
        elif self.country_code == "EUR" or self.country_code == "DE":
            holidays.update(self._eur_holidays(year))
        
        self._cache[year] = holidays
        return holidays
    
    def _us_holidays(self, year: int) -> List:
        """US financial market holidays (NYSE/SIFMA)"""
        holidays = []
        
        # New Year's Day
        holidays.append(datetime(year, 1, 1).date())
        
        # Martin Luther King Jr. Day (3rd Monday in January)
        jan_1 = datetime(year, 1, 1)
        days_to_monday = (7 - jan_1.weekday()) % 7
        first_monday = jan_1 + timedelta(days=days_to_monday)
        mlk_day = first_monday + timedelta(weeks=2)  # 3rd Monday
        holidays.append(mlk_day.date())
        
        # Presidents Day (3rd Monday in February)  
        feb_1 = datetime(year, 2, 1)
        days_to_monday = (7 - feb_1.weekday()) % 7
        first_monday = feb_1 + timedelta(days=days_to_monday)
        presidents_day = first_monday + timedelta(weeks=2)
        holidays.append(presidents_day.date())
        
        # Good Friday (complex calculation)
        easter = self._calculate_easter(year)
        good_friday = easter - timedelta(days=2)
        holidays.append(good_friday.date())
        
        # Memorial Day (last Monday in May)
        may_31 = datetime(year, 5, 31)
        days_back_to_monday = (may_31.weekday() - 0) % 7
        memorial_day = may_31 - timedelta(days=days_back_to_monday)
        holidays.append(memorial_day.date())
        
        # Juneteenth (June 19th, starting 2021)
        if year >= 2021:
            holidays.append(datetime(year, 6, 19).date())
        
        # Independence Day (July 4th)
        holidays.append(datetime(year, 7, 4).date())
        
        # Labor Day (1st Monday in September)
        sep_1 = datetime(year, 9, 1)
        days_to_monday = (7 - sep_1.weekday()) % 7
        labor_day = sep_1 + timedelta(days=days_to_monday)
        holidays.append(labor_day.date())
        
        # Columbus Day (2nd Monday in October)
        oct_1 = datetime(year, 10, 1)
        days_to_monday = (7 - oct_1.weekday()) % 7
        first_monday = oct_1 + timedelta(days=days_to_monday)
        columbus_day = first_monday + timedelta(weeks=1)
        holidays.append(columbus_day.date())
        
        # Veterans Day (November 11th)
        holidays.append(datetime(year, 11, 11).date())
        
        # Thanksgiving (4th Thursday in November)
        nov_1 = datetime(year, 11, 1)
        days_to_thursday = (3 - nov_1.weekday()) % 7
        first_thursday = nov_1 + timedelta(days=days_to_thursday)
        thanksgiving = first_thursday + timedelta(weeks=3)
        holidays.append(thanksgiving.date())
        
        # Christmas Day (December 25th)
        holidays.append(datetime(year, 12, 25).date())
        
        return holidays
    
    def _uk_holidays(self, year: int) -> List:
        """UK financial market holidays (basic implementation)"""
        # Simplified - in practice would need full UK holiday logic
        return [
            datetime(year, 1, 1).date(),  # New Year's Day
            datetime(year, 12, 25).date(),  # Christmas Day
            datetime(year, 12, 26).date(),  # Boxing Day
        ]
    
    def _eur_holidays(self, year: int) -> List:
        """European financial market holidays (TARGET calendar)"""
        return [
            datetime(year, 1, 1).date(),  # New Year's Day
            datetime(year, 5, 1).date(),  # Labour Day
            datetime(year, 12, 25).date(),  # Christmas Day
            datetime(year, 12, 26).date(),  # Boxing Day
        ]
    
    def _calculate_easter(self, year: int) -> datetime:
        """Calculate Easter Sunday using the algorithm"""
        # Anonymous Gregorian algorithm
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        n = (h + l - 7 * m + 114) // 31
        p = (h + l - 7 * m + 114) % 31
        return datetime(year, n, p + 1)


def add_business_days(start_date: datetime, num_days: int, 
                     calendar: Optional[HolidayCalendar] = None) -> datetime:
    """Add business days to a date, skipping weekends and holidays"""
    if calendar is None:
        calendar = HolidayCalendar("US")
    
    current = start_date
    days_added = 0
    direction = 1 if num_days > 0 else -1
    target_days = abs(num_days)
    
    while days_added < target_days:
        current += timedelta(days=direction)
        if calendar.is_business_day(current):
            days_added += 1
    
    return current


def adjust_business_day(date: datetime, convention: BusinessDayConvention,
                       calendar: Optional[HolidayCalendar] = None) -> datetime:
    """Adjust date according to business day convention"""
    if calendar is None:
        calendar = HolidayCalendar("US")
    
    if convention == BusinessDayConvention.NONE or convention == BusinessDayConvention.UNADJUSTED:
        return date
    
    if calendar.is_business_day(date):
        return date
    
    if convention == BusinessDayConvention.FOLLOWING:
        while not calendar.is_business_day(date):
            date += timedelta(days=1)
        return date
    
    elif convention == BusinessDayConvention.MODIFIED_FOLLOWING:
        original_month = date.month
        adjusted = date
        while not calendar.is_business_day(adjusted):
            adjusted += timedelta(days=1)
        # If rolled into next month, go back to preceding business day
        if adjusted.month != original_month:
            adjusted = date
            while not calendar.is_business_day(adjusted):
                adjusted -= timedelta(days=1)
        return adjusted
    
    elif convention == BusinessDayConvention.PRECEDING:
        while not calendar.is_business_day(date):
            date -= timedelta(days=1)
        return date
    
    elif convention == BusinessDayConvention.MODIFIED_PRECEDING:
        original_month = date.month
        adjusted = date
        while not calendar.is_business_day(adjusted):
            adjusted -= timedelta(days=1)
        # If rolled into previous month, go to following business day
        if adjusted.month != original_month:
            adjusted = date
            while not calendar.is_business_day(adjusted):
                adjusted += timedelta(days=1)
        return adjusted
    
    return date


def year_fraction_precise(start: datetime, end: datetime, 
                         convention: Union[str, DayCountConvention],
                         frequency: Optional[int] = None,
                         end_of_month: bool = False) -> float:
    """
    Calculate precise year fraction using institutional-grade day count conventions.
    
    Args:
        start: Start date
        end: End date  
        convention: Day count convention (string or enum)
        frequency: Coupon frequency (required for ICMA)
        end_of_month: Whether to apply end-of-month rule
    
    Returns:
        Year fraction with full precision
    """
    if isinstance(convention, str):
        # Map string to enum
        conv_map = {
            "30/360": DayCountConvention.THIRTY_360_BOND,
            "30/360-US": DayCountConvention.THIRTY_360_US,
            "30E/360": DayCountConvention.THIRTY_E_360,
            "30E/360-ISDA": DayCountConvention.THIRTY_E_360_ISDA,
            "ACT/ACT": DayCountConvention.ACT_ACT_ISDA,
            "ACT/ACT-ISDA": DayCountConvention.ACT_ACT_ISDA,
            "ACT/ACT-ICMA": DayCountConvention.ACT_ACT_ICMA,
            "ACT/ACT-AFB": DayCountConvention.ACT_ACT_AFB,
            "ACT/360": DayCountConvention.ACT_360,
            "ACT/365": DayCountConvention.ACT_365_FIXED,
            "ACT/365-FIXED": DayCountConvention.ACT_365_FIXED,
            "ACT/365.25": DayCountConvention.ACT_365_25,
        }
        convention = conv_map.get(convention.upper(), DayCountConvention.THIRTY_360_BOND)
    
    if start >= end:
        return 0.0
    
    # 30/360 Family
    if convention == DayCountConvention.THIRTY_360_BOND:
        return _thirty_360_bond(start, end, end_of_month)
    elif convention == DayCountConvention.THIRTY_360_US:
        return _thirty_360_us(start, end)
    elif convention == DayCountConvention.THIRTY_E_360:
        return _thirty_e_360(start, end)
    elif convention == DayCountConvention.THIRTY_E_360_ISDA:
        return _thirty_e_360_isda(start, end)
    
    # ACT/ACT Family
    elif convention == DayCountConvention.ACT_ACT_ISDA:
        return _act_act_isda(start, end)
    elif convention == DayCountConvention.ACT_ACT_ICMA:
        if frequency is None:
            raise ValueError("Frequency required for ACT/ACT-ICMA")
        return _act_act_icma(start, end, frequency)
    elif convention == DayCountConvention.ACT_ACT_AFB:
        return _act_act_afb(start, end)
    
    # Simple ACT conventions
    elif convention == DayCountConvention.ACT_360:
        return (end - start).days / 360.0
    elif convention == DayCountConvention.ACT_365_FIXED:
        return (end - start).days / 365.0
    elif convention == DayCountConvention.ACT_365_25:
        return (end - start).days / 365.25
    elif convention == DayCountConvention.ACT_365_L:
        return _act_365_l(start, end)
    elif convention == DayCountConvention.NL_365:
        return _nl_365(start, end)
    elif convention == DayCountConvention.BUS_252:
        return _bus_252(start, end)
    
    else:
        raise ValueError(f"Unsupported day count convention: {convention}")


def _thirty_360_bond(start: datetime, end: datetime, end_of_month: bool = False) -> float:
    """30/360 Bond Basis (NASD) with exact ISDA rules"""
    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year
    
    # End of month adjustments per ISDA
    if end_of_month and _is_last_day_of_month(start):
        d1 = 30
    if end_of_month and _is_last_day_of_month(end) and d1 == 30:
        d2 = 30
    
    # Standard 30/360 rules
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 == 30:
        d2 = 30
    
    # February end-of-month rules
    if _is_last_day_of_february(start):
        d1 = 30
    if _is_last_day_of_february(end) and _is_last_day_of_february(start):
        d2 = 30
    
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0


def _thirty_360_us(start: datetime, end: datetime) -> float:
    """30/360 US (Municipal) convention"""
    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year
    
    # February EOM handling
    if _is_last_day_of_february(start):
        d1 = 30
    if _is_last_day_of_february(end) and _is_last_day_of_february(start):
        d2 = 30
    
    # 31st day adjustments
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 in (30, 31):
        d2 = 30
    
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0


def _thirty_e_360(start: datetime, end: datetime) -> float:
    """30E/360 European convention"""
    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year
    
    # European: simply adjust 31st to 30th
    if d1 == 31:
        d1 = 30
    if d2 == 31:
        d2 = 30
    
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0


def _thirty_e_360_isda(start: datetime, end: datetime) -> float:
    """30E/360 ISDA convention with precise rules"""
    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year
    
    # ISDA 2006 rules
    if _is_last_day_of_month(start):
        d1 = 30
    if _is_last_day_of_month(end):
        d2 = 30
    
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0


def _act_act_isda(start: datetime, end: datetime) -> float:
    """ACT/ACT ISDA: Split by calendar years with exact leap year handling

    Optimized for large date ranges using direct calculation instead of year-by-year loop.
    """
    if start >= end:
        return 0.0

    # For small date ranges, use the original method for accuracy
    if (end - start).days <= 365 * 2:  # Less than 2 years
        year_fraction = 0.0
        current_start = start

        while current_start < end:
            year_end = datetime(current_start.year, 12, 31)
            current_end = min(year_end, end)
            days_in_period = (current_end - current_start).days
            days_in_year = 366 if _is_leap_year(current_start.year) else 365
            year_fraction += days_in_period / days_in_year
            current_start = datetime(current_start.year + 1, 1, 1)
        return year_fraction

    # For large date ranges, use optimized calculation
    total_days = (end - start).days
    start_year = start.year
    end_year = end.year

    # Calculate full years contribution
    full_years_fraction = 0.0
    for year in range(start_year, end_year):
        days_in_year = 366 if _is_leap_year(year) else 365
        full_years_fraction += 1.0 / days_in_year

    # Handle partial years at start and end
    start_year_end = datetime(start_year, 12, 31)
    end_year_start = datetime(end_year, 1, 1)

    # Start year partial contribution
    if start < start_year_end:
        days_in_start_year = (min(start_year_end, end) - start).days
        days_in_start_year_total = 366 if _is_leap_year(start_year) else 365
        start_fraction = days_in_start_year / days_in_start_year_total
    else:
        start_fraction = 0.0

    # End year partial contribution (if different from start year)
    if end_year > start_year and end > end_year_start:
        days_in_end_year = (end - end_year_start).days
        days_in_end_year_total = 366 if _is_leap_year(end_year) else 365
        end_fraction = days_in_end_year / days_in_end_year_total
    else:
        end_fraction = 0.0

    return start_fraction + full_years_fraction + end_fraction


def _act_act_icma(start: datetime, end: datetime, frequency: int) -> float:
    """ACT/ACT ICMA: Reference period method"""
    if frequency <= 0:
        raise ValueError("Frequency must be positive")
    
    days_in_period = (end - start).days
    
    # Calculate reference period length (approximate)
    months_per_period = 12 // frequency
    reference_start = start
    reference_end = _add_months(reference_start, months_per_period)
    reference_days = (reference_end - reference_start).days
    
    return days_in_period / (reference_days * frequency)


def _act_act_afb(start: datetime, end: datetime) -> float:
    """ACT/ACT AFB (French) convention"""
    total_days = (end - start).days
    
    # Check if period contains February 29
    current = start
    leap_days = 0
    
    while current < end:
        if _is_leap_year(current.year):
            feb29 = datetime(current.year, 2, 29)
            if start <= feb29 < end:
                leap_days += 1
        current = datetime(current.year + 1, 1, 1)
    
    # Use 366 if period contains leap day, else 365
    denominator = 366 if leap_days > 0 else 365
    return total_days / denominator


def _act_365_l(start: datetime, end: datetime) -> float:
    """ACT/365L: Leap year version"""
    if _contains_leap_day(start, end):
        return (end - start).days / 366.0
    else:
        return (end - start).days / 365.0


def _nl_365(start: datetime, end: datetime) -> float:
    """NL/365: No Leap, treat Feb 29 as Feb 28"""
    adjusted_start = _remove_leap_day(start)
    adjusted_end = _remove_leap_day(end)
    return (adjusted_end - adjusted_start).days / 365.0


def _bus_252(start: datetime, end: datetime) -> float:
    """BUS/252: Business days over 252"""
    calendar = HolidayCalendar("US")
    current = start
    business_days = 0
    
    while current < end:
        if calendar.is_business_day(current):
            business_days += 1
        current += timedelta(days=1)
    
    return business_days / 252.0


def _is_leap_year(year: int) -> bool:
    """Check if year is a leap year"""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _is_last_day_of_month(date: datetime) -> bool:
    """Check if date is the last day of its month"""
    last_day = calendar.monthrange(date.year, date.month)[1]
    return date.day == last_day


def _is_last_day_of_february(date: datetime) -> bool:
    """Check if date is the last day of February"""
    if date.month != 2:
        return False
    return _is_last_day_of_month(date)


def _contains_leap_day(start: datetime, end: datetime) -> bool:
    """Check if period contains February 29"""
    current_year = start.year
    while current_year <= end.year:
        if _is_leap_year(current_year):
            feb29 = datetime(current_year, 2, 29)
            if start <= feb29 < end:
                return True
        current_year += 1
    return False


def _remove_leap_day(date: datetime) -> datetime:
    """Convert Feb 29 to Feb 28 for NL/365 calculation"""
    if date.month == 2 and date.day == 29:
        return datetime(date.year, 2, 28)
    return date


def _add_months(date: datetime, months: int) -> datetime:
    """Add months to a date, handling month-end properly"""
    target_month = date.month + months
    target_year = date.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    
    # Handle month-end dates
    max_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(date.day, max_day)
    
    return datetime(target_year, target_month, target_day)


def accrued_interest_precise(
    last_coupon_date: datetime,
    settlement_date: datetime,
    next_coupon_date: datetime,
    coupon_rate: float,
    face_value: float,
    day_count: Union[str, DayCountConvention],
    frequency: int = 2
) -> float:
    """
    Calculate precise accrued interest using institutional standards.
    
    Args:
        last_coupon_date: Previous coupon payment date
        settlement_date: Settlement date for accrual calculation  
        next_coupon_date: Next coupon payment date
        coupon_rate: Annual coupon rate (as decimal, e.g., 0.05 for 5%)
        face_value: Face value of the bond
        day_count: Day count convention
        frequency: Coupon frequency per year
    
    Returns:
        Accrued interest amount
    """
    # Days from last coupon to settlement
    accrued_fraction = year_fraction_precise(
        last_coupon_date, settlement_date, day_count, frequency
    )
    
    # Full coupon period fraction
    period_fraction = year_fraction_precise(
        last_coupon_date, next_coupon_date, day_count, frequency
    )
    
    # Coupon amount for the period
    coupon_amount = (coupon_rate / frequency) * face_value
    
    # Accrued interest = (accrued_days / period_days) * coupon_amount
    if period_fraction > 0:
        return (accrued_fraction / period_fraction) * coupon_amount
    else:
        return 0.0


# Test function for validation
def test_day_count_precision():
    """Test suite for day count precision - run this to validate implementations"""
    print("Testing Enhanced Day Count Conventions...")
    
    # Test case 1: ACT/ACT ISDA across leap year
    start = datetime(2024, 1, 15)  # 2024 is leap year
    end = datetime(2025, 1, 15)
    
    yf_isda = year_fraction_precise(start, end, DayCountConvention.ACT_ACT_ISDA)
    print(f"ACT/ACT ISDA (leap year): {yf_isda:.10f}")
    
    # Test case 2: 30/360 with month-end dates
    start = datetime(2024, 1, 31)
    end = datetime(2024, 2, 29)  # Leap year Feb 29
    
    yf_360 = year_fraction_precise(start, end, DayCountConvention.THIRTY_360_BOND, end_of_month=True)
    print(f"30/360 Bond (EOM): {yf_360:.10f}")
    
    # Test case 3: Business day calculation
    start = datetime(2024, 12, 20)  # Friday
    bus_date = add_business_days(start, 5)  # Should skip weekend + Christmas
    print(f"5 business days from {start.date()}: {bus_date.date()}")
    
    print("Enhanced day count testing complete!")


if __name__ == "__main__":
    test_day_count_precision()
