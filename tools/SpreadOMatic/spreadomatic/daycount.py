# daycount.py
# Purpose: Provide day-count conventions and lightweight date utilities shared
#          across SpreadOMatic analytics modules.

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Union

__all__ = ["to_datetime", "year_fraction"]


DateLike = Union[str, datetime]


def to_datetime(date_like: DateLike) -> datetime:
    """Ensure *date_like* is a ``datetime`` instance (ISO-8601 string accepted)."""
    if isinstance(date_like, datetime):
        return date_like
    return datetime.fromisoformat(str(date_like))


# ---------------------------------------------------------------------------
# Day-count conventions
# ---------------------------------------------------------------------------


def year_fraction(start: datetime, end: datetime, basis: str = "30/360") -> float:
    """Return year fraction between *start* and *end* under *basis*.

    Supported: 30/360, 30/360-US, ACT/360, ACT/365, ACT/ACT, ACT/ACT-ISDA (alias ISDA).
    """
    basis = basis.upper()
    if basis == "30/360":
        d1, m1, y1 = start.day, start.month, start.year
        d2, m2, y2 = end.day, end.month, end.year
        d1 = min(d1, 30)
        d2 = min(d2, 30) if d1 == 30 else d2
        return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0
    elif basis in {"30/360 US", "30/360-US", "US 30/360", "30/360U"}:
        # US 30/360 convention with EOM February handling
        from calendar import monthrange
        def _is_last_day_of_feb(dt: datetime) -> bool:
            return dt.month == 2 and dt.day == monthrange(dt.year, 2)[1]
        d1, m1, y1 = start.day, start.month, start.year
        d2, m2, y2 = end.day, end.month, end.year
        if _is_last_day_of_feb(start):
            d1 = 30
        if _is_last_day_of_feb(end) and _is_last_day_of_feb(start):
            d2 = 30
        if d1 == 31:
            d1 = 30
        if d2 == 31 and d1 in (30, 31):
            d2 = 30
        return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0
    elif basis == "ACT/360":
        return (end - start).days / 360.0
    elif basis == "ACT/365":
        return (end - start).days / 365.0
    elif basis in {"ACT/ACT", "ACT"}:
        # ACT/ACT convention: actual days in period / actual days in year containing period
        if start.year == end.year:
            # Same year: use days in that year
            days_in_year = 366 if (start.year % 4 == 0 and (start.year % 100 != 0 or start.year % 400 == 0)) else 365
            return (end - start).days / days_in_year
        else:
            # Multi-year period: split by calendar years
            yf = 0.0
            temp_start = start
            while temp_start < end:
                # Calculate year end as first moment of next year (not last moment of current year)
                year_end = datetime(temp_start.year + 1, 1, 1)
                period_end = min(year_end, end)
                days_in_year = 366 if (temp_start.year % 4 == 0 and (temp_start.year % 100 != 0 or temp_start.year % 400 == 0)) else 365
                # Calculate days in this year's portion
                days_in_period = (period_end - temp_start).days
                yf += days_in_period / days_in_year
                temp_start = period_end
            return yf
    elif basis in {"ACT/ACT-ISDA", "ISDA"}:
        # Split period by calendar year per ISDA convention
        if start >= end:
            return 0.0

        def _days_in_year(year: int) -> int:
            return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365

        yf = 0.0
        temp_start = start
        while temp_start < end:
            # Calculate year end as first moment of next year
            year_end = datetime(temp_start.year + 1, 1, 1)
            period_end = min(year_end, end)
            days_in_period = (period_end - temp_start).days
            yf += days_in_period / _days_in_year(temp_start.year)
            temp_start = period_end
        return yf
    else:
        raise ValueError(f"Unsupported day-count basis: {basis}") 