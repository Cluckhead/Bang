# data_loader.py
# Purpose: Load CSV-backed reference, schedule, call schedule, prices, and curves into typed models

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple, Optional

import json
import pandas as pd

from .config import DATA_DIR
from .models import BondReference, BondSchedule, CallScheduleEntry, Curve


def _parse_date_multi(value: str) -> datetime:
    """Parse a date from multiple common formats, including Excel serial dates.

    Supports dd/mm/YYYY (schedule.csv), ISO YYYY-MM-DD (reference or JSON), Excel serial dates,
    and additional separators. Raises if all formats fail.
    """
    import re
    s = str(value).strip()
    
    # Check if it's a numeric Excel serial date (like 48716)
    if re.match(r'^\d+(\.\d*)?$', s):
        try:
            serial_number = float(s)
            # Excel serial dates: 1 = January 1, 1900 (but Excel incorrectly treats 1900 as a leap year)
            # Adjust for Excel's leap year bug and convert to datetime
            if serial_number >= 60:  # After Feb 28, 1900
                serial_number -= 1  # Adjust for Excel's 1900 leap year bug
            excel_epoch = datetime(1900, 1, 1)
            return excel_epoch + timedelta(days=serial_number - 1)
        except (ValueError, OverflowError):
            pass  # Fall through to other parsing methods
    
    # Fast path: ISO date or ISO with time
    try:
        return datetime.fromisoformat(s.split("T")[0])
    except Exception:
        pass
    fmts = (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
    )
    last_err: Optional[Exception] = None  # type: ignore[name-defined]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise ValueError(f"Unable to parse date: {value}") from last_err


def _add_months(dt: datetime, months: int) -> datetime:
    """Add months to a date, clamping day to last valid day of target month."""
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    day = dt.day
    # Find last day of target month
    next_month_year = year + (1 if month == 12 else 0)
    next_month_month = 1 if month == 12 else month + 1
    first_of_next = datetime(next_month_year, next_month_month, 1)
    last_day = (first_of_next - timedelta(days=1)).day
    return dt.replace(year=year, month=month, day=min(day, last_day))


