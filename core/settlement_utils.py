"""
Settlement utilities module for Simple Data Checker.
Provides functions for calculating settlement dates based on configured conventions.
"""

import logging
from datetime import datetime, timedelta
import pandas as pd
from pandas.tseries.offsets import BDay
from pathlib import Path
from typing import Optional, Dict, Any, Union

from core.settings_loader import (
    get_settlement_conventions,
    get_currency_settlement, 
    get_security_type_settlement,
    get_settlement_days
)

logger = logging.getLogger(__name__)

class SettlementCalculator:
    """Calculate settlement dates based on conventions."""
    
    def __init__(self):
        """Initialize with settlement conventions."""
        self.conventions = get_settlement_conventions()
        self._load_calendars()
    
    def _load_calendars(self):
        """Load holiday calendars for different markets."""
        self.calendars = self.conventions.get('calendars', {})
        self.cutoff_times = self.conventions.get('cutoff_times', {})
    
    def calculate_settlement_date(
        self,
        trade_date: Union[datetime, pd.Timestamp, str],
        currency: Optional[str] = None,
        security_type: Optional[str] = None,
        trade_type: str = 'standard'
    ) -> pd.Timestamp:
        """
        Calculate settlement date from trade date.
        
        Args:
            trade_date: The trade execution date
            currency: Currency code (e.g., 'USD', 'EUR')
            security_type: Security type (e.g., 'treasury', 'corporate_bond')
            trade_type: Type of trade (e.g., 'standard', 'when_issued')
        
        Returns:
            Settlement date as pd.Timestamp
        """
        # Convert to pandas Timestamp
        if isinstance(trade_date, str):
            trade_date = pd.to_datetime(trade_date)
        elif isinstance(trade_date, datetime):
            trade_date = pd.Timestamp(trade_date)
        
        # Get settlement days (T+n)
        settlement_days = get_settlement_days(currency, security_type, trade_type)
        
        # Apply business day logic
        settlement_date = self._add_business_days(trade_date, settlement_days, currency)
        
        # Apply special rules if needed
        settlement_date = self._apply_special_rules(settlement_date, currency, security_type)
        
        return settlement_date
    
    def _add_business_days(
        self,
        start_date: pd.Timestamp,
        days: int,
        currency: Optional[str] = None
    ) -> pd.Timestamp:
        """Add business days considering market calendar."""
        if days == 0:
            return start_date
        
        # Use pandas BDay for now (can be enhanced with market calendars)
        # In production, you'd integrate with proper market calendar libraries
        return start_date + BDay(days)
    
    def _apply_special_rules(
        self,
        settlement_date: pd.Timestamp,
        currency: Optional[str] = None,
        security_type: Optional[str] = None
    ) -> pd.Timestamp:
        """Apply special settlement rules and adjustments."""
        special_rules = self.conventions.get('special_rules', {})
        
        # Apply holiday adjustments
        holiday_adj = special_rules.get('holiday_adjustment', {})
        method = holiday_adj.get('method', 'modified_following')
        
        # Apply month-end rules if applicable
        month_end_rules = special_rules.get('month_end_rules', {})
        if month_end_rules.get('apply') and settlement_date.is_month_end:
            # Keep at month end if original was month end
            pass
        
        return settlement_date
    
    def get_cutoff_time(self, currency: str, transaction_type: str = 'securities') -> str:
        """Get cutoff time for a currency and transaction type."""
        currency_cutoffs = self.cutoff_times.get(currency, {})
        return currency_cutoffs.get(transaction_type, '17:00')
    
    def is_same_day_settlement(self, security_type: str) -> bool:
        """Check if security type has same-day settlement."""
        security_conventions = self.conventions.get('security_type_conventions', {})
        if security_type in security_conventions:
            return security_conventions[security_type].get('standard', 2) == 0
        return False
    
    def get_fail_penalty_rate(self) -> float:
        """Get fail penalty rate from conventions."""
        fail_rules = self.conventions.get('special_rules', {}).get('fail_rules', {})
        return fail_rules.get('penalty_rate', 3.0)
    
    def validate_settlement_date(
        self,
        trade_date: Union[datetime, pd.Timestamp],
        settlement_date: Union[datetime, pd.Timestamp],
        currency: Optional[str] = None,
        security_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate if settlement date follows conventions.
        
        Returns:
            Dictionary with validation results
        """
        # Convert to timestamps
        if isinstance(trade_date, (datetime, str)):
            trade_date = pd.to_datetime(trade_date)
        if isinstance(settlement_date, (datetime, str)):
            settlement_date = pd.to_datetime(settlement_date)
        
        # Calculate expected settlement
        expected_settlement = self.calculate_settlement_date(
            trade_date, currency, security_type
        )
        
        # Calculate actual T+n
        actual_days = pd.bdate_range(trade_date, settlement_date).size - 1
        expected_days = get_settlement_days(currency, security_type)
        
        return {
            'is_valid': settlement_date == expected_settlement,
            'expected_settlement': expected_settlement,
            'actual_settlement': settlement_date,
            'expected_t_plus': expected_days,
            'actual_t_plus': actual_days,
            'variance_days': actual_days - expected_days
        }

def get_settlement_calculator() -> SettlementCalculator:
    """Get or create singleton settlement calculator instance."""
    if not hasattr(get_settlement_calculator, '_instance'):
        get_settlement_calculator._instance = SettlementCalculator()
    return get_settlement_calculator._instance

def calculate_settlement_date(
    trade_date: Union[datetime, pd.Timestamp, str],
    currency: Optional[str] = None,
    security_type: Optional[str] = None,
    trade_type: str = 'standard'
) -> pd.Timestamp:
    """
    Convenience function to calculate settlement date.
    
    Args:
        trade_date: The trade execution date
        currency: Currency code (e.g., 'USD', 'EUR')
        security_type: Security type (e.g., 'treasury', 'corporate_bond')
        trade_type: Type of trade (e.g., 'standard', 'when_issued')
    
    Returns:
        Settlement date as pd.Timestamp
    """
    calculator = get_settlement_calculator()
    return calculator.calculate_settlement_date(trade_date, currency, security_type, trade_type)

def validate_settlement(
    trade_date: Union[datetime, pd.Timestamp],
    settlement_date: Union[datetime, pd.Timestamp],
    currency: Optional[str] = None,
    security_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to validate settlement date.
    
    Returns:
        Dictionary with validation results
    """
    calculator = get_settlement_calculator()
    return calculator.validate_settlement_date(trade_date, settlement_date, currency, security_type)

def get_standard_settlement_days(currency: str = None, security_type: str = None) -> int:
    """Get standard T+n settlement days for given parameters."""
    return get_settlement_days(currency, security_type, 'standard')