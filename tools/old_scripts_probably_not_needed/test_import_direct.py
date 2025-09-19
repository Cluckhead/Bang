#!/usr/bin/env python
"""Direct import test"""

try:
    # Test the imports
    print("Testing imports...")
    from bond_calculation.excel.sheets.data_source import add_data_source_sheet
    print("✓ data_source imported")
    
    from bond_calculation.excel.sheets.controls import add_controls_sheet
    print("✓ controls imported")
    
    from bond_calculation.excel.sheets.sec_data import add_sec_data_sheet
    print("✓ sec_data imported")
    
    from bond_calculation.excel.sheets.summary_comparison import add_summary_comparison_sheet
    print("✓ summary_comparison imported")
    
    from bond_calculation.excel.workbook import build_workbook
    print("✓ workbook imported")
    
    # Test with minimal data
    from datetime import datetime
    
    # Minimal cashflow matching actual structure
    test_cf = {
        'date': datetime(2025, 6, 30),
        'time_years': 0.5,
        'coupon': 1.25,
        'principal': 0,
        'total': 1.25,
        'accrual_period': 0.5
    }
    
    print(f"\nTest cashflow structure:")
    print(f"  Keys: {list(test_cf.keys())}")
    print(f"  Total: {test_cf.get('total')}")
    print(f"  Amount: {test_cf.get('amount', 'NOT FOUND - using total')}")
    
    print("\n✓ All imports successful!")
    
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()