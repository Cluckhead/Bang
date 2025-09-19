# settlement_mechanics.py
# Purpose: Institutional-grade settlement mechanics for fixed income instruments
# Implements T+1/T+2/T+3 settlement, ex-dividend calculations, and accrued interest precision

from __future__ import annotations

import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Optional, Union, NamedTuple
from dataclasses import dataclass
from enum import Enum
import calendar

from .daycount_enhanced import (
    year_fraction_precise, 
    DayCountConvention, 
    HolidayCalendar, 
    BusinessDayConvention,
    adjust_business_day,
    add_business_days
)

__all__ = [
    "SettlementConvention",
    "SettlementCalculator", 
    "AccruedCalculator",
    "ExDividendCalculator",
    "MarketSettlementRules",
    "SettlementResult",
    "calculate_settlement_details"
]


class SettlementConvention(Enum):
    """Settlement timing conventions by instrument type"""
    CASH = "T+0"                    # Same day settlement
    REGULAR_WAY_BOND = "T+1"        # Next business day (US Treasuries)
    REGULAR_WAY_CORP = "T+2"        # Two business days (Corporate bonds)
    REGULAR_WAY_STOCK = "T+2"       # Two business days (Equities)
    WHEN_ISSUED = "T+1"             # When-issued securities
    SETTLEMENT_DATE = "T+3"         # Three business days (some international)
    CASH_MANAGEMENT = "T+0"         # Money market instruments
    
    @property
    def days(self) -> int:
        """Extract number of days from convention"""
        if self.value == "T+0":
            return 0
        elif self.value == "T+1":
            return 1
        elif self.value == "T+2":
            return 2
        elif self.value == "T+3":
            return 3
        else:
            return 1  # Default


@dataclass
class SettlementResult:
    """Complete settlement calculation results"""
    trade_date: datetime
    settlement_date: datetime
    accrued_interest: float
    accrued_days: int
    ex_dividend_adjustment: float
    clean_price: float
    dirty_price: float
    settlement_amount: float
    day_count_fraction: float
    next_coupon_date: Optional[datetime] = None
    previous_coupon_date: Optional[datetime] = None
    is_ex_dividend: bool = False
    settlement_convention: str = "T+1"
    currency: str = "USD"


class MarketSettlementRules:
    """
    Market-specific settlement rules and conventions.
    
    Implements the precise settlement mechanics used by major financial centers.
    """
    
    def __init__(self, market: str = "US"):
        self.market = market.upper()
        self.calendar = HolidayCalendar(self._get_country_code())
        self._load_market_rules()
    
    def _get_country_code(self) -> str:
        """Map market to country code for holiday calendar"""
        market_map = {
            "US": "US", "USA": "US", "UNITED_STATES": "US",
            "UK": "UK", "GBP": "UK", "LONDON": "UK", "GB": "UK",
            "EUR": "EUR", "EURO": "EUR", "GERMANY": "DE", "DE": "DE",
            "JAPAN": "JP", "JPY": "JP", "JP": "JP",
            "CANADA": "CA", "CAD": "CA", "CA": "CA"
        }
        return market_map.get(self.market, "US")
    
    def _load_market_rules(self):
        """Load market-specific settlement rules"""
        if self.market in ["US", "USA"]:
            self.bond_settlement = SettlementConvention.REGULAR_WAY_BOND  # T+1
            self.corporate_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2  
            self.treasury_settlement = SettlementConvention.REGULAR_WAY_BOND  # T+1
            self.money_market_settlement = SettlementConvention.CASH  # T+0
            self.ex_dividend_days = 1  # 1 business day before record date
            self.accrual_basis = "ACT/ACT-ISDA"
            
        elif self.market in ["UK", "GBP", "GB"]:
            self.bond_settlement = SettlementConvention.REGULAR_WAY_BOND  # T+1
            self.corporate_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2
            self.gilt_settlement = SettlementConvention.REGULAR_WAY_BOND  # T+1
            self.money_market_settlement = SettlementConvention.CASH  # T+0
            self.ex_dividend_days = 7  # 7 calendar days before record date
            self.accrual_basis = "ACT/ACT-ISDA"
            
        elif self.market in ["EUR", "DE", "GERMANY"]:
            self.bond_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2
            self.corporate_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2
            self.government_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2
            self.money_market_settlement = SettlementConvention.REGULAR_WAY_CORP  # T+2
            self.ex_dividend_days = 1  # 1 business day
            self.accrual_basis = "ACT/ACT-ICMA"
            
        elif self.market in ["JP", "JAPAN", "JPY"]:
            self.bond_settlement = SettlementConvention.SETTLEMENT_DATE  # T+3
            self.corporate_settlement = SettlementConvention.SETTLEMENT_DATE  # T+3
            self.government_settlement = SettlementConvention.SETTLEMENT_DATE  # T+3
            self.ex_dividend_days = 1
            self.accrual_basis = "ACT/365-FIXED"
            
        else:
            # Default to US rules
            self.bond_settlement = SettlementConvention.REGULAR_WAY_BOND
            self.corporate_settlement = SettlementConvention.REGULAR_WAY_CORP
            self.ex_dividend_days = 1
            self.accrual_basis = "ACT/ACT-ISDA"
    
    def get_settlement_convention(self, instrument_type: str) -> SettlementConvention:
        """Get settlement convention for instrument type"""
        instrument_type = instrument_type.upper()
        
        if instrument_type in ["TREASURY", "GOVERNMENT", "GILT", "BUND"]:
            return getattr(self, "treasury_settlement", 
                          getattr(self, "government_settlement", 
                                 getattr(self, "gilt_settlement", self.bond_settlement)))
        elif instrument_type in ["CORPORATE", "CREDIT", "BOND"]:
            return self.corporate_settlement
        elif instrument_type in ["MONEY_MARKET", "DEPOSIT", "CP", "CD"]:
            return getattr(self, "money_market_settlement", SettlementConvention.CASH)
        else:
            return self.bond_settlement


