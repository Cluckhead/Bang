#!/usr/bin/env python
"""Test that all named ranges are properly defined in the Excel workbook"""

from bond_calculation.excel.workbook import build_workbook
from datetime import datetime

# Create minimal test data
bond_data = {
    'reference': {
        'ISIN': 'TEST123',
        'Security Name': 'Test Bond',
        'Coupon Rate': 2.5,
        'Currency': 'USD'
    },
    'schedule': {
        'Maturity Date': datetime(2025, 12, 31),
        'Day Basis': 'ACT/ACT',
        'Coupon Frequency': 2,
        'Issue Date': datetime(2020, 1, 1),
        'First Coupon': datetime(2020, 6, 30)
    }
}

cashflows = [
    {
        'date': datetime(2025, 6, 30),
        'time_years': 0.5,
        'coupon': 1.25,
        'principal': 0,
        'total': 1.25,
        'accrual_period': 0.5
    },
    {
        'date': datetime(2025, 12, 31),
        'time_years': 1.0,
        'coupon': 1.25,
        'principal': 100,
        'total': 101.25,
        'accrual_period': 0.5
    }
]

curve_data = ([0.5, 1, 2, 3], [4.5, 4.6, 4.7, 4.8])

python_results = {
    'ytm': 0.045,
    'z_spread': 0.01,
    'g_spread': 0.009,
    'effective_duration': 7.25,
    'modified_duration': 7.15,
    'convexity': 62.3,
    'present_value': 98.75,
    'calculated': True,
    'oas_standard': None,
    'oas_enhanced': None
}

try:
    print("Creating workbook with named ranges...")
    wb = build_workbook(
        bond_data=bond_data,
        cashflows=cashflows,
        curve_data=curve_data,
        price=98.5,
        valuation_date=datetime(2024, 12, 1),
        python_results=python_results
    )
    
    # Check named ranges
    print("\nNamed ranges defined:")
    print("-" * 40)
    
    expected_ranges = [
        'Sel_ISIN', 'Sel_ValDate', 'Sel_Currency', 'Sel_Freq', 
        'Sel_DayBasis', 'Sel_Compounding', 'Sel_Settlement',
        'Sel_KRDBumpBps', 'Sel_SpreadBps',
        'Price_Clean', 'Price_Accrued', 'Price_Dirty',
        'Coupon_Rate', 'Notional', 'Frequency', 'Maturity',
        'Curve_Terms', 'Curve_Rates',
        'Assump_Frequency', 'Assump_Basis', 'Assump_Basis_Code'
    ]
    
    for name in expected_ranges:
        if name in wb.defined_names:
            print(f"✓ {name}: {wb.defined_names[name].attr_text}")
        else:
            print(f"✗ {name}: NOT FOUND")
    
    # Check YTM sheet for the formula
    ytm_sheet = wb['YTM_Calculations']
    print("\nChecking YTM sheet formulas...")
    
    # Find the YIELD formula cell (should be around row 85-86)
    for row in range(1, min(100, ytm_sheet.max_row + 1)):
        cell_value = ytm_sheet.cell(row=row, column=2).value
        if cell_value and isinstance(cell_value, str) and 'YIELD' in cell_value:
            print(f"Row {row}: {cell_value}")
            # Check if it references Coupon_Rate
            if 'Coupon_Rate' in cell_value:
                print("  ✓ References Coupon_Rate named range")
            else:
                print("  ✗ Missing Coupon_Rate reference")
    
    wb.save('test_named_ranges.xlsx')
    print(f"\n✓ Workbook saved as test_named_ranges.xlsx")
    print(f"✓ Total sheets: {len(wb.worksheets)}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()