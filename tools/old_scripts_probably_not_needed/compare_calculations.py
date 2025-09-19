#!/usr/bin/env python
"""Compare bond calculations between Excel path and synth analytics CSV path"""

import pandas as pd
from datetime import datetime
import os

# Import both calculation paths
from bond_calculation.bond_calculation_excel import (
    load_bond_data as excel_load_bond_data,
    generate_cashflows as excel_generate_cashflows,
    calculate_spreads_durations_and_oas as excel_calculate_analytics
)

from analytics.synth_analytics_csv_processor import (
    calculate_all_analytics_for_security,
    load_supporting_data
)

def compare_calculations_for_isin(isin: str, price: float, valuation_date: datetime, data_folder: str):
    """Compare calculations between Excel and synth paths for a specific bond"""
    
    print(f"\nComparing calculations for {isin}")
    print("=" * 60)
    
    # Excel path calculation
    print("\n1. EXCEL PATH:")
    try:
        # Load bond data
        bond_data = excel_load_bond_data(isin)
        print(f"   Coupon Rate: {bond_data['reference']['Coupon Rate']}%")
        print(f"   Maturity: {bond_data['schedule']['Maturity Date']}")
        print(f"   Frequency: {bond_data['schedule']['Coupon Frequency']}")
        
        # Generate cashflows
        cashflows = excel_generate_cashflows(bond_data, valuation_date)
        print(f"   Cashflows count: {len(cashflows)}")
        
        # Show final cashflow
        if cashflows:
            final_cf = cashflows[-1]
            print(f"   Final CF: Date={final_cf['date']}, Total={final_cf.get('total', 0):.2f}")
            print(f"            Coupon={final_cf.get('coupon', 0):.2f}, Principal={final_cf.get('principal', 0):.2f}")
        
        # Load curve data
        from bond_calculation.bond_calculation_excel import load_curve_data
        currency = bond_data['reference'].get('Position Currency', 'USD')
        times, rates = load_curve_data(valuation_date, currency)
        curve_data = (times, rates)
        
        # Calculate analytics
        results = excel_calculate_analytics(price, cashflows, curve_data, valuation_date, bond_data)
        print(f"\n   Excel Results:")
        print(f"   YTM: {results['ytm']:.6f} ({results['ytm']*100:.4f}%)")
        print(f"   Z-Spread: {results['z_spread']*10000:.2f} bps")
        print(f"   Duration: {results['effective_duration']:.4f}")
        print(f"   Convexity: {results['convexity']:.2f}")
        
    except Exception as e:
        print(f"   Error in Excel path: {e}")
        import traceback
        traceback.print_exc()
    
    # Synth analytics path
    print("\n2. SYNTH ANALYTICS PATH:")
    try:
        # Load data files
        schedule_df, reference_df, curves_df, accrued_df = load_supporting_data(data_folder)
        
        # Get price row
        price_path = os.path.join(data_folder, 'sec_Price.csv')
        price_df = pd.read_csv(price_path)
        price_row = price_df[price_df['ISIN'] == isin].iloc[0] if not price_df[price_df['ISIN'] == isin].empty else None
        
        if price_row is None:
            print("   Could not find security in sec_Price.csv")
            return
        
        # Calculate analytics
        latest_date = valuation_date.strftime('%Y-%m-%d')
        analytics = calculate_all_analytics_for_security(
            price_row, price, latest_date, schedule_df, reference_df, curves_df, accrued_df
        )
        
        print(f"\n   Synth Results:")
        print(f"   YTM: {analytics.get('YTM', 'N/A')}")
        print(f"   Z-Spread: {analytics.get('Z_Spread', 'N/A')}")
        print(f"   Duration: {analytics.get('Effective_Duration', 'N/A')}")
        print(f"   Convexity: {analytics.get('Convexity', 'N/A')}")
        
    except Exception as e:
        print(f"   Error in Synth path: {e}")
        import traceback
        traceback.print_exc()
    
    # Show differences
    print("\n3. DIFFERENCES:")
    try:
        if 'results' in locals() and 'analytics' in locals():
            ytm_diff = results['ytm'] - float(analytics.get('YTM', 0))
            print(f"   YTM diff: {ytm_diff:.6f} ({ytm_diff*100:.4f}%)")
            
            z_spread_excel = results['z_spread'] * 10000
            z_spread_synth = float(analytics.get('Z_Spread', 0))
            z_diff = z_spread_excel - z_spread_synth
            print(f"   Z-Spread diff: {z_diff:.2f} bps")
            
            dur_diff = results['effective_duration'] - float(analytics.get('Effective_Duration', 0))
            print(f"   Duration diff: {dur_diff:.4f}")
    except:
        print("   Could not calculate differences")


if __name__ == "__main__":
    # Test with a specific bond
    data_folder = r"C:\Users\cluck\Code\Simple Data Checker\Data"
    
    # Example: Test with a specific ISIN
    test_isin = "SE8307649464"  # Replace with your actual ISIN
    test_price = 98.5
    test_date = datetime(2024, 12, 1)
    
    compare_calculations_for_isin(test_isin, test_price, test_date, data_folder)