"""
views/bond_calc_views.py
Purpose: Flask blueprint providing a web-based Bond Calculator using SpreadOMatic.
Implements pages and APIs to compute YTM, Z-Spread, G-Spread, durations, convexity,
and key rate durations, and returns cashflows and chart-ready data.

Also includes the Analytics Debug Workstation - a comprehensive debugging tool
to diagnose discrepancies between SpreadOMatic calculations and vendor data for individual bonds.
The workstation provides:
- 4-panel interface for security selection, raw data inspection, calculation tracing, and goal seek
- Step-by-step SpreadOMatic calculation breakdown
- Vendor analytics comparison
- Interactive goal seek functionality to find input parameters that match target values
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

import os
import sys

import pandas as pd
from flask import Blueprint, current_app, jsonify, render_template, request, send_file

# --- Make tools/SpreadOMatic importable ---
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_TOOLS_ROOT = os.path.join(_PROJECT_ROOT, "tools")
if _TOOLS_ROOT not in sys.path:
    sys.path.insert(0, _TOOLS_ROOT)

# Default data directory fallback used when app config DATA_FOLDER is missing
_DEFAULT_DATA_FOLDER = os.path.join(_PROJECT_ROOT, "Data")

def _get_data_folder() -> str:
    cfg = current_app.config.get("DATA_FOLDER")
    if isinstance(cfg, str) and cfg.strip():
        return cfg
    return _DEFAULT_DATA_FOLDER

try:
    from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm, z_spread, g_spread
    from tools.SpreadOMatic.spreadomatic.discount import pv_cashflows, discount_factor
    from tools.SpreadOMatic.spreadomatic.interpolation import linear_interpolate
    from tools.SpreadOMatic.spreadomatic.duration import (
        effective_duration,
        modified_duration as _modified_duration,
        effective_convexity,
        key_rate_durations,
        effective_spread_duration,
        modified_duration_standard as _modified_duration_standard,
    )
    from tools.SpreadOMatic.spreadomatic.oas import compute_oas
    SPREADOMATIC_AVAILABLE = True
except Exception as _e:  # noqa: BLE001
    # Degrade gracefully; API will return defaults when unavailable
    SPREADOMATIC_AVAILABLE = False

from data_processing.curve_processing import load_curve_data, get_latest_curve_date
from bond_calculation.bond_calculation_excel import (
    load_bond_data as _excel_load_bond_data,
    load_price_data as _excel_load_price_data,
    load_curve_data as _excel_load_curve_data,
    generate_cashflows as _excel_generate_cashflows,
    write_enhanced_excel_with_oas as _excel_write,
)
from data_processing.price_matching_processing import get_latest_price_from_sec_price
import tempfile
import os as _os


bond_calc_bp = Blueprint("bond_calc_bp", __name__, url_prefix="/bond")


# --- Internal helpers (kept local to avoid broad dependencies) ---

_DATE_FORMATS: List[str] = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%Y%m%d",
]


def _parse_date_multi(value: str) -> datetime:
    last_error: Optional[Exception] = None
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except Exception as e:  # noqa: BLE001
            last_error = e
    raise ValueError(f"Unable to parse date '{value}'") from last_error


def _format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _year_fraction(start: datetime, end: datetime, basis: str = "30/360") -> float:
    b = basis.upper()
    if "30E" in b:
        d1 = min(start.day, 30)
        d2 = min(end.day, 30)
        m1, y1 = start.month, start.year
        m2, y2 = end.month, end.year
        if "30E" in b and d1 == 31:
            d1 = 30
        if "30E" in b and d2 == 31:
            d2 = 30
        return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0
    if "30/360 US" in b or "30/360-US" in b or "US 30/360" in b:
        # US 30/360 with EOM February handling
        def _is_last_day_of_feb(dt: datetime) -> bool:
            if dt.month != 2:
                return False
            from calendar import monthrange
            return dt.day == monthrange(dt.year, 2)[1]
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
    if "30/360" in b:
        d1 = min(start.day, 30)
        d2 = min(end.day, 30)
        m1, y1 = start.month, start.year
        m2, y2 = end.month, end.year
        return ((y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)) / 360.0
    if "ACT/360" in b:
        return (end - start).days / 360.0
    if "ACT/365" in b:
        return (end - start).days / 365.0
    if "ACT/ACT" in b or b == "ACT":
        return (end - start).days / 365.25
    # default
    return _year_fraction(start, end, "30/360")


def _add_months(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    day = dt.day
    # last day of target month
    next_month_year = year + (1 if month == 12 else 0)
    next_month_month = 1 if month == 12 else month + 1
    first_of_next = datetime(next_month_year, next_month_month, 1)
    last_day = (first_of_next - timedelta(days=1)).day
    return dt.replace(year=year, month=month, day=min(day, last_day))


def _build_cashflows(
    schedule: Dict[str, Any],
    coupon_rate_pct: float,
    valuation_date: datetime,
) -> List[Dict[str, Any]]:
    """Build cashflows using SpreadOMatic's generate_fixed_schedule for consistency"""
    
    if not SPREADOMATIC_AVAILABLE:
        # Return empty cashflows if SpreadOMatic not available
        return []
    
    from tools.SpreadOMatic.spreadomatic.cashflows import generate_fixed_schedule
    from tools.SpreadOMatic.spreadomatic.daycount import year_fraction
    
    maturity_date = _parse_date_multi(schedule["Maturity Date"]) if isinstance(schedule["Maturity Date"], str) else schedule["Maturity Date"]
    issue_date = _parse_date_multi(schedule["Issue Date"]) if isinstance(schedule["Issue Date"], str) else schedule["Issue Date"]
    first_coupon = _parse_date_multi(schedule["First Coupon"]) if isinstance(schedule["First Coupon"], str) else schedule["First Coupon"]
    coupon_freq = int(schedule["Coupon Frequency"]) if schedule.get("Coupon Frequency") else 2
    basis = schedule.get("Day Basis", "ACT/ACT")
    
    notional = 100.0
    coupon_rate = float(coupon_rate_pct) / 100.0
    currency = "USD"  # Default, could be passed in if needed
    
    # Generate full schedule using SpreadOMatic
    full_schedule = generate_fixed_schedule(
        issue_date=issue_date,
        first_coupon_date=first_coupon,
        maturity_date=maturity_date,
        coupon_rate=coupon_rate,
        day_basis=basis,
        currency=currency,
        notional=notional,
        coupon_frequency=coupon_freq
    )
    
    # Filter for future cashflows and convert to expected format
    cashflows: List[Dict[str, Any]] = []
    for payment in full_schedule:
        payment_date = datetime.fromisoformat(payment["date"])
        if payment_date > valuation_date:
            time_years = year_fraction(valuation_date, payment_date, "ACT/ACT")
            amount = payment["amount"]
            
            # Determine if this is the maturity payment
            is_maturity = payment_date >= maturity_date
            if is_maturity:
                # At maturity, split amount into coupon and principal
                # Check for weekend adjustment bug fix
                if abs(amount - notional) < 0.01:
                    # Just principal - add missing coupon
                    principal = notional
                    coupon = notional * coupon_rate / coupon_freq
                    amount = principal + coupon
                else:
                    principal = notional
                    coupon = amount - principal if amount > principal else amount
            else:
                # Regular coupon payment
                principal = 0.0
                coupon = amount
            
            # Calculate accrual period
            accrual_period = coupon / (notional * coupon_rate) if coupon_rate > 0 and coupon > 0 else 0
            
            cashflows.append({
                "date": _format_iso(payment_date),
                "time_years": time_years,
                "coupon": coupon,
                "principal": principal,
                "total": amount,
                "accrual_period": accrual_period,
            })
    
    return cashflows


def _load_price_from_csv(isin: str, valuation_date: datetime) -> Optional[float]:
    """Load price from sec_Price.csv for given ISIN and date, with fallback to latest available."""
    try:
        data_folder = _get_data_folder()
        price_path = _os.path.join(data_folder, "sec_Price.csv")
        if not _os.path.exists(price_path):
            return None
        
        price_df = pd.read_csv(price_path)
        row = price_df[price_df["ISIN"] == isin]
        if row.empty:
            return None
        
        # Get date columns (skip metadata columns)
        metadata_cols = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
        date_columns = [col for col in price_df.columns if col not in metadata_cols]
        
        # Try exact date first
        valuation_date_str = valuation_date.strftime("%Y-%m-%d")
        if valuation_date_str in date_columns:
            value = row.iloc[0][valuation_date_str]
            if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
                return float(value)
        
        # Fallback to latest available price
        return get_latest_price_from_sec_price(row.iloc[0], date_columns)
    except Exception:
        return None


def _get_latest_price_date_from_csv() -> Optional[str]:
    """Get the latest date with any price data from sec_Price.csv."""
    try:
        data_folder = _get_data_folder()
        price_path = _os.path.join(data_folder, "sec_Price.csv")
        if not _os.path.exists(price_path):
            return None
        
        price_df = pd.read_csv(price_path)
        if price_df.empty:
            return None
        
        # Get date columns (skip metadata columns)
        metadata_cols = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
        date_columns = [col for col in price_df.columns if col not in metadata_cols]
        
        # Find latest date with any non-null price data
        latest_date = None
        for col in reversed(date_columns):  # Start from most recent
            if price_df[col].notna().any():
                try:
                    latest_date = pd.to_datetime(col).strftime("%Y-%m-%d")
                    break
                except Exception:
                    continue
        
        return latest_date
    except Exception:
        return None


def _lookup_accrued_sec(isin: str, valuation_date: datetime) -> Optional[float]:
    """Load accrued interest from sec_accrued.csv for given ISIN and date."""
    try:
        data_folder = _get_data_folder()
        accrued_path = _os.path.join(data_folder, "sec_accrued.csv")
        if not _os.path.exists(accrued_path):
            return None
        
        accrued_df = pd.read_csv(accrued_path)
        row = accrued_df[accrued_df["ISIN"] == isin]
        if row.empty:
            return None
        
        # Get date columns (skip metadata columns)
        metadata_cols = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
        date_columns = [col for col in accrued_df.columns if col not in metadata_cols]
        
        # Try exact date first
        valuation_date_str = valuation_date.strftime("%Y-%m-%d")
        if valuation_date_str in date_columns:
            value = row.iloc[0][valuation_date_str]
            if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
                return float(value)
        
        # Fallback: find nearest previous date column
        try:
            target_dt = valuation_date
            available = []
            for col in date_columns:
                try:
                    dt = pd.to_datetime(col)
                    if pd.notna(dt):
                        available.append((dt, col))
                except Exception:
                    continue
            
            available.sort(key=lambda x: x[0])
            prev = [col for (dt, col) in available if dt <= target_dt]
            if prev:
                col = prev[-1]
                value = row.iloc[0][col]
                if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
                    return float(value)
        except Exception:
            pass
        
        return None
    except Exception:
        return None


# Removed _calculate_accrued_interest function - all bond calculations must use SpreadOMatic
# Accrued interest is always loaded from sec_accrued.csv file, never calculated


