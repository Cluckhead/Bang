# cashflows.py
# Purpose: Adapter layer for SpreadOMatic's cashflow generation functions

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from tools.SpreadOMatic.spreadomatic.cashflows import generate_fixed_schedule
from tools.SpreadOMatic.spreadomatic.daycount import year_fraction as oas_year_fraction


def _normalize_day_basis(basis: str) -> str:
    """Map unsupported day-count basis strings to supported equivalents.

    SpreadOMatic supports: 30/360, ACT/360, ACT/365, ACT/ACT, ACT/ACT-ISDA (ISDA).
    Normalize common variants like 30E/360 to 30/360.
    """
    if not basis:
        return "30/360"
    b = str(basis).strip().upper()
    if b in {"30E/360", "30E", "30/360E"}:
        return "30/360"
    return b


def generate_cashflows(bond_data: Dict, valuation_date: datetime) -> List[Dict]:
    """Generate future cashflows using SpreadOMatic's core implementation.
    
    This function adapts the bond_data dict format to call SpreadOMatic's
    generate_fixed_schedule function, then transforms the output to match
    the expected format for Excel generation.
    """
    schedule = bond_data["schedule"]
    reference = bond_data["reference"]

    # Import the enhanced date parser
    from .data_loader import _parse_date_multi
    
    maturity_date = _parse_date_multi(schedule["Maturity Date"])
    issue_date = _parse_date_multi(schedule["Issue Date"])
    first_coupon = _parse_date_multi(schedule["First Coupon"])

    coupon_rate = float(reference["Coupon Rate"]) / 100.0
    coupon_freq = int(schedule["Coupon Frequency"])
    day_basis = _normalize_day_basis(schedule["Day Basis"])
    currency = reference.get("Position Currency", "USD")
    # Business day convention from schedule or reference if available
    bdc = (
        schedule.get('Business Day Convention')
        or schedule.get('BusinessDayConvention')
        or reference.get('Business Day Convention')
        or reference.get('BusinessDayConvention')
        or 'NONE'
    )
    notional = 100.0

    # Call SpreadOMatic's function with proper parameters
    full_schedule = generate_fixed_schedule(
        issue_date=issue_date,
        first_coupon_date=first_coupon,
        maturity_date=maturity_date,
        coupon_rate=coupon_rate,
        day_basis=day_basis,
        currency=currency,
        notional=notional,
        coupon_frequency=coupon_freq,
        business_day_convention=str(bdc)
    )
    
    # Filter for cashflows after valuation date and transform to expected format
    cashflows: List[Dict] = []
    
    # SpreadOMatic may generate separate payments for last coupon and principal
    # We need to combine them if they're close to maturity
    payments_to_process = []
    for payment in full_schedule:
        payment_date = datetime.fromisoformat(payment["date"])
        if payment_date > valuation_date:
            payments_to_process.append((payment_date, payment["amount"]))
    
    i = 0
    while i < len(payments_to_process):
        payment_date, amount = payments_to_process[i]
        
        # Check if this is near maturity and might need combining
        days_to_maturity = abs((payment_date - maturity_date).days)
        
        # If we're within 7 days of maturity and there's a next payment at maturity
        if (days_to_maturity <= 7 and 
            i + 1 < len(payments_to_process) and 
            payments_to_process[i + 1][0] >= maturity_date):
            # Combine this coupon with the principal payment
            next_date, next_amount = payments_to_process[i + 1]
            
            time_years = oas_year_fraction(valuation_date, next_date, "ACT/ACT")
            coupon_payment = amount  # Current payment is the coupon
            principal = next_amount  # Next payment should be principal (100)
            
            # Verify principal is around 100
            if abs(principal - notional) < 10:  # Allow some tolerance
                # This is indeed the principal payment
                pass
            else:
                # Next payment includes both - extract components
                principal = notional
                coupon_payment = amount
                
            cashflows.append({
                "date": next_date,  # Use maturity date
                "time_years": time_years,
                "coupon": coupon_payment,
                "principal": principal,
                "total": coupon_payment + principal,
                "accrual_period": coupon_payment / (notional * coupon_rate) if coupon_rate > 0 else 0,
            })
            i += 2  # Skip both payments as we've combined them
        else:
            # Regular coupon payment or single maturity payment
            time_years = oas_year_fraction(valuation_date, payment_date, "ACT/ACT")
            
            # Check if this is the maturity payment
            is_maturity = payment_date >= maturity_date
            
            if is_maturity:
                # At maturity, we should have both principal and final coupon
                if amount >= notional * 1.5:
                    # Combined payment already includes both
                    principal = notional
                    coupon_payment = amount - principal
                elif abs(amount - notional) < 0.01:
                    # Just principal (100) - missing final coupon due to business day adjustment
                    # This is a bug in the cashflow generation - we should add the final coupon
                    principal = notional
                    # Calculate standard coupon for the period
                    coupon_payment = notional * coupon_rate / coupon_freq
                    print(f"Warning: Final payment only had principal. Adding missing coupon of {coupon_payment:.4f}")
                else:
                    # Unexpected amount at maturity
                    principal = notional
                    coupon_payment = max(0, amount - principal)
            else:
                # Regular coupon payment before maturity
                principal = 0
                coupon_payment = amount
                
            accrual_period = coupon_payment / (notional * coupon_rate) if coupon_rate > 0 and coupon_payment > 0 else 0
            
            cashflows.append({
                "date": payment_date,
                "time_years": time_years,
                "coupon": coupon_payment,
                "principal": principal,
                "total": coupon_payment + principal,  # This will now include both when at maturity
                "accrual_period": accrual_period,
            })
            i += 1
    
    return cashflows


def to_payment_schedule(cashflows: List[Dict]) -> List[Dict]:
    """Convert generated cashflows to SpreadOMatic-compatible payment schedule."""
    return [
        {"date": (cf["date"].isoformat() if isinstance(cf["date"], datetime) else cf["date"]), "amount": cf["total"]}
        for cf in cashflows
    ]


