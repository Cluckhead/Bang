"""
Trade settlement processing module.
Demonstrates usage of settlement conventions for trade processing and validation.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from core.settlement_utils import (
    calculate_settlement_date,
    validate_settlement,
    get_standard_settlement_days,
    get_settlement_calculator
)
from core.settings_loader import get_settlement_conventions
from core.data_utils import read_csv_robustly, parse_dates_robustly

logger = logging.getLogger(__name__)

def process_trades_with_settlement(
    trades_df: pd.DataFrame,
    currency_col: str = 'Currency',
    security_type_col: str = 'SecurityType',
    trade_date_col: str = 'TradeDate',
    settlement_date_col: str = 'SettlementDate'
) -> pd.DataFrame:
    """
    Process trades DataFrame and add/validate settlement information.
    
    Args:
        trades_df: DataFrame containing trade data
        currency_col: Name of currency column
        security_type_col: Name of security type column
        trade_date_col: Name of trade date column
        settlement_date_col: Name of settlement date column (if exists)
    
    Returns:
        DataFrame with settlement calculations and validations
    """
    if trades_df.empty:
        return trades_df
    
    df = trades_df.copy()
    
    # Parse dates
    if trade_date_col in df.columns:
        df[trade_date_col] = pd.to_datetime(df[trade_date_col], errors='coerce')
    
    if settlement_date_col in df.columns:
        df[settlement_date_col] = pd.to_datetime(df[settlement_date_col], errors='coerce')
    
    # Calculate expected settlement dates
    calculator = get_settlement_calculator()
    
    expected_settlements = []
    settlement_validations = []
    
    for idx, row in df.iterrows():
        try:
            trade_date = row.get(trade_date_col)
            currency = row.get(currency_col) if currency_col in df.columns else None
            security_type = row.get(security_type_col) if security_type_col in df.columns else None
            
            if pd.notna(trade_date):
                # Calculate expected settlement
                expected_settlement = calculate_settlement_date(
                    trade_date, 
                    currency=currency,
                    security_type=security_type
                )
                expected_settlements.append(expected_settlement)
                
                # Validate actual settlement if provided
                if settlement_date_col in df.columns and pd.notna(row.get(settlement_date_col)):
                    validation = validate_settlement(
                        trade_date,
                        row[settlement_date_col],
                        currency=currency,
                        security_type=security_type
                    )
                    settlement_validations.append(validation)
                else:
                    settlement_validations.append(None)
            else:
                expected_settlements.append(None)
                settlement_validations.append(None)
                
        except Exception as e:
            logger.error(f"Error processing settlement for row {idx}: {e}")
            expected_settlements.append(None)
            settlement_validations.append(None)
    
    # Add calculated columns
    df['ExpectedSettlement'] = expected_settlements
    
    # Add validation columns if actual settlement exists
    if settlement_date_col in df.columns:
        df['SettlementValid'] = [v['is_valid'] if v else None for v in settlement_validations]
        df['SettlementVarianceDays'] = [v['variance_days'] if v else None for v in settlement_validations]
        df['ExpectedTPlus'] = [v['expected_t_plus'] if v else None for v in settlement_validations]
        df['ActualTPlus'] = [v['actual_t_plus'] if v else None for v in settlement_validations]
    
    # Add standard T+n for reference
    df['StandardTPlus'] = df.apply(
        lambda row: get_standard_settlement_days(
            row.get(currency_col) if currency_col in df.columns else None,
            row.get(security_type_col) if security_type_col in df.columns else None
        ),
        axis=1
    )
    
    return df

def identify_settlement_failures(
    trades_df: pd.DataFrame,
    threshold_days: int = 1
) -> pd.DataFrame:
    """
    Identify potential settlement failures based on variance from expected.
    
    Args:
        trades_df: DataFrame with settlement calculations
        threshold_days: Number of days variance to flag as potential failure
    
    Returns:
        DataFrame containing only trades with potential settlement issues
    """
    if 'SettlementVarianceDays' not in trades_df.columns:
        logger.warning("Settlement variance not calculated, cannot identify failures")
        return pd.DataFrame()
    
    # Filter for settlement issues
    failures = trades_df[
        (trades_df['SettlementVarianceDays'].abs() > threshold_days) |
        (trades_df['SettlementValid'] == False)
    ].copy()
    
    # Add failure categorization
    if not failures.empty:
        failures['FailureType'] = failures.apply(
            lambda row: categorize_settlement_failure(row),
            axis=1
        )
    
    return failures

def categorize_settlement_failure(row: pd.Series) -> str:
    """Categorize the type of settlement failure."""
    variance = row.get('SettlementVarianceDays', 0)
    
    if pd.isna(variance):
        return 'Missing Data'
    elif variance > 0:
        return f'Late Settlement (T+{int(row.get("ActualTPlus", 0))})'
    elif variance < 0:
        return f'Early Settlement (T+{int(row.get("ActualTPlus", 0))})'
    else:
        return 'Invalid Settlement'

def generate_settlement_report(
    trades_df: pd.DataFrame,
    group_by: List[str] = None
) -> Dict[str, Any]:
    """
    Generate settlement statistics report.
    
    Args:
        trades_df: DataFrame with settlement calculations
        group_by: Columns to group statistics by
    
    Returns:
        Dictionary containing settlement statistics
    """
    if trades_df.empty:
        return {}
    
    if group_by is None:
        group_by = ['Currency', 'SecurityType']
    
    report = {
        'summary': {
            'total_trades': len(trades_df),
            'trades_with_settlement': trades_df['SettlementDate'].notna().sum() if 'SettlementDate' in trades_df.columns else 0,
            'valid_settlements': trades_df['SettlementValid'].sum() if 'SettlementValid' in trades_df.columns else 0,
            'invalid_settlements': (~trades_df['SettlementValid']).sum() if 'SettlementValid' in trades_df.columns else 0
        }
    }
    
    # Group statistics
    if all(col in trades_df.columns for col in group_by):
        grouped = trades_df.groupby(group_by)
        
        group_stats = []
        for name, group in grouped:
            stats = {
                'group': name,
                'count': len(group),
                'avg_t_plus': group['ActualTPlus'].mean() if 'ActualTPlus' in group.columns else None,
                'expected_t_plus': group['ExpectedTPlus'].mode().iloc[0] if 'ExpectedTPlus' in group.columns and not group['ExpectedTPlus'].empty else None,
                'variance_mean': group['SettlementVarianceDays'].mean() if 'SettlementVarianceDays' in group.columns else None,
                'variance_std': group['SettlementVarianceDays'].std() if 'SettlementVarianceDays' in group.columns else None
            }
            group_stats.append(stats)
        
        report['group_statistics'] = group_stats
    
    # Identify outliers
    if 'SettlementVarianceDays' in trades_df.columns:
        variance_std = trades_df['SettlementVarianceDays'].std()
        variance_mean = trades_df['SettlementVarianceDays'].mean()
        
        outliers = trades_df[
            trades_df['SettlementVarianceDays'].abs() > (variance_mean + 2 * variance_std)
        ]
        
        report['outliers'] = {
            'count': len(outliers),
            'percentage': len(outliers) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        }
    
    return report

def apply_settlement_conventions_to_portfolio(
    positions_df: pd.DataFrame,
    valuation_date: datetime
) -> pd.DataFrame:
    """
    Apply settlement conventions to portfolio positions for cash flow projections.
    
    Args:
        positions_df: DataFrame containing portfolio positions
        valuation_date: Date for valuation/settlement calculations
    
    Returns:
        DataFrame with settlement-adjusted cash flows
    """
    df = positions_df.copy()
    
    # Get settlement conventions
    conventions = get_settlement_conventions()
    calculator = get_settlement_calculator()
    
    # Calculate settlement dates for different transaction types
    for idx, position in df.iterrows():
        currency = position.get('Currency')
        security_type = position.get('SecurityType')
        
        # Calculate various settlement scenarios
        df.loc[idx, 'SpotSettlement'] = calculate_settlement_date(
            valuation_date, currency, security_type, 'standard'
        )
        
        # Check for same-day settlement eligibility
        df.loc[idx, 'SameDayEligible'] = calculator.is_same_day_settlement(security_type)
        
        # Get cutoff time
        df.loc[idx, 'CutoffTime'] = calculator.get_cutoff_time(
            currency, 'securities'
        ) if currency else None
    
    return df

def validate_trade_file_settlements(
    file_path: str,
    output_path: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Validate settlements in a trade file and optionally save results.
    
    Args:
        file_path: Path to trade file
        output_path: Optional path to save validation results
    
    Returns:
        Tuple of (validated DataFrame, summary statistics)
    """
    try:
        # Read trade file
        trades_df = read_csv_robustly(file_path)
        
        if trades_df.empty:
            logger.warning(f"No data found in {file_path}")
            return pd.DataFrame(), {}
        
        # Process with settlement validations
        validated_df = process_trades_with_settlement(trades_df)
        
        # Generate report
        report = generate_settlement_report(validated_df)
        
        # Identify failures
        failures = identify_settlement_failures(validated_df)
        report['failures'] = {
            'count': len(failures),
            'details': failures.to_dict('records') if not failures.empty else []
        }
        
        # Save if output path provided
        if output_path:
            validated_df.to_csv(output_path, index=False)
            logger.info(f"Saved validated trades to {output_path}")
        
        return validated_df, report
        
    except Exception as e:
        logger.error(f"Error validating trade file {file_path}: {e}")
        return pd.DataFrame(), {}