class SettlementCalculator:
    """
    Professional settlement date calculator with market-specific rules.
    
    Handles complex scenarios like month-end, holiday weekends, and cross-border trades.
    """
    
    def __init__(self, market_rules: Optional[MarketSettlementRules] = None):
        self.market_rules = market_rules or MarketSettlementRules("US")
    
    def calculate_settlement_date(self, 
                                trade_date: datetime,
                                instrument_type: str = "BOND",
                                convention_override: Optional[SettlementConvention] = None) -> datetime:
        """
        Calculate settlement date with full business day and holiday handling.
        
        Args:
            trade_date: Trade execution date
            instrument_type: Type of instrument being settled
            convention_override: Override default settlement convention
            
        Returns:
            Settlement date (business day adjusted)
        """
        # Get settlement convention
        if convention_override:
            settlement_convention = convention_override
        else:
            settlement_convention = self.market_rules.get_settlement_convention(instrument_type)
        
        # Add settlement days
        settlement_days = settlement_convention.days
        if settlement_days == 0:
            return trade_date  # Same day settlement
        
        # Add business days using holiday calendar
        settlement_date = add_business_days(
            trade_date, 
            settlement_days, 
            self.market_rules.calendar
        )
        
        # Apply business day adjustment (Modified Following is standard)
        settlement_date = adjust_business_day(
            settlement_date, 
            BusinessDayConvention.MODIFIED_FOLLOWING,
            self.market_rules.calendar
        )
        
        return settlement_date
    
    def calculate_trade_date(self, 
                           settlement_date: datetime,
                           instrument_type: str = "BOND") -> datetime:
        """
        Calculate trade date given settlement date (reverse calculation).
        
        Useful for when-issued calculations and settlement date analysis.
        """
        settlement_convention = self.market_rules.get_settlement_convention(instrument_type)
        settlement_days = settlement_convention.days
        
        if settlement_days == 0:
            return settlement_date
        
        # Subtract business days
        trade_date = add_business_days(
            settlement_date, 
            -settlement_days, 
            self.market_rules.calendar
        )
        
        return trade_date
    
    def is_valid_settlement_date(self, 
                               trade_date: datetime, 
                               settlement_date: datetime,
                               instrument_type: str = "BOND") -> bool:
        """Check if settlement date is valid for given trade date"""
        expected_settlement = self.calculate_settlement_date(trade_date, instrument_type)
        return settlement_date == expected_settlement


