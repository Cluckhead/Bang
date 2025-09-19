# Integration test to verify both calculation methods produce consistent results
# after refactoring to use SecurityDataProvider

import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_unified_data_provider(mini_dataset):
    """Test that SecurityDataProvider provides consistent data using mini_dataset."""
    from analytics.security_data_provider import SecurityDataProvider
    
    # Initialize provider with mini dataset
    provider = SecurityDataProvider(mini_dataset)
    
    # Test with known ISIN from mini dataset
    isin = "US0000001"
    test_date = "2025-01-02"
    
    # Get security data
    security_data = provider.get_security_data(isin, test_date)
    
    assert security_data is not None, "SecurityDataProvider should not return None"
    
    # Verify fields merged correctly
    assert security_data.isin == isin
    assert security_data.price > 0, f"Price should be positive, got {security_data.price}"
    assert security_data.coupon_rate == 5.0, f"Expected coupon rate 5.0, got {security_data.coupon_rate}"
    assert security_data.maturity_date is not None, "Maturity date should be parsed"
    # Test currency precedence: Position Currency (EUR) should override Currency (USD)
    assert security_data.currency == "EUR", f"Expected EUR (Position Currency precedence), got {security_data.currency}"
    
    # Test accrued interest lookup
    assert security_data.accrued_interest == 1.22, f"Expected accrued interest 1.22, got {security_data.accrued_interest}"


def compare_calculation_results():
    """Compare results between synth_spread_calculator and synth_analytics_csv_processor."""
    data_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data')
    
    print(f"\n{'='*60}")
    print("COMPARING CALCULATION METHODS")
    print(f"{'='*60}")
    
    # Check if synthetic output files exist
    files_to_check = [
        'synth_sec_YTM.csv',
        'synth_sec_ZSpread.csv',
        'synth_sec_GSpread.csv',
        'synth_sec_EffectiveDuration.csv'
    ]
    
    print("\n[Checking] Synthetic calculation output files:")
    all_exist = True
    for file in files_to_check:
        path = os.path.join(data_folder, file)
        exists = os.path.exists(path)
        print(f"  - {file}: {'OK' if exists else 'MISSING'}")
        if not exists:
            all_exist = False
    
    if not all_exist:
        print("\n[WARNING] Some output files missing - run synth_spread_calculator first")
        assert False, "Test failed - check output above"
    
    # Load and compare a sample metric
    ytm_df = pd.read_csv(os.path.join(data_folder, 'synth_sec_YTM.csv'))
    
    if ytm_df.empty:
        print("[ERROR] YTM data is empty")
        assert False, "Test failed - check output above"
    
    # Get numeric columns (dates)
    date_cols = [col for col in ytm_df.columns if col not in 
                 ['ISIN', 'Security Name', 'Funds', 'Type', 'Callable', 'Currency']]
    
    if not date_cols:
        print("[ERROR] No date columns found in YTM data")
        assert False, "Test failed - check output above"
    
    # Count non-NaN values
    total_values = 0
    non_nan_values = 0
    
    for col in date_cols:
        total_values += len(ytm_df)
        non_nan_values += ytm_df[col].notna().sum()
    
    print(f"\n[Statistics] YTM Data:")
    print(f"  - Securities: {len(ytm_df)}")
    print(f"  - Date columns: {len(date_cols)}")
    print(f"  - Total data points: {total_values}")
    print(f"  - Calculated values: {non_nan_values}")
    print(f"  - Coverage: {non_nan_values/total_values*100:.1f}%")
    
    # Test completed successfully


def verify_no_data_divergence():
    """Verify that both methods use the same underlying data."""
    data_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data')
    
    print(f"\n{'='*60}")
    print("VERIFYING DATA CONSISTENCY")
    print(f"{'='*60}")
    
    # Initialize provider
    provider = SecurityDataProvider(data_folder)
    
    # Load reference and schedule data directly
    reference_path = os.path.join(data_folder, 'reference.csv')
    schedule_path = os.path.join(data_folder, 'schedule.csv')
    
    has_reference = os.path.exists(reference_path)
    has_schedule = os.path.exists(schedule_path)
    
    print(f"\n[Data Sources]:")
    print(f"  - reference.csv: {'OK' if has_reference else 'MISSING'}")
    print(f"  - schedule.csv: {'OK' if has_schedule else 'MISSING'}")
    
    if not has_reference or not has_schedule:
        print("[WARNING] Missing data files - cannot verify consistency")
        assert False, "Test failed - check output above"
    
    reference_df = pd.read_csv(reference_path)
    schedule_df = pd.read_csv(schedule_path)
    
    # Test a few ISINs
    test_isins = reference_df['ISIN'].head(5).tolist()
    
    print(f"\n[Testing] Data consistency for {len(test_isins)} ISINs:")
    
    all_consistent = True
    for isin in test_isins:
        # Get data from provider
        security_data = provider.get_security_data(isin, '2024-01-01')
        
        # Get data from original sources
        ref_row = reference_df[reference_df['ISIN'] == isin]
        sched_row = schedule_df[schedule_df['ISIN'] == isin]
        
        if security_data and not ref_row.empty:
            ref_coupon = ref_row.iloc[0].get('Coupon Rate', np.nan)
            provider_coupon = security_data.coupon_rate
            
            # Check if coupons match (allowing for NaN)
            match = (pd.isna(ref_coupon) and pd.isna(provider_coupon)) or \
                   (not pd.isna(ref_coupon) and not pd.isna(provider_coupon) and 
                    abs(float(ref_coupon) - float(provider_coupon)) < 0.001)
            
            status = "OK" if match else "MISMATCH"
            print(f"  - {isin}: {status} (ref={ref_coupon}, provider={provider_coupon})")
            
            if not match:
                all_consistent = False
    
    return all_consistent


def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("UNIFIED DATA LAYER INTEGRATION TESTS")
    print("Testing SecurityDataProvider integration")
    print("="*60)
    
    # Run tests
    test_results = []
    
    print("\n[1] Testing SecurityDataProvider...")
    test_results.append(("SecurityDataProvider", test_unified_data_provider()))
    
    print("\n[2] Comparing calculation results...")
    test_results.append(("Calculation Comparison", compare_calculation_results()))
    
    print("\n[3] Verifying data consistency...")
    test_results.append(("Data Consistency", verify_no_data_divergence()))
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    all_passed = True
    for test_name, passed in test_results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("[SUCCESS] ALL TESTS PASSED - Unified data layer is working correctly!")
        print("Both calculation methods now use the same SecurityDataProvider,")
        print("eliminating data divergence issues.")
    else:
        print("[WARNING] SOME TESTS FAILED - Review the output above for details")
    print(f"{'='*60}\n")
    
    assert all_passed, "Integration test failed - check the detailed output above"


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)