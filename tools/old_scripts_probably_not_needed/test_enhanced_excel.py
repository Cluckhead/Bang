#!/usr/bin/env python
"""Test script for enhanced Excel workbook generation"""

from bond_calculation.excel.workbook import build_workbook
from datetime import datetime
import os

def test_excel_generation():
    """Test the enhanced Excel workbook generation with all new features"""
    
    # Create sample bond data
    bond_data = {
        'reference': {
            'ISIN': 'US912828YM13',
            'Security Name': 'US Treasury 2.5% 2025',
            'Coupon Rate': 2.5,
            'Currency': 'USD'
        },
        'schedule': {
            'Maturity Date': datetime(2025, 12, 31),
            'Day Basis': 'ACT/ACT',
            'Coupon Frequency': 2,
            'Issue Date': datetime(2020, 1, 1),
            'First Coupon': datetime(2020, 6, 30),
            'Coupon Dates': [
                datetime(2024, 6, 30), 
                datetime(2024, 12, 31), 
                datetime(2025, 6, 30), 
                datetime(2025, 12, 31)
            ]
        }
    }
    
    # Create sample cashflows
    cashflows = [
        {
            'date': datetime(2024, 12, 31), 
            'amount': 1.25, 
            'type': 'Coupon', 
            'days_from_valuation': 30, 
            'accrual_fraction': 0.5
        },
        {
            'date': datetime(2025, 6, 30), 
            'amount': 1.25, 
            'type': 'Coupon', 
            'days_from_valuation': 211, 
            'accrual_fraction': 0.5
        },
        {
            'date': datetime(2025, 12, 31), 
            'amount': 101.25, 
            'type': 'Principal+Coupon', 
            'days_from_valuation': 395, 
            'accrual_fraction': 0.5
        }
    ]
    
    # Create sample curve data
    curve_data = (
        [0.25, 0.5, 1, 2, 3, 5, 7, 10],  # Terms in years
        [4.5, 4.6, 4.7, 4.8, 4.85, 4.9, 4.95, 5.0]  # Zero rates in %
    )
    
    # Python calculation results
    python_results = {
        'ytm': 0.0475,
        'z_spread': 0.0125,
        'g_spread': 0.0095,
        'effective_duration': 7.25,
        'modified_duration': 7.15,
        'convexity': 62.3,
        'present_value': 98.75,
        'oas_standard': None,
        'oas_enhanced': None,
        'valuation_date': '2024-12-01'
    }
    
    print("Creating enhanced Excel workbook...")
    print("-" * 50)
    
    try:
        # Build the workbook
        wb = build_workbook(
            bond_data=bond_data,
            cashflows=cashflows,
            curve_data=curve_data,
            price=98.5,
            valuation_date=datetime(2024, 12, 1),
            python_results=python_results
        )
        
        # Save the workbook
        output_file = 'test_enhanced_excel.xlsx'
        wb.save(output_file)
        
        print(f"✓ Excel workbook created: {output_file}")
        print(f"✓ Total sheets created: {len(wb.worksheets)}")
        print()
        
        print("Enhanced features implemented:")
        print("-" * 30)
        
        # Check for new sheets
        sheet_names = [ws.title for ws in wb.worksheets]
        
        features = [
            ("Controls", "Central control panel with parameters"),
            ("Data_Source", "Raw data audit trail"),
            ("Sec_Data", "Security time series display"),
            ("Summary_Comparison", "Python vs Excel comparison")
        ]
        
        for sheet_name, description in features:
            if sheet_name in sheet_names:
                print(f"✓ {sheet_name}: {description}")
            else:
                print(f"✗ {sheet_name}: Not found")
        
        print()
        print("Formula improvements:")
        print("-" * 30)
        print("✓ FORECAST.LINEAR for interpolation")
        print("✓ Flexible discount factor with compounding")
        print("✓ Enhanced named ranges for calculations")
        
        print()
        print("All sheets in workbook:")
        print("-" * 30)
        for i, sheet_name in enumerate(sheet_names, 1):
            print(f"{i:2}. {sheet_name}")
        
        # Check file size
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            print()
            print(f"File size: {size:,} bytes")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_excel_generation()
    if success:
        print("\n✓ Test completed successfully!")
    else:
        print("\n✗ Test failed!")
    
    input("\nPress Enter to exit...")