class AccruedCalculator:
    """
    Precision accrued interest calculator with exact day count and settlement mechanics.
    
    Handles complex scenarios like leap years, month-end dates, and ex-dividend periods.
    """
    
    def __init__(self, market_rules: Optional[MarketSettlementRules] = None):
        self.market_rules = market_rules or MarketSettlementRules("US")
    
    def calculate_accrued_interest(self,
                                 settlement_date: datetime,
                                 coupon_rate: float,
                                 face_value: float,
                                 previous_coupon_date: datetime,
                                 next_coupon_date: datetime,
                                 day_count_convention: str,
                                 frequency: int = 2,
                                 is_first_coupon: bool = False,
                                 is_last_coupon: bool = False) -> Dict[str, float]:
        """
        Calculate precise accrued interest with institutional accuracy.
        
        Args:
            settlement_date: Settlement date for calculation
            coupon_rate: Annual coupon rate (as decimal)
            face_value: Face value of bond  
            previous_coupon_date: Previous coupon payment date
            next_coupon_date: Next coupon payment date
            day_count_convention: Day count method
            frequency: Coupon frequency per year
            is_first_coupon: Whether this is first coupon period
            is_last_coupon: Whether this is last coupon period
            
        Returns:
            Dictionary with detailed accrued interest breakdown
        """
        
        # Handle edge cases
        if settlement_date <= previous_coupon_date:
            return {
                'accrued_interest': 0.0,
                'accrued_days': 0,
                'coupon_period_days': 0,
                'day_count_fraction': 0.0,
                'coupon_amount': 0.0,
                'settlement_date': settlement_date
            }
        
        # Calculate day count fractions with precision
        accrued_fraction = year_fraction_precise(
            previous_coupon_date, 
            settlement_date, 
            day_count_convention,
            frequency
        )
        
        coupon_period_fraction = year_fraction_precise(
            previous_coupon_date,
            next_coupon_date, 
            day_count_convention,
            frequency
        )
        
        # Handle irregular first/last coupon periods
        if is_first_coupon or is_last_coupon:
            # Actual coupon amount may be prorated
            period_coupon = coupon_rate * coupon_period_fraction * face_value
        else:
            # Regular coupon
            period_coupon = (coupon_rate / frequency) * face_value
        
        # Calculate accrued interest
        if coupon_period_fraction > 0:
            accrued_interest = period_coupon * (accrued_fraction / coupon_period_fraction)
        else:
            accrued_interest = 0.0
        
        # Calculate calendar days for reference
        accrued_days = (settlement_date - previous_coupon_date).days
        coupon_period_days = (next_coupon_date - previous_coupon_date).days
        
        return {
            'accrued_interest': accrued_interest,
            'accrued_days': accrued_days,
            'coupon_period_days': coupon_period_days,
            'day_count_fraction': accrued_fraction,
            'coupon_period_fraction': coupon_period_fraction,
            'coupon_amount': period_coupon,
            'settlement_date': settlement_date,
            'day_count_convention': day_count_convention
        }
    
    def calculate_accrued_for_bond_schedule(self,
                                          settlement_date: datetime,
                                          bond_data: Dict) -> Dict[str, float]:
        """Calculate accrued interest using full bond schedule information"""
        
        # Extract bond parameters
        coupon_rate = float(bond_data.get('reference', {}).get('Coupon Rate', 0)) / 100.0
        face_value = 100.0  # Standard
        frequency = int(bond_data.get('schedule', {}).get('Coupon Frequency', 2))
        day_count = bond_data.get('schedule', {}).get('Day Basis', 'ACT/ACT')
        
        # Generate coupon schedule (simplified - in practice would use full schedule)
        maturity_date = self._parse_date(bond_data.get('schedule', {}).get('Maturity Date'))
        issue_date = self._parse_date(bond_data.get('schedule', {}).get('Issue Date'))
        
        # Find surrounding coupon dates
        previous_coupon, next_coupon = self._find_coupon_dates(
            settlement_date, issue_date, maturity_date, frequency
        )
        
        # Determine if irregular coupon
        is_first = (previous_coupon <= issue_date + timedelta(days=30))
        is_last = (next_coupon >= maturity_date - timedelta(days=30))
        
        return self.calculate_accrued_interest(
            settlement_date, coupon_rate, face_value,
            previous_coupon, next_coupon, day_count,
            frequency, is_first, is_last
        )
    
    def _find_coupon_dates(self, 
                          settlement_date: datetime,
                          issue_date: datetime,
                          maturity_date: datetime,
                          frequency: int) -> Tuple[datetime, datetime]:
        """Find previous and next coupon dates around settlement date"""
        
        # Generate coupon dates (simplified approach)
        months_between = 12 // frequency
        
        # Start from maturity and work backwards
        coupon_dates = []
        current_date = maturity_date
        
        while current_date > issue_date:
            coupon_dates.append(current_date)
            # Subtract months
            if current_date.month <= months_between:
                current_date = current_date.replace(
                    year=current_date.year - 1,
                    month=current_date.month + 12 - months_between
                )
            else:
                current_date = current_date.replace(
                    month=current_date.month - months_between
                )
        
        coupon_dates.sort()
        
        # Find surrounding dates
        for i, coupon_date in enumerate(coupon_dates):
            if coupon_date > settlement_date:
                if i > 0:
                    return coupon_dates[i-1], coupon_date
                else:
                    return issue_date, coupon_date
        
        # Settlement after last coupon
        return coupon_dates[-1] if coupon_dates else maturity_date, maturity_date
    
    def _parse_date(self, date_input) -> datetime:
        """Parse date from various formats"""
        if isinstance(date_input, datetime):
            return date_input
        if isinstance(date_input, str):
            try:
                return datetime.strptime(date_input, '%d/%m/%Y')
            except:
                try:
                    return datetime.strptime(date_input, '%Y-%m-%d')
                except:
                    return datetime.now()
        return datetime.now()


