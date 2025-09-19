# test_bond_calc.py
# Purpose: Test the bond calculation script with predefined inputs

import sys
from datetime import datetime

# Import the main calculation module
from bond_calculation_test import (
    load_bond_data, load_price_data, load_curve_data,
    generate_cashflows, calculate_ytm, calculate_zspread, 
    calculate_gspread, write_to_excel, COMPOUNDING
)

def test_calculation():
    """Test bond calculations with a specific ISIN and date"""
    
    # Test parameters
    isin = "AU0231471865"  # ISIN that exists in both reference and schedule data
    date_str = "2025-02-06"
    valuation_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    print("=" * 60)
    print("Bond Calculation Test - Automated")
    print("=" * 60)
    
    try:
        # Load data
        print(f"\n1. Loading data for ISIN: {isin}")
        bond_data = load_bond_data(isin)
        price = load_price_data(isin, date_str)
        
        # Get currency
        currency = bond_data['reference'].get('Position Currency', 'USD')
        if currency not in ['USD', 'EUR', 'GBP', 'JPY', 'CHF']:
            currency = 'USD'
        
        curve_data = load_curve_data(valuation_date, currency)
        
        print(f"   Bond: {bond_data['reference']['Security Name']}")
        print(f"   Clean Price: {price:.4f}")
        print(f"   Coupon Rate: {bond_data['reference']['Coupon Rate']}%")
        print(f"   Maturity: {bond_data['schedule']['Maturity Date']}")
        print(f"   Currency: {currency}")
        print(f"   Day Count: {bond_data['schedule']['Day Basis']}")
        
        # Generate cashflows
        print("\n2. Generating cashflows...")
        cashflows = generate_cashflows(bond_data, valuation_date)
        print(f"   Found {len(cashflows)} future cashflows")
        
        # Show first few cashflows
        print("\n   First 3 cashflows:")
        for i, cf in enumerate(cashflows[:3]):
            print(f"   {i+1}. Date: {cf['date'].strftime('%Y-%m-%d')}, "
                  f"Amount: {cf['total']:.4f}, Time: {cf['time_years']:.4f} years")
        
        # Calculate YTM
        print("\n3. Calculating YTM...")
        ytm_result = calculate_ytm(price, cashflows, COMPOUNDING)
        print(f"   YTM: {ytm_result['ytm']*100:.4f}%")
        print(f"   Converged: {ytm_result['converged']}")
        print(f"   Iterations: {len(ytm_result['iterations'])}")
        
        # Calculate Z-Spread
        print("\n4. Calculating Z-Spread...")
        zspread_result = calculate_zspread(price, cashflows, curve_data[0], curve_data[1], COMPOUNDING)
        print(f"   Z-Spread: {zspread_result['zspread']*10000:.2f} bps")
        print(f"   Converged: {zspread_result['converged']}")
        
        # Calculate G-Spread
        print("\n5. Calculating G-Spread...")
        maturity_years = cashflows[-1]['time_years']
        gspread_result = calculate_gspread(ytm_result['ytm'], maturity_years, 
                                          curve_data[0], curve_data[1])
        print(f"   G-Spread: {gspread_result['gspread']*10000:.2f} bps")
        print(f"   Government Rate at Maturity: {gspread_result['govt_rate']*100:.4f}%")
        
        # Write to Excel
        output_file = f"bond_calc_test_{isin}_{date_str}.xlsx"
        print(f"\n6. Writing results to Excel: {output_file}")
        write_to_excel(bond_data, cashflows, ytm_result, zspread_result, gspread_result,
                      curve_data, price, valuation_date, output_file)
        
        print("\n" + "=" * 60)
        print("TEST COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        
        # Print summary
        print("\nSUMMARY OF RESULTS:")
        print(f"  ISIN:        {isin}")
        print(f"  Date:        {date_str}")
        print(f"  Price:       {price:.4f}")
        print(f"  YTM:         {ytm_result['ytm']*100:.4f}%")
        print(f"  Z-Spread:    {zspread_result['zspread']*10000:.2f} bps")
        print(f"  G-Spread:    {gspread_result['gspread']*10000:.2f} bps")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_calculation()
    sys.exit(0 if success else 1)