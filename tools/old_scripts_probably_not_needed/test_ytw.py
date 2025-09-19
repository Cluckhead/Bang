#!/usr/bin/env python
"""Test script for YTW (Yield to Worst) implementation in SpreadOMatic"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.SpreadOMatic.spreadomatic.ytw import calculate_ytw
from tools.SpreadOMatic.spreadomatic.yield_spread import solve_ytm

def test_callable_bond():
    """Test YTW calculation for a callable bond"""
    
    print("=" * 60)
    print("Testing YTW for Callable Bond")
    print("=" * 60)
    
    # Bond parameters
    dirty_price = 105.0  # Trading above par
    coupon_rate = 0.05   # 5% annual coupon
    frequency = 2        # Semi-annual payments
    principal = 100.0
    
    # Valuation date
    valuation_date = datetime(2024, 1, 15)
    
    # Create simple cashflows (2 years to maturity)
    cashflows = [
        (0.5, 2.5),   # 6 months: $2.50 coupon
        (1.0, 2.5),   # 1 year: $2.50 coupon
        (1.5, 2.5),   # 1.5 years: $2.50 coupon
        (2.0, 102.5), # 2 years: $2.50 coupon + $100 principal
    ]
    
    # Call schedule - callable at par in 1 year
    call_schedule = [
        {
            'date': datetime(2025, 1, 15),  # Callable in 1 year
            'price': 100.0  # At par
        }
    ]
    
    # Calculate YTM first
    times = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    ytm = solve_ytm(dirty_price, times, amounts, comp=2)
    print(f"\nYield to Maturity: {ytm * 100:.2f}%")
    
    # Calculate YTW
    result = calculate_ytw(
        dirty_price=dirty_price,
        cashflows=cashflows,
        call_schedule=call_schedule,
        valuation_date=valuation_date,
        settlement_date=valuation_date,
        coupon_rate=coupon_rate,
        frequency=frequency,
        principal=principal,
        day_basis="ACT/ACT",
        compounding=2
    )
    
    print(f"\nYTW Results:")
    print(f"  YTW: {result['ytw'] * 100:.2f}%")
    print(f"  YTW Date: {result['ytw_date']}")
    print(f"  YTW Type: {result['ytw_type']}")
    print(f"  YTW Price: {result['ytw_price']}")
    
    print(f"\nAll Calculated Yields:")
    for yield_info in result['all_yields']:
        print(f"  {yield_info['type'].capitalize()} on {yield_info['date']}: "
              f"{yield_info['yield'] * 100:.2f}% (price: {yield_info['price']})")
    
    # Analysis
    print(f"\nAnalysis:")
    if result['ytw'] < ytm:
        print(f"  Bond is likely to be called (YTW < YTM)")
        print(f"  Investor's worst case yield is {result['ytw'] * 100:.2f}%")
    else:
        print(f"  Bond is likely to mature (YTW = YTM)")
    
    return result


def test_non_callable_bond():
    """Test YTW calculation for a non-callable bond (should equal YTM)"""
    
    print("\n" + "=" * 60)
    print("Testing YTW for Non-Callable Bond")
    print("=" * 60)
    
    # Bond parameters
    dirty_price = 95.0   # Trading below par
    
    # Simple cashflows
    cashflows = [
        (0.5, 3.0),
        (1.0, 3.0),
        (1.5, 3.0),
        (2.0, 103.0),
    ]
    
    # No call schedule
    call_schedule = None
    
    # Calculate YTM
    times = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    ytm = solve_ytm(dirty_price, times, amounts, comp=2)
    print(f"\nYield to Maturity: {ytm * 100:.2f}%")
    
    # Calculate YTW (should equal YTM)
    result = calculate_ytw(
        dirty_price=dirty_price,
        cashflows=cashflows,
        call_schedule=call_schedule,
        valuation_date=datetime(2024, 1, 15),
        compounding=2
    )
    
    print(f"\nYTW Results:")
    print(f"  YTW: {result['ytw'] * 100:.2f}%")
    print(f"  YTW Type: {result['ytw_type']}")
    
    # Verify YTW equals YTM
    if abs(result['ytw'] - ytm) < 0.0001:
        print(f"\n✓ Correct: YTW equals YTM for non-callable bond")
    else:
        print(f"\n✗ Error: YTW should equal YTM for non-callable bond")
    
    return result


def test_multiple_call_dates():
    """Test YTW with multiple call dates"""
    
    print("\n" + "=" * 60)
    print("Testing YTW with Multiple Call Dates")
    print("=" * 60)
    
    dirty_price = 108.0  # Premium bond
    
    cashflows = [
        (0.5, 3.5),
        (1.0, 3.5),
        (1.5, 3.5),
        (2.0, 3.5),
        (2.5, 3.5),
        (3.0, 103.5),
    ]
    
    # Multiple call dates with different prices
    call_schedule = [
        {'date': datetime(2025, 1, 15), 'price': 102.0},  # 1 year: 102
        {'date': datetime(2025, 7, 15), 'price': 101.0},  # 1.5 years: 101
        {'date': datetime(2026, 1, 15), 'price': 100.0},  # 2 years: par
    ]
    
    result = calculate_ytw(
        dirty_price=dirty_price,
        cashflows=cashflows,
        call_schedule=call_schedule,
        valuation_date=datetime(2024, 1, 15),
        coupon_rate=0.07,
        frequency=2,
        principal=100.0,
        compounding=2
    )
    
    print(f"\nYTW Results:")
    print(f"  YTW: {result['ytw'] * 100:.2f}%")
    print(f"  Worst Date: {result['ytw_date']}")
    print(f"  Call Price: {result['ytw_price']}")
    
    print(f"\nAll Scenarios:")
    for yield_info in result['all_yields']:
        worst_marker = " ← WORST" if yield_info['yield'] == result['ytw'] else ""
        print(f"  {yield_info['type'].capitalize()} on {yield_info['date']}: "
              f"{yield_info['yield'] * 100:.2f}% (price: {yield_info['price']}){worst_marker}")
    
    return result


if __name__ == "__main__":
    print("Testing YTW Implementation in SpreadOMatic")
    print("=" * 60)
    
    try:
        # Run tests
        test_callable_bond()
        test_non_callable_bond()
        test_multiple_call_dates()
        
        print("\n" + "=" * 60)
        print("✓ All YTW tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)