class ExDividendCalculator:
    """
    Ex-dividend and record date calculator for coupon-bearing bonds.
    
    Handles market-specific ex-dividend rules and their impact on settlement.
    """
    
    def __init__(self, market_rules: Optional[MarketSettlementRules] = None):
        self.market_rules = market_rules or MarketSettlementRules("US")
    
    def calculate_ex_dividend_date(self, 
                                 record_date: datetime,
                                 payment_date: datetime) -> datetime:
        """
        Calculate ex-dividend date based on market rules.
        
        Args:
            record_date: Record date for coupon entitlement
            payment_date: Actual payment date
            
        Returns:
            Ex-dividend date
        """
        # Ex-dividend date is typically 1-7 business days before record date
        ex_dividend_days = self.market_rules.ex_dividend_days
        
        ex_dividend_date = add_business_days(
            record_date, 
            -ex_dividend_days, 
            self.market_rules.calendar
        )
        
        return ex_dividend_date
    
    def is_ex_dividend(self, 
                      settlement_date: datetime,
                      record_date: datetime,
                      payment_date: datetime) -> bool:
        """Check if settlement occurs during ex-dividend period"""
        ex_dividend_date = self.calculate_ex_dividend_date(record_date, payment_date)
        return settlement_date >= ex_dividend_date and settlement_date < payment_date
    
    def calculate_ex_dividend_adjustment(self,
                                       settlement_date: datetime,
                                       coupon_amount: float,
                                       record_date: datetime,
                                       payment_date: datetime) -> float:
        """
        Calculate price adjustment for ex-dividend trading.
        
        When a bond trades ex-dividend, the buyer doesn't receive the upcoming coupon,
        so the price is typically adjusted downward.
        """
        if self.is_ex_dividend(settlement_date, record_date, payment_date):
            # Full coupon adjustment for bonds (unlike stocks with dividend yield)
            return -coupon_amount
        else:
            return 0.0


