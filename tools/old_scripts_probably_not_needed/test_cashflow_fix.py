#!/usr/bin/env python
"""Test that the Excel generation works with actual cashflow structure"""

import sys
import os
os.chdir(r'C:\Users\cluck\Code\Simple Data Checker')

from bond_calculation.excel.workbook import build_workbook
from datetime import datetime

# Create test data matching actual cashflow structure
bond_data = {
    'reference': {
        'ISIN': 'SE8307649464',
        'Security Name': 'Test Bond',
        'Coupon Rate': 2.5,
        'Currency': 'USD'
    },
    'schedule': {
        'Maturity Date': datetime(2025, 12, 31),
        'Day Basis': 'ACT/ACT',
        'Coupon Frequency': 2
    }
}

# Cashflows matching the actual structure from generate_cashflows
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
    'present_value': 98.75
}

try:
    print("Testing Excel generation with actual cashflow structure...")
    wb = build_workbook(
        bond_data=bond_data,
        cashflows=cashflows,
        curve_data=curve_data,
        price=98.5,
        valuation_date=datetime(2024, 12, 1),
        python_results=python_results
    )
    
    wb.save('test_cashflow_fix.xlsx')
    print("✓ Excel file created successfully!")
    print("✓ Cashflow structure handled correctly")
    
    # Check specific sheets
    for sheet in wb.worksheets:
        if sheet.title == "Data_Source":
            print(f"✓ Data_Source sheet created with {sheet.max_row} rows")
        elif sheet.title == "Cashflows":
            print(f"✓ Cashflows sheet created with {sheet.max_row-1} cashflows")
            
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()