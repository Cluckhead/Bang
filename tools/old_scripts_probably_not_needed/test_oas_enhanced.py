# test_oas_enhanced.py
# Purpose: Test and demonstrate the enhanced OAS calculation improvements

import sys
import os
import json
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spreadomatic.oas import compute_oas
from spreadomatic.oas_enhanced import (
    compute_oas_enhanced, 
    VolatilityCalibrator, 
    BinomialOASCalculator
)
from spreadomatic.daycount import to_datetime, year_fraction
from spreadomatic.interpolation import linear_interpolate
from spreadomatic.yield_spread import solve_ytm, z_spread
from spreadomatic.discount import discount_factor


def create_test_bond():
    """Create a test callable bond with multiple call dates."""
    valuation_date = datetime(2024, 1, 15)
    
    # Payment schedule - 5% annual coupon, 5-year maturity
    payment_schedule = [
        {"date": "2025-01-15", "amount": 5.0},
        {"date": "2026-01-15", "amount": 5.0},
        {"date": "2027-01-15", "amount": 5.0},
        {"date": "2028-01-15", "amount": 5.0},
        {"date": "2029-01-15", "amount": 105.0},  # Final coupon + principal
    ]
    
    # Multiple call dates with declining call prices
    call_schedule = [
        {"date": "2025-01-15", "price": 102.0},  # Call at 102 in 1 year
        {"date": "2026-01-15", "price": 101.5},  # Call at 101.5 in 2 years
        {"date": "2027-01-15", "price": 101.0},  # Call at 101 in 3 years
        {"date": "2028-01-15", "price": 100.5},  # Call at 100.5 in 4 years
    ]
    
    # Zero curve (simplified flat curve for testing)
    zero_times = [0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]
    zero_rates = [0.03, 0.032, 0.034, 0.036, 0.038, 0.04, 0.042, 0.045]
    
    # Bond characteristics for volatility adjustment
    bond_characteristics = {
        'rating': 'BBB',
        'credit_spread': 0.015,  # 150 bps
        'sector': 'Corporate',
        'currency': 'USD'
    }
    
    return {
        'valuation_date': valuation_date,
        'payment_schedule': payment_schedule,
        'call_schedule': call_schedule,
        'zero_times': zero_times,
        'zero_rates': zero_rates,
        'clean_price': 98.5,  # Trading at discount
        'day_basis': '30/360',
        'bond_characteristics': bond_characteristics
    }


