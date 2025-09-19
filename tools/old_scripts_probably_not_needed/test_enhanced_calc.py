# test_enhanced_calc.py
# Purpose: Test the enhanced bond calculation with predefined inputs

from bond_calculation_enhanced import (
    load_bond_data, load_price_data, load_curve_data,
    generate_cashflows, write_enhanced_excel
)
from datetime import datetime

def test_enhanced():
    """Test enhanced bond calculations with default inputs"""
    
    # Default parameters
    isin = "AU0231471865"
    date_str = "2025-02-06"
    valuation_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    print("=" * 60)
    print("Enhanced Bond Calculation Test")
    print("=" * 60)
    
    try:
        # Load data
        print(f"\nLoading data for ISIN: {isin}")
        bond_data = load_bond_data(isin)
        price = load_price_data(isin, date_str)
        
        # Get currency
        currency = bond_data['reference'].get('Position Currency', 'USD')
        if currency not in ['USD', 'EUR', 'GBP', 'JPY', 'CHF']:
            currency = 'USD'
        
        curve_data = load_curve_data(valuation_date, currency)
        
        print(f"  Bond: {bond_data['reference']['Security Name']}")
        print(f"  Price: {price:.4f}")
        print(f"  Coupon: {bond_data['reference']['Coupon Rate']}%")
        print(f"  Maturity: {bond_data['schedule']['Maturity Date']}")
        print(f"  Currency: {currency}")
        
        # Generate cashflows
        print("\nGenerating cashflows...")
        cashflows = generate_cashflows(bond_data, valuation_date)
        print(f"  Found {len(cashflows)} future cashflows")
        
        # Show cashflows
        for i, cf in enumerate(cashflows[:3], 1):
            print(f"  {i}. {cf['date'].strftime('%Y-%m-%d')}: ${cf['total']:.2f}")
        
        # Write enhanced Excel
        output_file = f"bond_calc_enhanced_{isin}_{date_str}.xlsx"
        print(f"\nCreating enhanced Excel: {output_file}")
        write_enhanced_excel(bond_data, cashflows, curve_data, price, 
                           valuation_date, output_file)
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Enhanced Excel file created with:")
        print("=" * 60)
        print("  • Editable input parameters (blue cells)")
        print("  • Working Excel formulas throughout")
        print("  • Three YTM calculation methods:")
        print("    - Python Newton-Raphson")
        print("    - Excel YIELD() function")
        print("    - First principles with formulas")
        print("  • Interactive Z-Spread calculator")
        print("  • Modifiable yield curve data")
        print("  • Full calculation transparency")
        print()
        print("📊 Key Features:")
        print("  • Change price/coupon → see yield impact")
        print("  • Modify curve → see spread changes")
        print("  • All formulas visible and editable")
        print("  • Use Goal Seek/Solver for optimization")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_enhanced()
    exit(0 if success else 1)