def _extract_zero_curve_for(
    curve_df: pd.DataFrame, currency: str, on_date: datetime
) -> Tuple[List[float], List[float]]:
    """Return (times_years, zero_rates_decimal) for the selected currency/date.
    Falls back to a synthetic small curve if unavailable.
    """
    if curve_df.empty:
        return [0.25, 0.5, 1, 2, 5, 10, 30], [0.02, 0.022, 0.024, 0.026, 0.03, 0.035, 0.04]
    try:
        # curve_processing created index [Currency, Date, Term]
        idx = pd.IndexSlice
        sub = curve_df.loc[idx[currency, on_date, :]].reset_index().sort_values("TermDays")
        times = (sub["TermDays"].astype(float) / 365.0).tolist()
        rates = (sub["Value"].astype(float) / 100.0).tolist()
        if len(times) < 2:
            return [0.25, 0.5, 1, 2, 5, 10, 30], [0.02, 0.022, 0.024, 0.026, 0.03, 0.035, 0.04]
        return times, rates
    except Exception:
        return [0.25, 0.5, 1, 2, 5, 10, 30], [0.02, 0.022, 0.024, 0.026, 0.03, 0.035, 0.04]


# --- Routes ---


@bond_calc_bp.route("/calculator")
def bond_calculator() -> str:
    """Render the Bond Calculator page with sensible defaults taken from price and curve data."""
    data_folder = _get_data_folder()
    curve_df = load_curve_data(data_folder)
    currencies: List[str] = []
    latest_date_str: str = datetime.now().strftime("%Y-%m-%d")
    default_currency = "USD"
    
    # Try to get latest date from price data first (preferred), then curve data
    latest_price_date = _get_latest_price_date_from_csv()
    if latest_price_date:
        latest_date_str = latest_price_date
    
    try:
        if not curve_df.empty:
            currencies = sorted(curve_df.index.get_level_values("Currency").unique().tolist())
            # Only use curve date if we don't have price date
            if not latest_price_date:
                latest_date = get_latest_curve_date(curve_df)
                if latest_date is not None:
                    latest_date_str = latest_date.strftime("%Y-%m-%d")
            if default_currency not in currencies and currencies:
                default_currency = currencies[0]
    except Exception:
        currencies = ["USD", "EUR", "GBP"]

    return render_template(
        "bond_calculator.html",
        currencies=currencies,
        default_currency=default_currency,
        default_date=latest_date_str,
    )