def compare_oas_methods():
    """Compare original vs enhanced OAS calculation."""
    
    print("=" * 70)
    print("OAS CALCULATION COMPARISON: Original vs Enhanced")
    print("=" * 70)
    
    # Create test bond
    bond = create_test_bond()
    
    # Extract cashflows for calculations
    from spreadomatic.cashflows import extract_cashflows
    times, cfs = extract_cashflows(
        bond['payment_schedule'],
        bond['valuation_date'],
        bond['zero_times'],
        bond['zero_rates'],
        bond['day_basis']
    )
    
    # Calculate YTM and Z-spread for reference
    ytm = solve_ytm(bond['clean_price'], times, cfs, comp='annual')
    z_spr = z_spread(bond['clean_price'], times, cfs, 
                     bond['zero_times'], bond['zero_rates'], comp='annual')
    
    print(f"\nBond Analytics:")
    print(f"  Clean Price:     {bond['clean_price']:.2f}")
    print(f"  YTM:            {ytm*100:.3f}%")
    print(f"  Z-Spread:       {z_spr*10000:.1f} bps")
    
    # 1. Original OAS (simplified, single call, fixed volatility)
    print("\n" + "-" * 50)
    print("1. ORIGINAL OAS CALCULATION")
    print("-" * 50)
    
    # Original only uses first call
    first_call = bond['call_schedule'][0]
    original_oas = compute_oas(
        bond['payment_schedule'],
        bond['valuation_date'],
        bond['zero_times'],
        bond['zero_rates'],
        bond['day_basis'],
        bond['clean_price'],
        next_call_date=to_datetime(first_call['date']),
        next_call_price=first_call['price'],
        comp='annual',
        sigma=0.20  # Fixed 20% volatility
    )
    
    if original_oas:
        print(f"  Method:         Black model (single call)")
        print(f"  Volatility:     20.0% (fixed)")
        print(f"  Calls used:     1 of {len(bond['call_schedule'])}")
        print(f"  OAS:           {original_oas*10000:.1f} bps")
    else:
        print("  Calculation failed")
    
    # 2. Enhanced OAS with default volatility
    print("\n" + "-" * 50)
    print("2. ENHANCED OAS - DEFAULT VOLATILITY")
    print("-" * 50)
    
    enhanced_oas_default = compute_oas_enhanced(
        bond['payment_schedule'],
        bond['valuation_date'],
        bond['zero_times'],
        bond['zero_rates'],
        bond['day_basis'],
        bond['clean_price'],
        call_schedule=bond['call_schedule'],
        comp='annual',
        use_binomial=False,  # Use Black for comparison
        bond_characteristics=bond['bond_characteristics']
    )
    
    if enhanced_oas_default:
        print(f"  Method:         Black model (multi-call aware)")
        print(f"  Volatility:     Calibrated (term structure)")
        print(f"  Calls used:     {len(bond['call_schedule'])} of {len(bond['call_schedule'])}")
        print(f"  OAS:           {enhanced_oas_default*10000:.1f} bps")
    else:
        print("  Calculation failed")
    
    # 3. Enhanced OAS with calibrated volatility
    print("\n" + "-" * 50)
    print("3. ENHANCED OAS - CALIBRATED VOLATILITY")
    print("-" * 50)
    
    # Create calibrated volatility model
    calibrator = VolatilityCalibrator(default_vol=0.15)
    
    # Demonstrate volatility term structure
    print("  Volatility term structure:")
    for year in [1, 2, 3, 5]:
        vol = calibrator.get_volatility(year, 1.0, bond['bond_characteristics'])
        print(f"    {year}Y: {vol*100:.1f}%")
    
    enhanced_oas_calibrated = compute_oas_enhanced(
        bond['payment_schedule'],
        bond['valuation_date'],
        bond['zero_times'],
        bond['zero_rates'],
        bond['day_basis'],
        bond['clean_price'],
        call_schedule=bond['call_schedule'],
        comp='annual',
        volatility_calibrator=calibrator,
        use_binomial=False,
        bond_characteristics=bond['bond_characteristics']
    )
    
    if enhanced_oas_calibrated:
        print(f"  OAS:           {enhanced_oas_calibrated*10000:.1f} bps")
    else:
        print("  Calculation failed")
    
    # 4. Enhanced OAS with binomial tree
    print("\n" + "-" * 50)
    print("4. ENHANCED OAS - BINOMIAL TREE")
    print("-" * 50)
    
    enhanced_oas_binomial = compute_oas_enhanced(
        bond['payment_schedule'],
        bond['valuation_date'],
        bond['zero_times'],
        bond['zero_rates'],
        bond['day_basis'],
        bond['clean_price'],
        call_schedule=bond['call_schedule'],
        comp='annual',
        volatility_calibrator=calibrator,
        use_binomial=True,  # Use binomial tree
        bond_characteristics=bond['bond_characteristics']
    )
    
    if enhanced_oas_binomial:
        print(f"  Method:         Binomial tree (100 steps)")
        print(f"  American style: Yes (optimal exercise)")
        print(f"  Calls used:     All {len(bond['call_schedule'])} dates")
        print(f"  OAS:           {enhanced_oas_binomial*10000:.1f} bps")
    else:
        print("  Calculation failed")
    
    # Summary comparison
    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON")
    print("=" * 70)
    
    if original_oas and enhanced_oas_default and enhanced_oas_calibrated and enhanced_oas_binomial:
        print(f"\nOAS Results (in basis points):")
        print(f"  Original (fixed vol, single call):      {original_oas*10000:7.1f} bps")
        print(f"  Enhanced (default vol, multi-call):     {enhanced_oas_default*10000:7.1f} bps")
        print(f"  Enhanced (calibrated vol, multi-call):  {enhanced_oas_calibrated*10000:7.1f} bps")
        print(f"  Enhanced (binomial tree, all calls):    {enhanced_oas_binomial*10000:7.1f} bps")
        
        # Calculate differences
        diff_default = (enhanced_oas_default - original_oas) * 10000
        diff_calibrated = (enhanced_oas_calibrated - original_oas) * 10000
        diff_binomial = (enhanced_oas_binomial - original_oas) * 10000
        
        print(f"\nDifferences from Original:")
        print(f"  Enhanced default:     {diff_default:+7.1f} bps")
        print(f"  Enhanced calibrated:  {diff_calibrated:+7.1f} bps")
        print(f"  Enhanced binomial:    {diff_binomial:+7.1f} bps")
        
        print("\nKey Improvements:")
        print("  ✓ Market-calibrated volatility (vs fixed 20%)")
        print("  ✓ Full call schedule consideration")
        print("  ✓ Credit spread adjustment for volatility")
        print("  ✓ American option pricing (binomial)")
        print("  ✓ Term structure of volatility")
    
    return {
        'original': original_oas,
        'enhanced_default': enhanced_oas_default,
        'enhanced_calibrated': enhanced_oas_calibrated,
        'enhanced_binomial': enhanced_oas_binomial
    }


