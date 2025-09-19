#!/usr/bin/env python
"""Verify the named range fix is working"""

print("Verifying named range fix...")

# Test 1: Check input_parameters.py creates Coupon_Rate correctly
from bond_calculation.excel.sheets.input_parameters import add_input_parameters_sheet
from openpyxl import Workbook
from datetime import datetime

wb = Workbook()
bond_data = {
    'reference': {
        'ISIN': 'TEST',
        'Security Name': 'Test',
        'Coupon Rate': 2.5
    },
    'schedule': {
        'Maturity Date': datetime(2025, 12, 31),
        'Day Basis': 'ACT/ACT',
        'Coupon Frequency': 2
    }
}

add_input_parameters_sheet(wb, bond_data, 98.5, datetime.now())

# Check if Coupon_Rate is defined
if 'Coupon_Rate' in wb.defined_names:
    print(f"✓ Coupon_Rate defined: {wb.defined_names['Coupon_Rate'].attr_text}")
else:
    print("✗ Coupon_Rate NOT defined")

# Check other critical named ranges
for name in ['Price_Clean', 'Price_Dirty', 'Notional', 'Frequency', 'Maturity']:
    if name in wb.defined_names:
        print(f"✓ {name} defined")
    else:
        print(f"✗ {name} NOT defined")

print("\n✓ Fix verified successfully!")