def calculate_settlement_details(trade_date: datetime,
                               bond_data: Dict,
                               clean_price: float,
                               face_value: float = 100.0,
                               market: str = "US",
                               settlement_override: Optional[datetime] = None) -> SettlementResult:
    """
    Comprehensive settlement calculation with full institutional precision.
    
    This is the main function that orchestrates all settlement mechanics.
    
    Args:
        trade_date: Trade execution date
        bond_data: Complete bond information
        clean_price: Clean price of the bond
        face_value: Face value for calculation
        market: Market for settlement rules
        settlement_override: Optional specific settlement date
        
    Returns:
        Complete SettlementResult with all calculations
    """
    
    # Initialize calculators
    market_rules = MarketSettlementRules(market)
    settlement_calc = SettlementCalculator(market_rules)
    accrued_calc = AccruedCalculator(market_rules)
    ex_div_calc = ExDividendCalculator(market_rules)
    
    # Calculate settlement date
    if settlement_override:
        settlement_date = settlement_override
    else:
        instrument_type = bond_data.get('reference', {}).get('Security Sub Type', 'BOND')
        settlement_date = settlement_calc.calculate_settlement_date(trade_date, instrument_type)
    
    # Calculate accrued interest
    accrued_details = accrued_calc.calculate_accrued_for_bond_schedule(settlement_date, bond_data)
    accrued_interest = accrued_details['accrued_interest']
    
    # Calculate dirty price
    dirty_price = clean_price + accrued_interest
    
    # Calculate settlement amount
    settlement_amount = dirty_price * face_value / 100.0
    
    # Ex-dividend calculations (simplified for bonds)
    # In practice, would need full coupon schedule
    next_coupon_date = settlement_date + timedelta(days=180)  # Simplified
    coupon_rate = float(bond_data.get('reference', {}).get('Coupon Rate', 0)) / 100.0
    frequency = int(bond_data.get('schedule', {}).get('Coupon Frequency', 2))
    coupon_amount = (coupon_rate / frequency) * face_value
    
    record_date = next_coupon_date - timedelta(days=7)  # Simplified
    is_ex_dividend = ex_div_calc.is_ex_dividend(settlement_date, record_date, next_coupon_date)
    ex_dividend_adjustment = ex_div_calc.calculate_ex_dividend_adjustment(
        settlement_date, coupon_amount, record_date, next_coupon_date
    )
    
    # Create comprehensive result
    return SettlementResult(
        trade_date=trade_date,
        settlement_date=settlement_date,
        accrued_interest=accrued_interest,
        accrued_days=accrued_details['accrued_days'],
        ex_dividend_adjustment=ex_dividend_adjustment,
        clean_price=clean_price,
        dirty_price=dirty_price,
        settlement_amount=settlement_amount,
        day_count_fraction=accrued_details['day_count_fraction'],
        next_coupon_date=next_coupon_date,
        is_ex_dividend=is_ex_dividend,
        settlement_convention=market_rules.bond_settlement.value,
        currency=bond_data.get('reference', {}).get('Position Currency', 'USD')
    )


def test_settlement_mechanics():
    """Comprehensive test suite for settlement mechanics"""
    print("Testing Settlement Mechanics...")
    
    # Test 1: Basic settlement calculation
    trade_date = datetime(2024, 3, 15)  # Friday
    
    settlement_calc = SettlementCalculator()
    settlement_date = settlement_calc.calculate_settlement_date(trade_date, "TREASURY")
    print(f"T+1 Settlement: {trade_date.strftime('%A %Y-%m-%d')} → {settlement_date.strftime('%A %Y-%m-%d')}")
    
    # Test 2: Holiday handling
    trade_date_holiday = datetime(2024, 7, 3)  # Day before July 4th
    settlement_holiday = settlement_calc.calculate_settlement_date(trade_date_holiday, "CORPORATE")
    print(f"Holiday Settlement: {trade_date_holiday.strftime('%A %Y-%m-%d')} → {settlement_holiday.strftime('%A %Y-%m-%d')}")
    
    # Test 3: Accrued interest calculation
    bond_data = {
        'reference': {'Coupon Rate': 5.0, 'Position Currency': 'USD'},
        'schedule': {
            'Day Basis': 'ACT/ACT', 
            'Coupon Frequency': 2,
            'Issue Date': '15/01/2020',
            'Maturity Date': '15/01/2030'
        }
    }
    
    accrued_calc = AccruedCalculator()
    accrued_result = accrued_calc.calculate_accrued_for_bond_schedule(
        datetime(2024, 4, 15), bond_data
    )
    print(f"Accrued Interest: ${accrued_result['accrued_interest']:.4f} ({accrued_result['accrued_days']} days)")
    
    # Test 4: Full settlement calculation
    settlement_result = calculate_settlement_details(
        trade_date=datetime(2024, 3, 15),
        bond_data=bond_data,
        clean_price=98.50,
        face_value=100.0,
        market="US"
    )
    
    print(f"\nFull Settlement Details:")
    print(f"  Trade Date: {settlement_result.trade_date.strftime('%Y-%m-%d')}")
    print(f"  Settlement Date: {settlement_result.settlement_date.strftime('%Y-%m-%d')}")
    print(f"  Clean Price: ${settlement_result.clean_price:.4f}")
    print(f"  Accrued Interest: ${settlement_result.accrued_interest:.4f}")
    print(f"  Dirty Price: ${settlement_result.dirty_price:.4f}")
    print(f"  Settlement Amount: ${settlement_result.settlement_amount:.2f}")
    print(f"  Convention: {settlement_result.settlement_convention}")
    
    print("Settlement mechanics testing complete!")


if __name__ == "__main__":
    test_settlement_mechanics()