def test_volatility_calibration():
    """Test the volatility calibration features."""
    
    print("\n" + "=" * 70)
    print("VOLATILITY CALIBRATION DEMONSTRATION")
    print("=" * 70)
    
    calibrator = VolatilityCalibrator(default_vol=0.15)
    
    # Test different bond characteristics
    test_cases = [
        {'rating': 'AAA', 'credit_spread': 0.002},  # 20 bps - high grade
        {'rating': 'A', 'credit_spread': 0.008},     # 80 bps - investment grade
        {'rating': 'BBB', 'credit_spread': 0.015},   # 150 bps - lower IG
        {'rating': 'BB', 'credit_spread': 0.035},    # 350 bps - high yield
    ]
    
    print("\nVolatility by Credit Quality:")
    print("-" * 50)
    print("Rating | Spread | 1Y Vol | 3Y Vol | 5Y Vol")
    print("-" * 50)
    
    for case in test_cases:
        vol_1y = calibrator.get_volatility(1.0, 1.0, case)
        vol_3y = calibrator.get_volatility(3.0, 1.0, case)
        vol_5y = calibrator.get_volatility(5.0, 1.0, case)
        
        print(f"{case['rating']:6} | {case['credit_spread']*10000:4.0f}bp | "
              f"{vol_1y*100:5.1f}% | {vol_3y*100:5.1f}% | {vol_5y*100:5.1f}%")
    
    print("\nVolatility Smile Effect (3Y option):")
    print("-" * 50)
    print("Moneyness | Volatility | Description")
    print("-" * 50)
    
    moneyness_levels = [
        (0.85, "Deep OTM"),
        (0.95, "OTM"),
        (1.00, "ATM"),
        (1.05, "ITM"),
        (1.15, "Deep ITM")
    ]
    
    for moneyness, desc in moneyness_levels:
        vol = calibrator.get_volatility(3.0, moneyness, {'rating': 'A'})
        print(f"{moneyness:9.2f} | {vol*100:10.1f}% | {desc}")


if __name__ == "__main__":
    print("\n" + "█" * 70)
    print("█" + " " * 20 + "OAS ENHANCEMENT TEST SUITE" + " " * 22 + "█")
    print("█" * 70)
    
    # Run comparison
    results = compare_oas_methods()
    
    # Test volatility calibration
    test_volatility_calibration()
    
    print("\n" + "█" * 70)
    print("█" + " " * 25 + "TEST COMPLETE" + " " * 30 + "█")
    print("█" * 70)
    print("\nThe enhanced OAS calculation provides more accurate pricing by:")
    print("• Using market-calibrated volatility instead of fixed 20%")
    print("• Considering all call dates, not just the first")
    print("• Adjusting volatility for credit quality and term structure")
    print("• Offering binomial tree pricing for American-style optionality")
    print("")