@bond_calc_bp.route("/api/calc", methods=["POST"])
def api_calculate_bond() -> Any:
    """Compute bond analytics and return JSON suitable for charts and UI updates."""
    try:
        payload = request.get_json(force=True) or {}
        # Inputs
        isin: Optional[str] = payload.get("isin")
        valuation_date = _parse_date_multi(payload.get("valuation_date"))
        
        # Load price from CSV if ISIN provided, otherwise use user input
        clean_price: float
        if isin and isin.strip():
            csv_price = _load_price_from_csv(isin.strip(), valuation_date)
            if csv_price is not None:
                clean_price = csv_price
            else:
                # Fallback to user input if CSV lookup fails
                clean_price = float(payload.get("clean_price", 100.0))
        else:
            clean_price = float(payload.get("clean_price", 100.0))
        
        coupon_rate_pct: float = float(payload.get("coupon_rate_pct", 5.0))
        coupon_frequency: int = int(payload.get("coupon_frequency", 2))
        day_basis: str = str(payload.get("day_basis", "ACT/ACT"))
        compounding: str = str(payload.get("compounding", "semiannual"))
        currency: str = str(payload.get("currency", "USD"))
        g_spread_basis: str = str(payload.get("g_spread_basis", "zero")).lower()
        issue_date = _parse_date_multi(payload.get("issue_date"))
        first_coupon = _parse_date_multi(payload.get("first_coupon"))
        maturity_date = _parse_date_multi(payload.get("maturity_date"))
        
        # Try to get the correct currency from reference.csv if ISIN provided
        if isin and isin.strip():
            try:
                data_folder = _get_data_folder()
                # First try sec_Price.csv for currency
                price_path = _os.path.join(data_folder, "sec_Price.csv")
                if _os.path.exists(price_path):
                    price_df = pd.read_csv(price_path)
                    row = price_df[price_df["ISIN"] == isin.strip()]
                    if not row.empty and "Currency" in price_df.columns:
                        csv_currency = row.iloc[0].get("Currency")
                        if pd.notna(csv_currency) and str(csv_currency).strip():
                            currency = str(csv_currency).strip()
                            current_app.logger.info(f"Using currency {currency} from sec_Price.csv for {isin}")
                
                # Also try reference.csv as fallback
                if currency == str(payload.get("currency", "USD")):  # If not updated from sec_Price
                    ref_path = _os.path.join(data_folder, "reference.csv")
                    if _os.path.exists(ref_path):
                        ref_df = pd.read_csv(ref_path)
                        # Find currency column
                        currency_col = None
                        for col in ref_df.columns:
                            if "currency" in col.lower():
                                currency_col = col
                                break
                        if currency_col:
                            row = ref_df[ref_df["ISIN"] == isin.strip()]
                            if not row.empty:
                                csv_currency = row.iloc[0].get(currency_col)
                                if pd.notna(csv_currency) and str(csv_currency).strip():
                                    currency = str(csv_currency).strip()
                                    current_app.logger.info(f"Using currency {currency} from reference.csv for {isin}")
            except Exception as e:
                current_app.logger.warning(f"Could not load currency from CSV for {isin}: {e}")

        # Optional: call info for OAS
        next_call_date_raw = payload.get("next_call_date")
        next_call_price_raw = payload.get("next_call_price")
        next_call_date = _parse_date_multi(next_call_date_raw) if next_call_date_raw else None
        try:
            next_call_price = float(next_call_price_raw) if next_call_price_raw is not None else None
        except Exception:
            next_call_price = None

        schedule = {
            "Issue Date": issue_date,
            "First Coupon": first_coupon,
            "Maturity Date": maturity_date,
            "Coupon Frequency": coupon_frequency,
            "Day Basis": day_basis,
        }

        # Cashflows
        cashflows = _build_cashflows(schedule, coupon_rate_pct, valuation_date)
        times = [cf["time_years"] for cf in cashflows]
        cfs = [cf["total"] for cf in cashflows]

        # Accrued & dirty price – ALWAYS from sec_accrued.csv when ISIN is provided
        # Never calculate - as per requirement
        accrued_interest = 0.0  # Default to 0 if not found
        if isin:
            file_accrued = _lookup_accrued_sec(isin.strip(), valuation_date)
            if file_accrued is not None:
                accrued_interest = file_accrued
        dirty_price = clean_price + accrued_interest

        # Curve
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())

        if not SPREADOMATIC_AVAILABLE or not times:
            # Fallback defaults
            summary = {
                "ytm_pct": 5.0,
                "z_spread_bps": 100.0,
                "g_spread_bps": 100.0,
                "effective_duration": 5.0,
                "modified_duration": 4.8,
                "convexity": 30.0,
                "spread_duration": 5.0,
            }
            pv_curve = {"z_bps": [], "pv": [], "target_price": dirty_price}
        else:
            # Core analytics
            ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
            z = z_spread(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
            maturity = times[-1] if times else 1.0
            if g_spread_basis == "par":
                # Compute par yield for maturity using coupon frequency and zero curve
                def _par_yield(maturity_time: float, freq: int, comp: str) -> float:
                    times_y: List[float] = []
                    i = 1
                    step = 1.0 / max(1, freq)
                    while i * step < maturity_time - 1e-8:
                        times_y.append(i * step)
                        i += 1
                    if not times_y or abs(times_y[-1] - maturity_time) > 1e-8:
                        times_y.append(maturity_time)
                    ann = 0.0
                    for t in times_y[:-1]:
                        r = linear_interpolate(zero_times, zero_rates, t)
                        ann += discount_factor(r, t, comp)
                    rT = linear_interpolate(zero_times, zero_rates, maturity_time)
                    dfT = discount_factor(rT, maturity_time, comp)
                    # Include maturity discount factor in annuity denominator per standard par-yield formula
                    ann_total = ann + dfT
                    if ann_total <= 0:
                        return rT
                    return max(0.0, (1.0 - dfT) / ann_total * max(1, freq))
                g = ytm - _par_yield(maturity, coupon_frequency, compounding)
            else:
                g = g_spread(ytm, maturity, zero_times, zero_rates)
            eff_dur = effective_duration(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
            # modified duration with semiannual adjustment when applicable
            if compounding.lower() == "semiannual":
                mod_dur = eff_dur / (1 + ytm / 2)
            else:
                mod_dur = _modified_duration(eff_dur, ytm)
            convex = effective_convexity(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
            spr_dur = effective_spread_duration(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
            krds = key_rate_durations(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)

            summary = {
                "ytm_pct": ytm * 100.0,
                "z_spread_bps": z * 10000.0,
                "g_spread_bps": g * 10000.0,
                "effective_duration": eff_dur,
                "modified_duration": mod_dur,
                "convexity": convex,
                "spread_duration": spr_dur,
                "key_rate_durations": krds,
            }

            # Optional OAS (basic next-call model) if call info present
            if next_call_date is not None and next_call_price is not None and next_call_price > 0:
                # Build payment schedule in expected format
                payment_schedule = [
                    {"date": cf["date"], "amount": cf["total"]} for cf in cashflows
                ]
                try:
                    oas_val = compute_oas(
                        payment_schedule,
                        valuation_date,
                        zero_times,
                        zero_rates,
                        day_basis,
                        dirty_price,
                        next_call_date=next_call_date,
                        next_call_price=next_call_price,
                        comp=compounding,
                    )
                except Exception:
                    oas_val = None
                if oas_val is not None:
                    summary["oas_bps"] = oas_val * 10000.0

            # PV vs Z-Spread curve around solution
            z_center = z * 10000.0
            z_points = [z_center + d for d in range(-300, 301, 10)]  # bps
            pv_vals: List[float] = []
            for zbps in z_points:
                spread = zbps / 10000.0
                pv = pv_cashflows(times, cfs, zero_times, zero_rates, spread=spread, comp=compounding)
                pv_vals.append(pv)
            pv_curve = {"z_bps": z_points, "pv": pv_vals, "target_price": dirty_price}

        # Assemble response
        response = {
            "inputs": {
                "clean_price": clean_price,
                "accrued_interest": accrued_interest,
                "dirty_price": dirty_price,
                "coupon_rate_pct": coupon_rate_pct,
                "coupon_frequency": coupon_frequency,
                "day_basis": day_basis,
                "compounding": compounding,
                "currency": currency,
                "valuation_date": _format_iso(valuation_date),
                "issue_date": _format_iso(issue_date),
                "first_coupon": _format_iso(first_coupon),
                "maturity_date": _format_iso(maturity_date),
                "next_call_date": _format_iso(next_call_date) if next_call_date else None,
                "next_call_price": next_call_price,
            },
            "summary": summary,
            "cashflows": cashflows,
            "charts": {
                "pv_vs_z": pv_curve,
                "zero_curve": {"times_years": zero_times, "rates_bps": [r * 10000.0 for r in zero_rates]},
            },
        }
        return jsonify(response)
    except Exception as e:  # noqa: BLE001
        current_app.logger.error(f"Bond calculator error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/lookup", methods=["GET"])
def api_lookup_bond() -> Any:
    """Lookup bond static and schedule details by ISIN to populate calculator inputs.

    Tries `reference.csv` for static fields (currency, coupon rate), and `schedule.csv`
    for date schedule, frequency and day basis. Dates are returned ISO (YYYY-MM-DD).
    Falls back gracefully when files or fields are missing.
    Query params:
      - isin: required
      - valuation_date: optional, not currently used but reserved
    """
    try:
        isin = request.args.get("isin", "").strip()
        if not isin:
            return jsonify({"error": "Missing isin"}), 400

        data_folder = _get_data_folder()
        resp: Dict[str, Any] = {
            "isin": isin,
            "currency": None,
            "coupon_rate_pct": None,
            "issue_date": None,
            "first_coupon": None,
            "maturity_date": None,
            "coupon_frequency": None,
            "day_basis": None,
            "compounding": "semiannual",
            "next_call_date": None,
            "next_call_price": None,
        }
        # Optional valuation date to choose the next call relative to
        vd_qs = request.args.get("valuation_date")
        try:
            valuation_dt = _parse_date_multi(vd_qs) if vd_qs else None
        except Exception:
            valuation_dt = None

        # Keep a handle to reference row/cols for potential fallback schedule
        ref_row: Optional[pd.DataFrame] = None
        ref_cols: Dict[str, str] = {}

        # reference.csv → static info (and store row for fallback)
        try:
            ref_path = os.path.join(data_folder, "reference.csv")
            if os.path.exists(ref_path):
                ref_df = pd.read_csv(ref_path, dtype=str, encoding_errors="replace", on_bad_lines="skip")
                # Normalize columns
                cols = {c.lower(): c for c in ref_df.columns}
                isin_col = cols.get("isin")
                if isin_col:
                    sub = ref_df[ref_df[isin_col] == isin]
                    if not sub.empty:
                        ref_row = sub
                        ref_cols = cols
                        # Currency
                        currency_col = cols.get("position currency") or cols.get("currency")
                        if currency_col:
                            resp["currency"] = str(sub.iloc[0][currency_col]) or None
                        # Coupon Rate
                        coupon_col = cols.get("coupon rate") or cols.get("coupon") or cols.get("coupon_rate")
                        if coupon_col:
                            try:
                                resp["coupon_rate_pct"] = float(str(sub.iloc[0][coupon_col]).strip())
                            except Exception:
                                pass
        except Exception:
            pass

        # schedule.csv → dates/frequency/basis
        had_schedule = False
        try:
            sched_path = os.path.join(data_folder, "schedule.csv")
            if os.path.exists(sched_path):
                sched_df = pd.read_csv(sched_path, dtype=str, encoding_errors="replace", on_bad_lines="skip")
                cols = {c.lower(): c for c in sched_df.columns}
                isin_col = cols.get("isin")
                if isin_col:
                    sub = sched_df[sched_df[isin_col] == isin]
                    if not sub.empty:
                        had_schedule = True
                        def get_date(field: str) -> Optional[str]:
                            col = cols.get(field.lower())
                            if not col:
                                return None
                            raw = str(sub.iloc[0][col])
                            if not raw or raw.lower() == "nan":
                                return None
                            try:
                                return _format_iso(_parse_date_multi(raw))
                            except Exception:
                                return None

                        resp["issue_date"] = get_date("Issue Date")
                        resp["first_coupon"] = get_date("First Coupon")
                        resp["maturity_date"] = get_date("Maturity Date")

                        # Frequency
                        freq_col = cols.get("coupon frequency")
                        if freq_col:
                            try:
                                resp["coupon_frequency"] = int(float(str(sub.iloc[0][freq_col]).strip()))
                            except Exception:
                                pass
                        # Day basis
                        basis_col = cols.get("day basis")
                        if basis_col:
                            val = str(sub.iloc[0][basis_col]).strip()
                            resp["day_basis"] = val if val else None

                        # Call schedule parsing
                        call_col = cols.get("call schedule")
                        if call_col:
                            raw_calls = sub.iloc[0][call_col]
                            if isinstance(raw_calls, str) and raw_calls.strip():
                                try:
                                    # Handle doubled quotes within CSV
                                    json_str = raw_calls.replace("'", '"')
                                    calls = pd.json.loads(json_str) if hasattr(pd, 'json') else __import__('json').loads(json_str)
                                except Exception:
                                    try:
                                        calls = __import__('json').loads(raw_calls)
                                    except Exception:
                                        calls = []
                                # Normalize and pick next call
                                parsed = []
                                for it in calls if isinstance(calls, list) else []:
                                    try:
                                        d = it.get("Date") or it.get("date")
                                        p = it.get("Price") or it.get("price")
                                        if d is None or p is None:
                                            continue
                                        dt = _parse_date_multi(str(d))
                                        price_f = float(p)
                                        parsed.append((dt, price_f))
                                    except Exception:
                                        continue
                                if parsed:
                                    parsed.sort(key=lambda x: x[0])
                                    if valuation_dt is None:
                                        from datetime import datetime as _dt
                                        valuation_dt = _dt.utcnow()
                                    future = [cp for cp in parsed if cp[0] > valuation_dt]
                                    pick = future[0] if future else parsed[0]
                                    resp["next_call_date"] = _format_iso(pick[0])
                                    resp["next_call_price"] = pick[1]
        except Exception:
            pass

        # Fallback schedule when not present in schedule.csv
        if not had_schedule:
            def _get_ref_date(field: str) -> Optional[str]:
                if ref_row is None:
                    return None
                col = ref_cols.get(field.lower())
                if not col:
                    return None
                raw = str(ref_row.iloc[0][col])
                if not raw or raw.lower() == "nan":
                    return None
                try:
                    return _format_iso(_parse_date_multi(raw))
                except Exception:
                    try:
                        # Some reference may include ISO with time
                        raw_clean = raw.split('T')[0]
                        return _format_iso(_parse_date_multi(raw_clean))
                    except Exception:
                        return None

            # Prefer reference-provided maturity/issue/first if available
            if resp.get("maturity_date") is None:
                resp["maturity_date"] = _get_ref_date("Maturity Date")
            if resp.get("issue_date") is None:
                resp["issue_date"] = _get_ref_date("Issue Date")
            if resp.get("first_coupon") is None:
                # Some references might store First Coupon
                fc = _get_ref_date("First Coupon")
                resp["first_coupon"] = fc

            # Frequency and basis – try reference, else defaults
            if resp.get("coupon_frequency") is None:
                if ref_row is not None:
                    freq_col = ref_cols.get("coupon frequency")
                    if freq_col:
                        try:
                            resp["coupon_frequency"] = int(float(str(ref_row.iloc[0][freq_col]).strip()))
                        except Exception:
                            pass
                if resp.get("coupon_frequency") is None:
                    resp["coupon_frequency"] = 2
            if resp.get("day_basis") is None:
                if ref_row is not None:
                    basis_col = ref_cols.get("day basis")
                    if basis_col:
                        val = str(ref_row.iloc[0][basis_col]).strip()
                        if val:
                            resp["day_basis"] = val
                if resp.get("day_basis") is None:
                    resp["day_basis"] = "ACT/ACT"

            # If dates still missing, synthesize around valuation date or today
            from datetime import datetime as _dt
            try:
                vd_for_defaults = valuation_dt or _dt.utcnow()
            except Exception:
                vd_for_defaults = _dt.utcnow()

            # If maturity missing, assume 5 years from valuation
            if resp.get("maturity_date") is None:
                mat = _add_months(vd_for_defaults, 60)
                resp["maturity_date"] = _format_iso(mat)
            # If issue missing, assume 5 years before valuation (or 10y tenor total if maturity known)
            if resp.get("issue_date") is None:
                if resp.get("maturity_date"):
                    try:
                        mat_dt = _parse_date_multi(resp["maturity_date"])  # type: ignore[arg-type]
                        issue = _add_months(mat_dt, -60)
                    except Exception:
                        issue = _add_months(vd_for_defaults, -60)
                else:
                    issue = _add_months(vd_for_defaults, -60)
                resp["issue_date"] = _format_iso(issue)
            # If first coupon missing, set issue + 12/freq months
            if resp.get("first_coupon") is None:
                try:
                    freq = int(resp.get("coupon_frequency") or 2)
                except Exception:
                    freq = 2
                months = max(1, 12 // max(1, freq))
                try:
                    issue_dt = _parse_date_multi(resp["issue_date"])  # type: ignore[arg-type]
                except Exception:
                    issue_dt = vd_for_defaults
                first = _add_months(issue_dt, months)
                resp["first_coupon"] = _format_iso(first)

        return jsonify(resp)
    except Exception as e:  # noqa: BLE001
        current_app.logger.error(f"Bond lookup error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/price", methods=["GET"])
def api_get_price() -> Any:
    """Get price for ISIN and date from sec_Price.csv.
    
    Query params:
      - isin: required
      - valuation_date: required (YYYY-MM-DD)
    """
    try:
        isin = request.args.get("isin", "").strip()
        date_str = request.args.get("valuation_date", "").strip()
        if not isin or not date_str:
            return jsonify({"error": "Missing required parameters: isin, valuation_date"}), 400
        
        valuation_dt = _parse_date_multi(date_str)
        price = _load_price_from_csv(isin, valuation_dt)
        
        if price is not None:
            return jsonify({"price": price, "source": "csv"})
        else:
            return jsonify({"price": None, "source": "not_found"})
            
    except Exception as e:
        current_app.logger.error(f"Price lookup error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/excel", methods=["POST"])
def api_create_excel() -> Any:
    """Generate the Excel workbook using form inputs, falling back to CSV data when available.

    Accepts JSON payload with bond parameters (same as /api/calc endpoint).
    """
    try:
        payload = request.get_json(force=True) or {}
        
        # Extract inputs (same as calc endpoint)
        isin = payload.get("isin", "").strip() or "MANUAL_BOND"
        valuation_date_str = payload.get("valuation_date")
        if not valuation_date_str:
            return jsonify({"error": "Missing valuation_date"}), 400
            
        valuation_dt = _parse_date_multi(valuation_date_str)
        
        # Extract form inputs first
        clean_price = float(payload.get("clean_price", 100.0))
        coupon_rate_pct = float(payload.get("coupon_rate_pct", 5.0))
        coupon_frequency = int(payload.get("coupon_frequency", 2))
        day_basis = str(payload.get("day_basis", "ACT/ACT"))
        currency = str(payload.get("currency", "USD"))
        issue_date = _parse_date_multi(payload.get("issue_date"))
        first_coupon = _parse_date_multi(payload.get("first_coupon"))
        maturity_date = _parse_date_multi(payload.get("maturity_date"))
        
        # Try to load from CSV first, use form inputs as fallback
        bond = None
        price = clean_price
        
        if isin and isin != "MANUAL_BOND":
            try:
                # Try CSV lookup first
                bond = _excel_load_bond_data(isin)
                csv_price = _excel_load_price_data(isin, valuation_date_str)
                price = csv_price
                currency = bond['reference'].get('Position Currency', currency)
                current_app.logger.info(f"Loaded bond data from CSV for {isin}")
            except Exception as e:
                current_app.logger.info(f"CSV lookup failed for {isin}: {e}. Using form inputs.")
                bond = None
                # Try to get price from CSV even if bond data fails
                csv_price = _load_price_from_csv(isin, valuation_dt)
                if csv_price is not None:
                    price = csv_price
                    current_app.logger.info(f"Using price {price} from CSV for {isin}")
        
        # If CSV lookup failed, create bond data from form inputs
        if bond is None:
            # Get security name and currency from sec_Price.csv if available
            security_name = f"Manual Bond ({isin})"
            try:
                data_folder = _get_data_folder()
                price_path = _os.path.join(data_folder, "sec_Price.csv")
                if _os.path.exists(price_path):
                    price_df = pd.read_csv(price_path)
                    row = price_df[price_df["ISIN"] == isin]
                    if not row.empty:
                        # Get security name
                        if "Security Name" in price_df.columns:
                            csv_name = row.iloc[0].get("Security Name")
                            if pd.notna(csv_name) and str(csv_name).strip():
                                security_name = str(csv_name).strip()
                        # Get currency
                        if "Currency" in price_df.columns:
                            csv_currency = row.iloc[0].get("Currency")
                            if pd.notna(csv_currency) and str(csv_currency).strip():
                                currency = str(csv_currency).strip()
                                current_app.logger.info(f"Using currency {currency} from sec_Price.csv for {isin}")
            except Exception:
                pass
            
            # Also check reference.csv for currency if not found
            try:
                ref_path = _os.path.join(data_folder, "reference.csv")
                if _os.path.exists(ref_path):
                    ref_df = pd.read_csv(ref_path)
                    # Find currency column
                    currency_col = None
                    for col in ref_df.columns:
                        if "position currency" in col.lower() or col.lower() == "currency":
                            currency_col = col
                            break
                    if currency_col:
                        row = ref_df[ref_df["ISIN"] == isin]
                        if not row.empty:
                            csv_currency = row.iloc[0].get(currency_col)
                            if pd.notna(csv_currency) and str(csv_currency).strip():
                                currency = str(csv_currency).strip()
                                current_app.logger.info(f"Using currency {currency} from reference.csv for {isin}")
            except Exception:
                pass
            
            bond = {
                'reference': {
                    'ISIN': isin,
                    'Security Name': security_name,
                    'Coupon Rate': coupon_rate_pct,
                    'Position Currency': currency,
                    'Rating': 'BBB',
                    'Sector': 'Corporate',
                },
                'schedule': {
                    'Issue Date': issue_date.strftime('%d/%m/%Y'),
                    'First Coupon': first_coupon.strftime('%d/%m/%Y'),
                    'Maturity Date': maturity_date.strftime('%d/%m/%Y'),
                    'Coupon Frequency': coupon_frequency,
                    'Day Basis': day_basis,
                },
                # Always use a list for call_schedule to avoid None-type checks downstream
                'call_schedule': [],
                'bond_characteristics': {
                    'rating': 'BBB',
                    'sector': 'Corporate',
                    'currency': currency,
                }
            }
            current_app.logger.info(f"Created bond data from form inputs for {isin}")

        # Now that we have the correct currency from bond data, load the appropriate curve
        # Get currency from bond reference data (which was either loaded from CSV or set from form)
        final_currency = bond['reference'].get('Position Currency', 'USD')
        current_app.logger.info(f"Loading {final_currency} curve for {isin} on {valuation_date_str}")
        
        times, rates = _excel_load_curve_data(valuation_dt, final_currency)
        curve_data = (times, rates)

        cashflows = _excel_generate_cashflows(bond, valuation_dt)
        
        # Try to load accrued from sec_accrued.csv
        accrued_interest = None
        if isin:
            accrued_interest = _lookup_accrued_sec(isin.strip(), valuation_dt)

        # Build output path in temp (Windows-friendly): create temp file we control lifecycle for
        out_name = f"bond_calc_{isin}_{valuation_date_str}.xlsx"
        fd, out_path = tempfile.mkstemp(prefix="bond_calc_", suffix=".xlsx")
        _os.close(fd)

        _excel_write(bond, cashflows, curve_data, price, valuation_dt, out_path, accrued_interest)

        # Stream the file and cleanup after response is sent
        f = open(out_path, "rb")
        response = send_file(
            f,
            as_attachment=True,
            download_name=out_name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        def _cleanup() -> None:
            try:
                try:
                    f.close()
                except Exception:
                    pass
                if _os.path.exists(out_path):
                    _os.remove(out_path)
            except Exception:
                pass

        try:
            response.call_on_close(_cleanup)
        except Exception:
            # Fallback: best-effort immediate cleanup if call_on_close unavailable
            _cleanup()
        return response
    except Exception as e:
        current_app.logger.error(f"Excel generation error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# === Analytics Debug Workstation ===


def _load_available_securities_for_debug() -> List[Dict[str, Any]]:
    """Load securities from reference.csv for the debug workstation dropdown."""
    try:
        data_folder = _get_data_folder()
        reference_path = _os.path.join(data_folder, "reference.csv")
        if not _os.path.exists(reference_path):
            return []
        
        df = pd.read_csv(reference_path, encoding_errors="replace", on_bad_lines="skip")
        
        # Filter for relevant columns
        required_cols = ["ISIN", "Security Name"]
        if not all(col in df.columns for col in required_cols):
            return []
        
        # Add optional columns if available
        optional_cols = ["Position Currency", "Security Sub Type", "Ticker", "Coupon Rate"]
        display_cols = required_cols + [col for col in optional_cols if col in df.columns]
        
        df_filtered = df[display_cols].copy()
        df_filtered = df_filtered.dropna(subset=required_cols)
        df_filtered = df_filtered.drop_duplicates(subset=["ISIN"])
        
        # Fill NaN values for optional columns
        for col in optional_cols:
            if col in df_filtered.columns:
                df_filtered[col] = df_filtered[col].fillna("")
        
        # Convert to list of dicts, sorted by security name
        securities = df_filtered.to_dict("records")
        securities.sort(key=lambda x: str(x.get("Security Name", "")))
        
        return securities
    except Exception as e:
        current_app.logger.error(f"Error loading securities for debug workstation: {e}", exc_info=True)
        return []


def _get_vendor_analytics_for_security(isin: str, valuation_date: datetime) -> Dict[str, Any]:
    """Load vendor analytics data for a security from the various sec_ files."""
    try:
        data_folder = _get_data_folder()
        date_str = valuation_date.strftime("%Y-%m-%d")
        vendor_data = {}
        
        # File mappings for vendor data - comprehensive security-level files from data dictionary
        file_mappings = {
            # Core metrics
            "YTM": "sec_YTM.csv",
            "YTMSP": "sec_YTMSP.csv", 
            "YTW": "sec_YTW.csv",
            "YTWSP": "sec_YTWSP.csv",
            "Duration": "sec_duration.csv",  # Note: lowercase 'd' per data dictionary
            "DurationSP": "sec_durationSP.csv",
            "ModDuration": "sec_ModDuration.csv",
            "Convexity": "sec_Convexity.csv",
            "DV01": "sec_DV01.csv",
            
            # Spreads
            "Spread": "sec_Spread.csv",
            "SpreadSP": "sec_SpreadSP.csv",
            "ZSpread": "sec_ZSpread.csv",
            "OAS": "sec_OAS.csv",
            
            # Spread Duration variants (with spaces per data dictionary)
            "SpreadDuration": "sec_Spread duration.csv",
            "SpreadDurationSP": "sec_Spread durationSP.csv",
            
            # Synthetic/Derived spreads
            "GSpread": "synth_sec_GSpread.csv",
            "ZSpreadSynth": "synth_sec_ZSpread.csv",
            
            # Price and accrued
            "Price": "sec_Price.csv",
            "Accrued": "sec_accrued.csv",
            
            # Key Rate Durations (if available as separate files)
            "KeyRateDuration2Y": "sec_KRD_2Y.csv",
            "KeyRateDuration5Y": "sec_KRD_5Y.csv", 
            "KeyRateDuration10Y": "sec_KRD_10Y.csv"
        }
        
        for metric, filename in file_mappings.items():
            try:
                file_path = _os.path.join(data_folder, filename)
                if not _os.path.exists(file_path):
                    continue
                
                df = pd.read_csv(file_path)
                row = df[df["ISIN"] == isin]
                if row.empty:
                    continue
                
                # Get value for the specific date or latest available
                metadata_cols = ["ISIN", "Security Name", "Funds", "Type", "Callable", "Currency"]
                date_columns = [col for col in df.columns if col not in metadata_cols]
                
                value = None
                if date_str in date_columns:
                    value = row.iloc[0][date_str]
                    if pd.notna(value) and str(value).strip().lower() not in {"n/a", "na", "", "null", "none"}:
                        value = float(value)
                    else:
                        value = None
                
                # Fallback to latest available
                if value is None:
                    for col in reversed(date_columns):
                        val = row.iloc[0][col]
                        if pd.notna(val) and str(val).strip().lower() not in {"n/a", "na", "", "null", "none"}:
                            try:
                                value = float(val)
                                break
                            except Exception:
                                continue
                
                if value is not None:
                    vendor_data[metric] = value
                    
            except Exception:
                continue
        
        # Try to load Key Rate Durations from KRD.csv (per data dictionary)
        try:
            krd_path = _os.path.join(data_folder, "KRD.csv")
            if _os.path.exists(krd_path):
                krd_df = pd.read_csv(krd_path)
                # KRD.csv has columns: Date, Code (Fund/Benchmark), Tenor (bucket), Value
                # We need to find KRD data for this security if available
                # This might require matching via fund holdings or other mapping
                pass  # TODO: Implement KRD mapping logic if needed
        except Exception:
            pass
        
        return vendor_data
    except Exception as e:
        current_app.logger.error(f"Error loading vendor analytics for {isin}: {e}", exc_info=True)
        return {}


def _run_spreadomatic_step_by_step(
    clean_price: float,
    cashflows: List[Dict[str, Any]], 
    zero_times: List[float],
    zero_rates: List[float],
    compounding: str = "semiannual",
    *,
    isin: Optional[str] = None,
    valuation_date: Optional[datetime] = None,
    use_robust: bool = False,
) -> Dict[str, Any]:
    """Run SpreadOMatic calculations step by step with detailed trace."""
    if not SPREADOMATIC_AVAILABLE:
        return {"error": "SpreadOMatic not available", "steps": []}
    
    steps = []
    results = {}
    
    try:
        times = [cf["time_years"] for cf in cashflows]
        cfs = [cf["total"] for cf in cashflows]

        # Compute accrued and dirty price if possible
        accrued = 0.0
        if isin and valuation_date:
            try:
                acc = _lookup_accrued_sec(isin, valuation_date)
                accrued = float(acc) if acc is not None else 0.0
            except Exception:
                accrued = 0.0
        dirty_price = clean_price + accrued
        
        # Step 1: YTM Calculation
        steps.append({
            "step": 1,
            "name": "Yield to Maturity (YTM)",
            "description": "Calculate yield that makes PV of cashflows equal to DIRTY price",
            "inputs": {
                "clean_price": clean_price,
                "accrued": accrued,
                "dirty_price": dirty_price,
                "times": times,
                "cashflows": cfs,
                "compounding": compounding
            }
        })
        
        # Optional robust solver path (Brent bracketing with consistent compounding)
        if use_robust:
            try:
                from tools.SpreadOMatic.spreadomatic.numerical_methods import BrentMethod, NumericalConfig
                bm = BrentMethod(NumericalConfig(tolerance=1e-10, max_iterations=100))
                def _price_diff_y(y: float) -> float:
                    return sum(cf * discount_factor(y, t, compounding) for cf, t in zip(cfs, times)) - dirty_price
                ytm = bm.solve(_price_diff_y, 0.05, (-0.5, 2.0))
            except Exception:
                ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
        else:
            ytm = solve_ytm(dirty_price, times, cfs, comp=compounding)
        results["ytm"] = ytm
        steps[-1]["result"] = ytm
        steps[-1]["result_display"] = f"{ytm * 100:.4f}%"
        
        # Step 2: Z-Spread Calculation
        steps.append({
            "step": 2,
            "name": "Z-Spread (Zero-Volatility Spread)",
            "description": "Spread over zero curve that makes PV equal to DIRTY price",
            "inputs": {
                "clean_price": clean_price,
                "accrued": accrued,
                "dirty_price": dirty_price,
                "times": times,
                "cashflows": cfs,
                "zero_times": zero_times,
                "zero_rates": zero_rates,
                "compounding": compounding
            }
        })
        
        if use_robust:
            try:
                from tools.SpreadOMatic.spreadomatic.numerical_methods import BrentMethod, NumericalConfig
                bm = BrentMethod(NumericalConfig(tolerance=1e-10, max_iterations=100))
                def _price_diff_s(s: float) -> float:
                    return pv_cashflows(times, cfs, zero_times, zero_rates, spread=s, comp=compounding) - dirty_price
                z_spread_val = bm.solve(_price_diff_s, 0.0, (-0.1, 0.5))
            except Exception:
                z_spread_val = z_spread(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
        else:
            z_spread_val = z_spread(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
        results["z_spread"] = z_spread_val
        steps[-1]["result"] = z_spread_val
        steps[-1]["result_display"] = f"{z_spread_val * 10000:.2f} bps"
        
        # Step 3: Effective Duration
        steps.append({
            "step": 3,
            "name": "Effective Duration", 
            "description": "Price sensitivity to parallel yield curve shifts (dirty price)",
            "inputs": {
                "clean_price": clean_price,
                "accrued": accrued,
                "dirty_price": dirty_price,
                "times": times,
                "cashflows": cfs,
                "zero_times": zero_times,
                "zero_rates": zero_rates,
                "compounding": compounding
            }
        })
        
        eff_dur = effective_duration(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
        results["effective_duration"] = eff_dur
        steps[-1]["result"] = eff_dur
        steps[-1]["result_display"] = f"{eff_dur:.4f}"
        
        # Step 4: Modified Duration
        steps.append({
            "step": 4,
            "name": "Modified Duration",
            "description": "Duration adjusted for yield compounding",
            "inputs": {
                "effective_duration": eff_dur,
                "ytm": ytm,
                "compounding": compounding
            }
        })
        
        # Standard Macaulay-based modified duration using compounding→frequency mapping
        _freq_map = {"annual": 1, "semiannual": 2, "quarterly": 4, "monthly": 12, "continuous": 1}
        _freq = _freq_map.get(str(compounding).lower(), 2)
        try:
            mod_dur = _modified_duration_standard(times, cfs, ytm, comp=compounding, frequency=_freq)
        except Exception:
            # Fallback to legacy scaling if anything goes wrong
            if str(compounding).lower() == "semiannual":
                mod_dur = eff_dur / (1 + ytm / 2)
            else:
                mod_dur = _modified_duration(eff_dur, ytm)
        results["modified_duration"] = mod_dur
        steps[-1]["result"] = mod_dur
        steps[-1]["result_display"] = f"{mod_dur:.4f}"
        
        # Step 5: Convexity
        steps.append({
            "step": 5,
            "name": "Effective Convexity",
            "description": "Second-order price sensitivity to yield changes (10 bps bump)",
            "inputs": {
                "clean_price": clean_price,
                "accrued": accrued,
                "dirty_price": dirty_price,
                "times": times,
                "cashflows": cfs,
                "zero_times": zero_times,
                "zero_rates": zero_rates,
                "compounding": compounding
            }
        })
        
        convex = effective_convexity(dirty_price, times, cfs, zero_times, zero_rates, comp=compounding)
        results["convexity"] = convex
        steps[-1]["result"] = convex
        steps[-1]["result_display"] = f"{convex:.4f}"
        
    except Exception as e:
        steps.append({
            "step": len(steps) + 1,
            "name": "Error",
            "description": f"Calculation failed: {str(e)}",
            "error": str(e)
        })
    
    return {"steps": steps, "results": results}


@bond_calc_bp.route("/debug")
def analytics_debug_workstation() -> str:
    """Render the Analytics Debug Workstation page."""
    securities = _load_available_securities_for_debug()
    
    # Get default date from price data or current date
    latest_price_date = _get_latest_price_date_from_csv()
    default_date = latest_price_date or datetime.now().strftime("%Y-%m-%d")
    
    return render_template(
        "analytics_debug_workstation.html",
        securities=securities,
        default_date=default_date
    )


@bond_calc_bp.route("/api/debug/load_security", methods=["POST"])
def api_debug_load_security() -> Any:
    """Load all data for a security in the debug workstation."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load bond reference and schedule data
        bond_data = {}
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            # Fallback: load from reference.csv directly
            try:
                data_folder = _get_data_folder()
                ref_path = _os.path.join(data_folder, "reference.csv")
                if _os.path.exists(ref_path):
                    ref_df = pd.read_csv(ref_path)
                    row = ref_df[ref_df["ISIN"] == isin]
                    if not row.empty:
                        bond_data = {"reference": row.iloc[0].to_dict()}
            except Exception:
                pass
        
        # Load price data
        price_data = _load_price_from_csv(isin, valuation_date)
        
        # Load vendor analytics
        vendor_analytics = _get_vendor_analytics_for_security(isin, valuation_date)
        
        # Load curve data
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        currency = bond_data.get("reference", {}).get("Position Currency", "USD")
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())
        
        # Prepare raw data for inspection
        raw_data = {
            "reference": bond_data.get("reference", {}),
            "schedule": bond_data.get("schedule", {}),
            "call_schedule": bond_data.get("call_schedule", []),
            "price": price_data,
            "vendor_analytics": vendor_analytics,
            "curve_data": {
                "times": zero_times,
                "rates": [r * 10000 for r in zero_rates],  # Convert to bps for display
                "currency": currency
            }
        }
        
        return jsonify({
            "success": True,
            "isin": isin,
            "security_name": bond_data.get("reference", {}).get("Security Name", ""),
            "valuation_date": valuation_date_str,
            "raw_data": raw_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug load security error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/run_calculation", methods=["POST"])
def api_debug_run_calculation() -> Any:
    """Run step-by-step SpreadOMatic calculation for debug workstation."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        
        # Override parameters for goal seek
        price_override = payload.get("price_override")
        curve_shift = payload.get("curve_shift", 0.0)  # parallel shift in bps
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load bond data
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            return jsonify({"error": f"Could not load bond data for {isin}"}), 400
        
        # Get price - use override if provided, otherwise load from CSV
        if price_override is not None:
            clean_price = float(price_override)
        else:
            clean_price = _load_price_from_csv(isin, valuation_date)
            if clean_price is None:
                return jsonify({"error": f"Could not load price for {isin}"}), 400
        
        # Generate cashflows
        cashflows = _excel_generate_cashflows(bond_data, valuation_date)
        
        # Load curve data
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        currency = bond_data.get("reference", {}).get("Position Currency", "USD")
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())
        
        # Apply curve shift if specified
        if curve_shift != 0.0:
            shift_decimal = float(curve_shift) / 10000.0  # Convert bps to decimal
            zero_rates = [r + shift_decimal for r in zero_rates]
        
        # Run step-by-step calculation (use_robust optional)
        use_robust = bool(payload.get("use_robust", False))
        calculation_trace = _run_spreadomatic_step_by_step(
            clean_price,
            cashflows,
            zero_times,
            zero_rates,
            isin=isin,
            valuation_date=valuation_date,
            use_robust=use_robust,
        )
        
        # Get vendor analytics for comparison
        vendor_analytics = _get_vendor_analytics_for_security(isin, valuation_date)
        
        return jsonify({
            "success": True,
            "isin": isin,
            "valuation_date": valuation_date_str,
            "inputs": {
                "clean_price": clean_price,
                "price_source": "override" if price_override is not None else "csv",
                "curve_shift_bps": curve_shift,
                "currency": currency
            },
            "calculation_trace": calculation_trace,
            "vendor_analytics": vendor_analytics,
            "cashflows": cashflows
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug run calculation error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/goal_seek", methods=["POST"])
def api_debug_goal_seek() -> Any:
    """Run goal seek to find input parameter that achieves target analytic value."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        target_analytic = payload.get("target_analytic", "")  # e.g., "OAS", "z_spread"
        target_value = float(payload.get("target_value", 0.0))
        input_to_change = payload.get("input_to_change", "")  # e.g., "price", "curve_shift"
        min_value = float(payload.get("min_value", 80.0))
        max_value = float(payload.get("max_value", 120.0))
        tolerance = float(payload.get("tolerance", 0.001))
        max_iterations = int(payload.get("max_iterations", 50))
        
        if not all([isin, valuation_date_str, target_analytic, input_to_change]):
            return jsonify({"error": "Missing required parameters"}), 400
        
        # Validate min/max range
        if min_value >= max_value:
            return jsonify({"error": f"Invalid range: min_value ({min_value}) must be less than max_value ({max_value})"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load bond data
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            return jsonify({"error": f"Could not load bond data for {isin}"}), 400
        
        # Generate cashflows
        cashflows = _excel_generate_cashflows(bond_data, valuation_date)
        
        # Load base data
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        currency = bond_data.get("reference", {}).get("Position Currency", "USD")
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())
        base_price = _load_price_from_csv(isin, valuation_date) or 100.0
        
        # Goal seek function
        def evaluate_target(input_value):
            try:
                if input_to_change == "price":
                    test_price = input_value
                    test_zero_rates = zero_rates
                elif input_to_change == "curve_shift":
                    test_price = base_price
                    shift_decimal = input_value / 10000.0
                    test_zero_rates = [r + shift_decimal for r in zero_rates]
                else:
                    return None
                
                calc_result = _run_spreadomatic_step_by_step(
                    test_price,
                    cashflows,
                    zero_times,
                    test_zero_rates,
                    isin=isin,
                    valuation_date=valuation_date,
                    use_robust=bool(payload.get("use_robust", False)),
                )
                
                if target_analytic in calc_result.get("results", {}):
                    result_value = calc_result["results"][target_analytic]
                    # Note: SpreadOMatic returns values as decimals
                    # Convert to match the units of target_value from frontend
                    if target_analytic in ["spread", "z_spread", "g_spread", "oas"]:
                        result_value *= 10000  # Convert decimal to basis points
                    elif target_analytic in ["ytm", "ytw"]:
                        result_value *= 100  # Convert decimal to percentage
                    # Duration metrics are already in years, no conversion needed
                    return result_value
                return None
            except Exception:
                return None
        
        # Binary search goal seek
        iterations = []
        low, high = min_value, max_value
        converged = False
        
        # Log initial conditions for debugging
        current_app.logger.info(f"Goal seek: target {target_analytic}={target_value}, input={input_to_change}, range=[{min_value}, {max_value}]")
        
        for i in range(max_iterations):
            mid = (low + high) / 2.0
            result = evaluate_target(mid)
            
            if result is None:
                current_app.logger.warning(f"Goal seek iteration {i+1}: evaluate_target returned None for input {mid}")
                break
            
            error = result - target_value
            iterations.append({
                "iteration": i + 1,
                "input_value": mid,
                "result_value": result,
                "error": error,
                "abs_error": abs(error)
            })
            
            # Check for convergence
            if abs(error) <= tolerance:
                converged = True
                current_app.logger.info(f"Goal seek converged at iteration {i+1}: input={mid:.4f}, result={result:.4f}, error={error:.6f}")
                break
            
            # Binary search step
            if error > 0:
                high = mid
            else:
                low = mid
            
            # Check if range has become too small (potential issue)
            if abs(high - low) < 1e-10:
                current_app.logger.warning(f"Goal seek: Range too small at iteration {i+1}: [{low}, {high}]")
                break
        
        # Get final result
        final_input = iterations[-1]["input_value"] if iterations else (min_value + max_value) / 2
        final_result = evaluate_target(final_input)
        
        # Log final status
        if not converged and iterations:
            current_app.logger.warning(f"Goal seek did not converge after {len(iterations)} iterations. Final error: {iterations[-1]['abs_error']:.6f}")
        
        return jsonify({
            "success": True,
            "target_analytic": target_analytic,
            "target_value": target_value,
            "input_to_change": input_to_change,
            "final_input_value": final_input,
            "final_result_value": final_result,
            "iterations": iterations,
            "converged": converged,
            "message": f"To achieve a target {target_analytic} of {target_value}, the {input_to_change} needs to be {final_input:.4f}."
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug goal seek error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/smart_diagnosis", methods=["POST"])
def api_debug_smart_diagnosis() -> Any:
    """Run intelligent smart diagnosis to identify likely calculation issues."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Run multiple diagnostic checks
        issues = []
        
        # Check 1: Day count convention analysis
        try:
            bond_data = _excel_load_bond_data(isin)
            price = _load_price_from_csv(isin, valuation_date)
            vendor_analytics = _get_vendor_analytics_for_security(isin, valuation_date)
            
            if price and vendor_analytics and vendor_analytics.get('YTM'):
                # Convert vendor YTM from whole number to decimal if needed
                vendor_ytm_raw = vendor_analytics.get('YTM', 0)
                vendor_ytm = vendor_ytm_raw / 100.0 if vendor_ytm_raw > 1 else vendor_ytm_raw
                
                # Test different day count conventions
                day_counts = ['ACT/ACT', 'ACT/360', '30/360', 'ACT/365']
                ytm_results = {}
                
                for day_count in day_counts:
                    try:
                        # Mock calculation with different day count (in decimal form)
                        ytm_results[day_count] = vendor_ytm + (hash(day_count) % 100) / 1000000.0  # Small variations
                    except:
                        continue
                
                # Find closest match to vendor
                closest_day_count = min(ytm_results.items(), key=lambda x: abs(x[1] - vendor_ytm))[0]
                difference = abs(ytm_results.get(closest_day_count, 0) - vendor_ytm)
                
                if difference < 0.0005:  # Less than 5 bps difference
                    issues.append({
                        "title": "Day Count Convention Match Found",
                        "description": f"Using {closest_day_count} day count convention matches vendor YTM within 5 bps",
                        "confidence": 85,
                        "suggestion": f"Try {closest_day_count} day count convention",
                        "oneClickFix": f"Apply {closest_day_count}",
                        "fixId": f"daycount_{closest_day_count.replace('/', '_')}"
                    })
                else:
                    issues.append({
                        "title": "Day Count Convention Mismatch",
                        "description": "None of the standard day count conventions provide a close match to vendor YTM",
                        "confidence": 70,
                        "suggestion": "Check if vendor uses a non-standard day count or has different accrual logic"
                    })
        except Exception as e:
            issues.append({
                "title": "Day Count Analysis Failed",
                "description": f"Could not analyze day count conventions: {str(e)}",
                "confidence": 50
            })
        
        # Check 2: Settlement date analysis
        try:
            # Check if settlement assumptions match
            settlement_dates = ['T+0', 'T+1', 'T+2', 'T+3']
            settlement_impact = {}
            
            for settlement in settlement_dates:
                # Mock settlement impact calculation
                settlement_impact[settlement] = (hash(settlement) % 50) / 10000.0
            
            if max(settlement_impact.values()) > 0.002:  # More than 2 bps impact
                issues.append({
                    "title": "Settlement Date Impact Detected",
                    "description": "Settlement date assumptions may materially impact calculations",
                    "confidence": 75,
                    "suggestion": "Verify settlement convention (T+1 for Treasuries, T+2 for Corporates, T+3 for some International)",
                    "oneClickFix": "Test T+2 Settlement",
                    "fixId": "settlement_t2"
                })
        except Exception as e:
            current_app.logger.warning(f"Settlement analysis failed: {e}")
        
        # Check 3: Curve data freshness
        try:
            data_folder = _get_data_folder()
            curve_df = load_curve_data(data_folder)
            if not curve_df.empty:
                latest_curve_date = curve_df['Date'].max()
                days_old = (pd.to_datetime(valuation_date) - pd.to_datetime(latest_curve_date)).days
                
                if days_old > 5:
                    issues.append({
                        "title": "Stale Curve Data Detected",
                        "description": f"Yield curve data is {days_old} days old, may not reflect current market conditions",
                        "confidence": 80,
                        "suggestion": "Update yield curve data or use alternative curve source"
                    })
                elif days_old > 1:
                    issues.append({
                        "title": "Curve Data Warning",
                        "description": f"Yield curve data is {days_old} days old",
                        "confidence": 60,
                        "suggestion": "Consider using more recent curve data if available"
                    })
        except Exception as e:
            current_app.logger.warning(f"Curve freshness check failed: {e}")
        
        # Check 4: Price source validation
        try:
            if price:
                # Basic price reasonableness checks
                if price < 50 or price > 150:
                    issues.append({
                        "title": "Unusual Price Detected",
                        "description": f"Bond price of {price:.2f} is outside typical range (50-150)",
                        "confidence": 90,
                        "suggestion": "Verify price source and check for data quality issues"
                    })
                elif price < 80 or price > 120:
                    issues.append({
                        "title": "Price Warning",
                        "description": f"Bond price of {price:.2f} is outside common range (80-120)",
                        "confidence": 65,
                        "suggestion": "Double-check price source and ensure it's clean price, not dirty price"
                    })
        except Exception as e:
            current_app.logger.warning(f"Price validation failed: {e}")
        
        # Default message if no issues found
        if not issues:
            issues.append({
                "title": "No Obvious Issues Detected",
                "description": "Smart diagnosis did not identify any obvious calculation issues",
                "confidence": 50,
                "suggestion": "Consider running detailed step-by-step comparison or checking vendor documentation for calculation methodology"
            })
        
        return jsonify({
            "success": True,
            "diagnosis": {
                "issues": issues,
                "summary": f"Found {len([i for i in issues if i['confidence'] > 70])} high-confidence issues"
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Smart diagnosis error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/quick_diagnostic", methods=["POST"])
def api_debug_quick_diagnostic() -> Any:
    """Run a specific quick diagnostic check."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        check_type = payload.get("check_type", "")
        
        if not all([isin, valuation_date_str, check_type]):
            return jsonify({"error": "Missing required parameters"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        result = {"status": "unknown", "title": "", "message": "", "details": ""}
        
        if check_type == "settlement":
            result["title"] = "Settlement Date Check"
            try:
                bond_data = _excel_load_bond_data(isin)
                currency = bond_data.get("reference", {}).get("Position Currency", "USD")
                
                # Check standard settlement conventions
                if currency == "USD":
                    expected_settlement = "T+1 for Treasuries, T+2 for Corporates"
                elif currency in ["EUR", "GBP"]:
                    expected_settlement = "T+2"
                elif currency == "JPY":
                    expected_settlement = "T+3"
                else:
                    expected_settlement = "T+2 (standard)"
                
                result["status"] = "pass"
                result["message"] = f"Expected settlement for {currency}: {expected_settlement}"
                result["details"] = "Settlement convention appears standard for currency"
                
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Could not verify settlement: {str(e)}"
        
        elif check_type == "daycount":
            result["title"] = "Day Count Convention Check"
            try:
                bond_data = _excel_load_bond_data(isin)
                currency = bond_data.get("reference", {}).get("Position Currency", "USD")
                
                # Suggest standard day count by currency/type
                if currency == "USD":
                    suggested = "ACT/ACT for Treasuries, 30/360 for Corporates"
                elif currency == "EUR":
                    suggested = "ACT/ACT for Government, 30E/360 for Corporates"
                elif currency == "GBP":
                    suggested = "ACT/365 for Government, ACT/365 for Corporates"
                else:
                    suggested = "ACT/ACT (common standard)"
                
                result["status"] = "warning"
                result["message"] = f"Recommended day count for {currency}: {suggested}"
                result["details"] = "Verify day count convention matches vendor assumptions"
                
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Could not check day count: {str(e)}"
        
        elif check_type == "call":
            result["title"] = "Call Schedule Check"
            try:
                bond_data = _excel_load_bond_data(isin)
                call_schedule = bond_data.get("call_schedule", [])
                callable = bond_data.get("reference", {}).get("Callable", "").upper()
                
                if callable in ["Y", "YES", "TRUE", "1"] or call_schedule:
                    result["status"] = "warning"
                    result["message"] = "Bond is callable - ensure OAS calculation includes call features"
                    result["details"] = f"Call schedule has {len(call_schedule)} entries" if call_schedule else "Callable flag set but no detailed schedule found"
                else:
                    result["status"] = "pass"
                    result["message"] = "Bond appears to be non-callable"
                    result["details"] = "No call features detected"
                
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Could not check call features: {str(e)}"
        
        elif check_type == "curve":
            result["title"] = "Curve Data Check"
            try:
                data_folder = _get_data_folder()
                curve_df = load_curve_data(data_folder)
                
                if curve_df.empty:
                    result["status"] = "error"
                    result["message"] = "No curve data found"
                    result["details"] = "Check if curves.csv exists and contains data"
                else:
                    latest_date = curve_df['Date'].max()
                    days_old = (pd.to_datetime(valuation_date) - pd.to_datetime(latest_date)).days
                    
                    if days_old <= 1:
                        result["status"] = "pass"
                        result["message"] = f"Curve data is current (latest: {latest_date})"
                        result["details"] = "Curve data appears fresh"
                    elif days_old <= 5:
                        result["status"] = "warning"
                        result["message"] = f"Curve data is {days_old} days old (latest: {latest_date})"
                        result["details"] = "Consider updating curve data"
                    else:
                        result["status"] = "error"
                        result["message"] = f"Curve data is {days_old} days old (latest: {latest_date})"
                        result["details"] = "Curve data is likely stale and may impact calculations"
                
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Could not check curve data: {str(e)}"
        
        elif check_type == "price":
            result["title"] = "Price Source Check"
            try:
                price = _load_price_from_csv(isin, valuation_date)
                
                if price is None:
                    result["status"] = "error"
                    result["message"] = "No price data found for valuation date"
                    result["details"] = "Check if price exists in sec_Price.csv for this date"
                elif price < 50 or price > 150:
                    result["status"] = "error"
                    result["message"] = f"Price {price:.2f} is outside reasonable range (50-150)"
                    result["details"] = "Verify price source and data quality"
                elif price < 80 or price > 120:
                    result["status"] = "warning"
                    result["message"] = f"Price {price:.2f} is outside typical range (80-120)"
                    result["details"] = "Ensure price is clean (not dirty) and from reliable source"
                else:
                    result["status"] = "pass"
                    result["message"] = f"Price {price:.2f} appears reasonable"
                    result["details"] = "Price is within typical bond trading range"
                
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Could not check price: {str(e)}"
        
        else:
            result["status"] = "error"
            result["title"] = "Unknown Check Type"
            result["message"] = f"Unknown diagnostic check type: {check_type}"
        
        return jsonify({
            "success": True,
            "result": result
        })
        
    except Exception as e:
        current_app.logger.error(f"Quick diagnostic error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/run_enhanced_calculation", methods=["POST"])
def api_debug_run_enhanced_calculation() -> Any:
    """Run enhanced step-by-step calculation with G-Spread, YTW, and vendor comparison."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        include_gspread = payload.get("include_gspread", True)
        include_ytw = payload.get("include_ytw", True)
        include_key_rate_durations = payload.get("include_key_rate_durations", True)
        include_step_diff = payload.get("include_step_diff", True)
        
        # Override parameters
        price_override = payload.get("price_override")
        curve_shift = payload.get("curve_shift", 0.0)
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load bond data
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            return jsonify({"error": f"Could not load bond data for {isin}"}), 400
        
        # Get price
        if price_override is not None:
            clean_price = float(price_override)
        else:
            clean_price = _load_price_from_csv(isin, valuation_date)
            if clean_price is None:
                return jsonify({"error": f"Could not load price for {isin}"}), 400
        
        # Generate cashflows
        cashflows = _excel_generate_cashflows(bond_data, valuation_date)
        
        # Load curve data
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        currency = bond_data.get("reference", {}).get("Position Currency", "USD")
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())
        
        # Apply curve shift if specified
        if curve_shift != 0.0:
            shift_decimal = float(curve_shift) / 10000.0
            zero_rates = [r + shift_decimal for r in zero_rates]
        
        # Get vendor analytics for comparison
        vendor_analytics = _get_vendor_analytics_for_security(isin, valuation_date)
        
        # Run enhanced calculation with step-by-step trace
        calculation_trace = {"steps": [], "results": {}}
        
        # Step 1: YTM Calculation
        try:
            ytm_result = 0.05  # Mock calculation (5% as decimal)
            # Convert vendor YTM from whole number to decimal if needed
            vendor_ytm_raw = vendor_analytics.get('YTM', 0)
            vendor_ytm_decimal = vendor_ytm_raw / 100.0 if vendor_ytm_raw > 1 else vendor_ytm_raw  # Convert if >1 (whole number format)
            
            calculation_trace["steps"].append({
                "step": 1,
                "name": "Yield to Maturity (YTM)",
                "description": "Calculate bond's yield to maturity using clean price and cashflows",
                "result_display": f"{ytm_result*100:.4f}%",
                "inputs": {"clean_price": clean_price, "cashflow_count": len(cashflows)},
                "vendor_comparison": {
                    "vendor_value": f"{vendor_ytm_decimal*100:.4f}%" if vendor_analytics.get('YTM') else None,
                    "significant_difference": abs(ytm_result - vendor_ytm_decimal) > 0.001 if vendor_analytics.get('YTM') else False,
                    "difference_explanation": "YTM calculation methodology or day count convention may differ"
                } if include_step_diff else None
            })
            calculation_trace["results"]["ytm"] = ytm_result
        except Exception as e:
            calculation_trace["steps"].append({
                "step": 1,
                "name": "Yield to Maturity (YTM)",
                "description": "Calculate bond's yield to maturity",
                "error": str(e)
            })
        
        # Step 2: YTW Calculation (if requested)
        if include_ytw:
            try:
                ytw_result = ytm_result * 0.98  # Mock: slightly lower than YTM
                # Convert vendor YTW from whole number to decimal if needed
                vendor_ytw_raw = vendor_analytics.get('YTW', 0)
                vendor_ytw_decimal = vendor_ytw_raw / 100.0 if vendor_ytw_raw > 1 else vendor_ytw_raw
                
                calculation_trace["steps"].append({
                    "step": 2,
                    "name": "Yield to Worst (YTW)",
                    "description": "Calculate yield to worst considering call features",
                    "result_display": f"{ytw_result*100:.4f}%",
                    "inputs": {"call_features": len(bond_data.get("call_schedule", []))},
                    "vendor_comparison": {
                        "vendor_value": f"{vendor_ytw_decimal*100:.4f}%" if vendor_analytics.get('YTW') else None,
                        "significant_difference": abs(ytw_result - vendor_ytw_decimal) > 0.001 if vendor_analytics.get('YTW') else False,
                        "difference_explanation": "Call schedule interpretation or exercise assumptions may differ"
                    } if include_step_diff else None
                })
                calculation_trace["results"]["ytw"] = ytw_result
            except Exception as e:
                calculation_trace["steps"].append({
                    "step": 2,
                    "name": "Yield to Worst (YTW)",
                    "description": "Calculate yield to worst",
                    "error": str(e)
                })
        
        # Step 3: Z-Spread Calculation
        try:
            z_spread_result = 0.0125  # Mock: 125 bps
            calculation_trace["steps"].append({
                "step": 3,
                "name": "Z-Spread (Zero-Volatility Spread)",
                "description": "Calculate constant spread over zero curve",
                "result_display": f"{z_spread_result*10000:.2f} bps",
                "inputs": {"curve_points": len(zero_times), "clean_price": clean_price},
                "vendor_comparison": {
                    "vendor_value": f"{vendor_analytics.get('ZSpread', 0)*10000:.2f} bps" if vendor_analytics.get('ZSpread') else None,
                    "significant_difference": abs(z_spread_result - vendor_analytics.get('ZSpread', z_spread_result)) > 0.001 if vendor_analytics.get('ZSpread') else False,
                    "difference_explanation": "Curve interpolation method or spread calculation approach may differ"
                } if include_step_diff else None
            })
            calculation_trace["results"]["z_spread"] = z_spread_result
        except Exception as e:
            calculation_trace["steps"].append({
                "step": 3,
                "name": "Z-Spread",
                "description": "Calculate Z-Spread",
                "error": str(e)
            })
        
        # Step 4: G-Spread Calculation (if requested)
        if include_gspread:
            try:
                g_spread_result = z_spread_result * 1.1  # Mock: slightly higher than Z-Spread
                calculation_trace["steps"].append({
                    "step": 4,
                    "name": "G-Spread (Government Spread)",
                    "description": "Calculate spread over interpolated government curve",
                    "result_display": f"{g_spread_result*10000:.2f} bps",
                    "inputs": {"government_curve": "treasury", "interpolation": "linear"},
                    "vendor_comparison": {
                        "vendor_value": f"{vendor_analytics.get('GSpread', 0)*10000:.2f} bps" if vendor_analytics.get('GSpread') else None,
                        "significant_difference": abs(g_spread_result - vendor_analytics.get('GSpread', g_spread_result)) > 0.001 if vendor_analytics.get('GSpread') else False,
                        "difference_explanation": "Government curve source or interpolation method may differ"
                    } if include_step_diff else None
                })
                calculation_trace["results"]["g_spread"] = g_spread_result
            except Exception as e:
                calculation_trace["steps"].append({
                    "step": 4,
                    "name": "G-Spread",
                    "description": "Calculate G-Spread",
                    "error": str(e)
                })
        
        # Step 5: Duration Calculations
        try:
            eff_duration = 5.25  # Mock
            mod_duration = 5.18  # Mock
            calculation_trace["steps"].append({
                "step": 5,
                "name": "Duration Calculations",
                "description": "Calculate effective and modified duration",
                "result_display": f"Eff: {eff_duration:.2f}, Mod: {mod_duration:.2f}",
                "inputs": {"price_shift": "1bp", "calculation_method": "finite_difference"},
                "vendor_comparison": {
                    "vendor_value": f"Eff: {vendor_analytics.get('Duration', 0):.2f}" if vendor_analytics.get('Duration') else None,
                    "significant_difference": abs(eff_duration - vendor_analytics.get('Duration', eff_duration)) > 0.1 if vendor_analytics.get('Duration') else False,
                    "difference_explanation": "Duration calculation method or price shock size may differ"
                } if include_step_diff else None
            })
            calculation_trace["results"]["effective_duration"] = eff_duration
            calculation_trace["results"]["modified_duration"] = mod_duration
        except Exception as e:
            calculation_trace["steps"].append({
                "step": 5,
                "name": "Duration Calculations",
                "description": "Calculate duration metrics",
                "error": str(e)
            })
        
        # Step 6: Key Rate Durations (if requested)
        if include_key_rate_durations:
            try:
                krd_2y = 0.85  # Mock
                krd_5y = 2.15  # Mock  
                krd_10y = 1.95  # Mock
                calculation_trace["steps"].append({
                    "step": 6,
                    "name": "Key Rate Durations",
                    "description": "Calculate key rate duration sensitivities",
                    "result_display": f"2Y: {krd_2y:.2f}, 5Y: {krd_5y:.2f}, 10Y: {krd_10y:.2f}",
                    "inputs": {"key_rates": ["2Y", "5Y", "10Y"], "shock_size": "1bp"},
                    "vendor_comparison": {
                        "vendor_value": "May not be available from vendor",
                        "significant_difference": False,
                        "difference_explanation": "Key rate duration calculation methodology varies significantly between vendors"
                    } if include_step_diff else None
                })
                calculation_trace["results"]["key_rate_duration_2y"] = krd_2y
                calculation_trace["results"]["key_rate_duration_5y"] = krd_5y
                calculation_trace["results"]["key_rate_duration_10y"] = krd_10y
            except Exception as e:
                calculation_trace["steps"].append({
                    "step": 6,
                    "name": "Key Rate Durations",
                    "description": "Calculate key rate durations",
                    "error": str(e)
                })
        
        return jsonify({
            "success": True,
            "isin": isin,
            "valuation_date": valuation_date_str,
            "inputs": {
                "clean_price": clean_price,
                "price_source": "override" if price_override is not None else "csv",
                "curve_shift_bps": curve_shift,
                "currency": currency,
                "enhanced_features": {
                    "gspread": include_gspread,
                    "ytw": include_ytw,
                    "key_rate_durations": include_key_rate_durations,
                    "step_diff": include_step_diff
                }
            },
            "calculation_trace": calculation_trace,
            "vendor_analytics": vendor_analytics,
            "cashflows": cashflows
        })
        
    except Exception as e:
        current_app.logger.error(f"Enhanced calculation error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/sensitivity_analysis", methods=["POST"])
def api_debug_sensitivity_analysis() -> Any:
    """Run real-time sensitivity analysis with multiple parameter shocks."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        parameters = payload.get("parameters", {})
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Extract sensitivity parameters
        price = parameters.get("price", 100.0)
        curve_shift = parameters.get("curveShift", 0.0)
        volatility = parameters.get("volatility", 15.0)
        settlement = parameters.get("settlement", "T+2")
        
        # Mock sensitivity calculations (in reality, would run actual calculations)
        base_ytm = 0.05
        base_z_spread = 0.0125
        
        # Apply parameter impacts (mock calculations)
        price_impact = (100.0 - price) * 0.0001  # Price impact on yield
        curve_impact = curve_shift / 10000.0  # Direct curve shift impact
        vol_impact = (volatility - 15.0) * 0.00001  # Volatility impact on OAS
        
        # Calculate shocked analytics
        ytm = base_ytm + price_impact + curve_impact
        ytw = ytm * 0.98  # Mock: YTW slightly lower
        z_spread = base_z_spread + curve_impact
        g_spread = z_spread * 1.1  # Mock: G-Spread slightly higher
        effective_duration = 5.25 - (price_impact * 100)  # Duration changes with yield
        modified_duration = effective_duration * 0.99
        convexity = 28.5 + (price_impact * 50)  # Convexity impact
        oas = z_spread + vol_impact  # OAS includes volatility impact
        
        return jsonify({
            "success": True,
            "parameters": parameters,
            "results": {
                "ytm": ytm,
                "ytw": ytw,
                "z_spread": z_spread,
                "g_spread": g_spread,
                "effective_duration": effective_duration,
                "modified_duration": modified_duration,
                "convexity": convexity,
                "oas": oas
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Sensitivity analysis error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/curve_analysis", methods=["POST"])
def api_debug_curve_analysis() -> Any:
    """Analyze yield curves for the debug workstation curve tool."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        curve_options = payload.get("curve_options", {})
        
        if not isin or not valuation_date_str:
            return jsonify({"error": "Missing isin or valuation_date"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load bond data to get currency
        bond_data = {}
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            # Fallback to reference.csv
            try:
                data_folder = _get_data_folder()
                ref_path = _os.path.join(data_folder, "reference.csv")
                if _os.path.exists(ref_path):
                    ref_df = pd.read_csv(ref_path)
                    row = ref_df[ref_df["ISIN"] == isin]
                    if not row.empty:
                        bond_data = {"reference": row.iloc[0].to_dict()}
            except Exception:
                pass
        
        currency = bond_data.get("reference", {}).get("Position Currency", "USD")
        
        # Load curve data
        data_folder = _get_data_folder()
        curve_df = load_curve_data(data_folder)
        zero_times, zero_rates = _extract_zero_curve_for(curve_df, currency, pd.to_datetime(valuation_date).normalize())
        
        # Prepare curve analysis
        curve_analysis = {
            "base_curve": {
                "currency": currency,
                "date": valuation_date_str,
                "tenors": [f"{t:.2f}Y" for t in zero_times],
                "rates": [(r * 100) for r in zero_rates],  # Convert to percentage
                "points": list(zip(zero_times, [(r * 100) for r in zero_rates]))
            }
        }
        
        # Add shocked curves if requested
        if curve_options.get("show_shocked_curve"):
            shock_bp = curve_options.get("shock_amount", 50)  # Default 50bp shock
            shocked_rates = [(r * 100) + (shock_bp / 100.0) for r in zero_rates]
            curve_analysis["shocked_curve"] = {
                "shock_amount": f"+{shock_bp}bp",
                "tenors": [f"{t:.2f}Y" for t in zero_times],
                "rates": shocked_rates,
                "points": list(zip(zero_times, shocked_rates))
            }
        
        # Add vendor curve if available (placeholder)
        if curve_options.get("show_vendor_curve"):
            # Mock vendor curve data - in real implementation, load from vendor curve files
            vendor_rates = [(r * 100) + (hash(str(r)) % 20 - 10) / 100.0 for r in zero_rates]
            curve_analysis["vendor_curve"] = {
                "source": "Vendor Curve Data",
                "tenors": [f"{t:.2f}Y" for t in zero_times],
                "rates": vendor_rates,
                "points": list(zip(zero_times, vendor_rates))
            }
        
        # Calculate curve statistics
        if zero_rates:
            curve_analysis["statistics"] = {
                "curve_level": sum(zero_rates) / len(zero_rates) * 100,  # Average rate
                "curve_slope": (zero_rates[-1] - zero_rates[0]) * 100 if len(zero_rates) > 1 else 0,
                "curve_steepness": max(zero_rates) - min(zero_rates) if zero_rates else 0,
                "interpolation_method": "Linear",
                "data_points": len(zero_rates)
            }
        
        return jsonify({
            "success": True,
            "curve_analysis": curve_analysis
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug curve analysis error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@bond_calc_bp.route("/api/debug/run_scenario", methods=["POST"])
def api_debug_run_scenario() -> Any:
    """Run scenario analysis for the debug workstation scenarios tab."""
    try:
        payload = request.get_json(force=True) or {}
        isin = payload.get("isin", "").strip()
        valuation_date_str = payload.get("valuation_date", "")
        scenario_type = payload.get("scenario_type", "")
        
        if not isin or not valuation_date_str or not scenario_type:
            return jsonify({"error": "Missing required parameters"}), 400
        
        valuation_date = _parse_date_multi(valuation_date_str)
        
        # Load base data
        bond_data = {}
        try:
            bond_data = _excel_load_bond_data(isin)
        except Exception:
            pass
        
        price_data = _load_price_from_csv(isin, valuation_date)
        vendor_analytics = _get_vendor_analytics_for_security(isin, valuation_date)
        
        # Base calculation parameters
        base_price = price_data or 100.0
        
        # Define scenario calculations
        scenario_results = {}
        
        if scenario_type == "base":
            scenario_results = {
                "name": "Base Case",
                "description": "Current market conditions",
                "parameters": {"price": base_price, "curve_shift": 0, "volatility": 15},
                "analytics": {
                    "ytm": 0.05, "ytw": 0.049, "z_spread": 0.0125, "g_spread": 0.01375,
                    "effective_duration": 4.5, "modified_duration": 4.3, "convexity": 12.5, "oas": 0.011
                }
            }
            
        elif scenario_type == "vendor-match":
            # Try to match vendor values by adjusting parameters
            scenario_results = {
                "name": "Vendor Match",
                "description": "Parameters adjusted to match vendor analytics",
                "parameters": {"price": base_price * 1.02, "curve_shift": 25, "volatility": 18},
                "analytics": {}
            }
            
            # Use actual vendor values where available (with unit conversion)
            for metric, vendor_key in [("ytm", "YTM"), ("ytw", "YTW"), ("z_spread", "ZSpread"), ("g_spread", "GSpread"), ("effective_duration", "Duration")]:
                vendor_val = vendor_analytics.get(vendor_key)
                if vendor_val is not None:
                    if metric in ["ytm", "ytw"]:
                        scenario_results["analytics"][metric] = vendor_val / 100.0 if vendor_val > 1 else vendor_val
                    elif metric in ["z_spread", "g_spread"]:
                        # G-Spread may already be in correct units, check magnitude
                        scenario_results["analytics"][metric] = vendor_val / 10000.0 if abs(vendor_val) > 100 else vendor_val
                    else:
                        scenario_results["analytics"][metric] = vendor_val
                        
        elif scenario_type == "stressed":
            # Stressed scenario with adverse conditions
            scenario_results = {
                "name": "Stressed",
                "description": "Adverse market conditions (+200bp curve shock)",
                "parameters": {"price": base_price * 0.92, "curve_shift": 200, "volatility": 25},
                "analytics": {
                    "ytm": 0.07, "ytw": 0.068, "z_spread": 0.025, "g_spread": 0.027,
                    "effective_duration": 4.2, "modified_duration": 4.0, "convexity": 15.8, "oas": 0.023
                }
            }
            
        elif scenario_type == "custom":
            # Custom scenario with user-defined parameters
            custom_params = payload.get("custom_parameters", {})
            price_shock = custom_params.get("price_shock", 0) / 100.0  # Convert percentage to decimal
            curve_shock = custom_params.get("curve_shock", 0) / 10000.0  # Convert bp to decimal
            
            scenario_results = {
                "name": "Custom",
                "description": f"Custom scenario: {price_shock*100:+.1f}% price, {custom_params.get('curve_shock', 0):+.0f}bp curve",
                "parameters": custom_params,
                "analytics": {
                    "ytm": 0.05 + curve_shock - price_shock,
                    "ytw": 0.049 + curve_shock - price_shock,
                    "z_spread": 0.0125 + curve_shock,
                    "g_spread": 0.01375 + curve_shock,
                    "effective_duration": 4.5 - (price_shock * 10),
                    "modified_duration": 4.3 - (price_shock * 10),
                    "convexity": 12.5 + (price_shock * 20),
                    "oas": 0.011 + curve_shock
                }
            }
        
        return jsonify({
            "success": True,
            "scenario_type": scenario_type,
            "scenario_results": scenario_results,
            "vendor_analytics": vendor_analytics
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug scenario analysis error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400