def load_bond_reference_and_schedule(isin: str) -> tuple[BondReference, BondSchedule, Optional[list[CallScheduleEntry]]]:
    ref_df = pd.read_csv(f"{DATA_DIR}/reference.csv")
    sch_df = pd.read_csv(f"{DATA_DIR}/schedule.csv")

    ref_row = ref_df[ref_df["ISIN"] == isin]
    if ref_row.empty:
        raise ValueError(f"ISIN {isin} not found in reference data")
    sch_row = sch_df[sch_df["ISIN"] == isin]

    r = ref_row.iloc[0]

    reference = BondReference(
        isin=r["ISIN"],
        security_name=r.get("Security Name", f"Synthetic_{str(isin)[-6:]}"),
        coupon_rate=float(r.get("Coupon Rate", 5.0)),
        currency=r.get("Position Currency", "USD"),
        rating=r.get("Rating"),
        sector=r.get("Sector"),
        ytm_hint=float(r["YTM"]) if "YTM" in r and pd.notna(r["YTM"]) else None,
    )

    # Build schedule – real from schedule.csv when present, else synthesize gracefully
    if not sch_row.empty:
        s = sch_row.iloc[0]
        schedule = BondSchedule(
            issue_date=_parse_date_multi(str(s["Issue Date"])),
            first_coupon=_parse_date_multi(str(s["First Coupon"])),
            maturity_date=_parse_date_multi(str(s["Maturity Date"])),
            coupon_frequency=int(s["Coupon Frequency"]),
            day_basis=str(s["Day Basis"]),
        )
    else:
        # Fallback schedule from reference (if available), otherwise synthetic 5Y semiannual ACT/ACT
        coupon_frequency = 2
        try:
            cf_raw = r.get("Coupon Frequency")
            if pd.notna(cf_raw):
                coupon_frequency = int(float(cf_raw))
        except Exception:
            coupon_frequency = 2

        day_basis = str(r.get("Day Basis", "ACT/ACT") or "ACT/ACT")

        # Prefer dates from reference if present
        issue_dt: Optional[datetime] = None
        first_coupon_dt: Optional[datetime] = None
        maturity_dt: Optional[datetime] = None
        try:
            raw = r.get("Issue Date")
            if pd.notna(raw):
                issue_dt = _parse_date_multi(str(raw))
        except Exception:
            pass
        try:
            raw = r.get("First Coupon")
            if pd.notna(raw):
                first_coupon_dt = _parse_date_multi(str(raw))
        except Exception:
            pass
        try:
            raw = r.get("Maturity Date")
            if pd.notna(raw):
                maturity_dt = _parse_date_multi(str(raw))
        except Exception:
            pass

        # Synthesize missing dates
        base = datetime.utcnow()
        if maturity_dt is None:
            maturity_dt = _add_months(base, 60)
        if issue_dt is None:
            # If maturity exists, assume 5y tenor; else 5y before base
            try:
                issue_dt = _add_months(maturity_dt, -60) if maturity_dt else _add_months(base, -60)
            except Exception:
                issue_dt = _add_months(base, -60)
        if first_coupon_dt is None:
            months = max(1, 12 // max(1, int(coupon_frequency)))
            first_coupon_dt = _add_months(issue_dt, months)

        schedule = BondSchedule(
            issue_date=issue_dt,
            first_coupon=first_coupon_dt,
            maturity_date=maturity_dt,
            coupon_frequency=int(coupon_frequency),
            day_basis=day_basis,
        )

    # Call schedule
    call_schedule: Optional[list[CallScheduleEntry]] = None
    try:
        if not sch_row.empty:
            s = sch_row.iloc[0]
            if "Call Schedule" in sch_row.columns and pd.notna(s.get("Call Schedule")):
                data = json.loads(s["Call Schedule"])  # expected list of {Date, Price}
                call_schedule = [
                    CallScheduleEntry(date=_parse_date_multi(c.get("Date") or c.get("date")),
                                      price=float(c.get("Price", c.get("price", 100.0))))
                    for c in data if isinstance(c, dict)
                ]
            elif "Call Date" in sch_row.columns and pd.notna(s.get("Call Date")):
                call_schedule = [
                    CallScheduleEntry(date=_parse_date_multi(str(s.get("Call Date"))),
                                      price=float(s.get("Call Price", 100.0)))
                ]
    except Exception:
        # Fallback for callable flag – optional
        pass

    if call_schedule is None:
        try:
            if str(r.get("Callable", "")).strip().upper().startswith("Y"):
                call_schedule = []
                maturity = schedule.maturity_date
                for years_before in [4, 3, 2, 1]:
                    dt = maturity - timedelta(days=int(365.25 * years_before))
                    if dt > datetime.utcnow():
                        call_schedule.append(CallScheduleEntry(date=dt, price=100.0 + years_before * 0.5))
        except Exception:
            # Ignore callable synthesis if reference lacks expected fields
            pass

    return reference, schedule, call_schedule


def load_price(isin: str, date_str: str) -> float:
    prices_df = pd.read_csv(f"{DATA_DIR}/sec_Price.csv")
    row = prices_df[prices_df["ISIN"] == isin]
    if row.empty:
        raise ValueError(f"ISIN {isin} not found in price data")
    if date_str not in row.columns:
        raise ValueError(f"Date {date_str} not found in price data")
    return float(row[date_str].iloc[0])


def load_curve(date: datetime, currency: str = "USD") -> Curve:
    curves_df = pd.read_csv(f"{DATA_DIR}/curves.csv")
    date_str = date.strftime("%Y-%m-%d")
    print(f"[DEBUG] Loading curve for currency={currency} on date={date_str}")
    df = curves_df[(curves_df["Date"].str.startswith(date_str)) & (curves_df["Currency Code"] == currency)].copy()
    if df.empty:
        print(f"[WARNING] No curve data found for {date_str} and {currency}, trying fallback")
        # Try without date filter as fallback
        df = curves_df[curves_df["Currency Code"] == currency].copy()
        if df.empty:
            raise ValueError(f"No curve data found for currency {currency} at all")

    term_map = {"7D": 7 / 365, "14D": 14 / 365, "1M": 1 / 12, "2M": 2 / 12, "6M": 0.5, "12M": 1.0, "24M": 2.0, "48M": 4.0, "60M": 5.0, "120M": 10.0}
    times: List[float] = []
    rates: List[float] = []
    for _, row in df.iterrows():
        if row["Term"] in term_map:
            times.append(term_map[row["Term"]])
            rates.append(float(row["Daily Value"]) / 100.0)

    if len(times) < 2:
        if len(times) == 1:
            times.append(times[0] + 1.0)
            rates.append(rates[0])
        else:
            times = [0.5, 5.0]
            rates = [0.03, 0.035]

    return Curve(times=times, rates=rates)


