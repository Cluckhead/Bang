"""
Comprehensive verification script for SpreadOMatic accuracy.
Tests mathematical calculations, identifies potential issues, and validates against known results.
"""

import sys
import os
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
import traceback

# Add SpreadOMatic to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from SpreadOMatic.spreadomatic import (
    yield_spread,
    daycount,
    cashflows,
    discount,
    ytw,
    interpolation
)

class SpreadOMaticVerifier:
    """Comprehensive verification of SpreadOMatic calculations."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed_tests = 0
        self.failed_tests = 0
        
    def log_error(self, test_name: str, message: str):
        """Log an error found during testing."""
        self.errors.append(f"ERROR in {test_name}: {message}")
        self.failed_tests += 1
        
    def log_warning(self, test_name: str, message: str):
        """Log a warning found during testing."""
        self.warnings.append(f"WARNING in {test_name}: {message}")
        
    def log_pass(self, test_name: str):
        """Log a passed test."""
        self.passed_tests += 1
        print(f"[PASS] {test_name}")
        
    def assert_close(self, actual: float, expected: float, tolerance: float, test_name: str, desc: str = ""):
        """Assert two values are close within tolerance."""
        diff = abs(actual - expected)
        if diff > tolerance:
            self.log_error(test_name, f"{desc}: Expected {expected:.8f}, got {actual:.8f}, diff={diff:.8f}")
            return False
        else:
            return True
            
    def test_daycount_conventions(self):
        """Test accuracy of day count conventions."""
        print("\n=== Testing Day Count Conventions ===")
        
        # Test cases with known results
        start = datetime(2024, 1, 15)
        end = datetime(2024, 7, 15)
        
        test_cases = [
            ("30/360", start, end, 0.5),  # Exactly 6 months in 30/360
            ("ACT/360", start, end, (end - start).days / 360.0),
            ("ACT/365", start, end, (end - start).days / 365.0),
        ]
        
        for basis, s, e, expected in test_cases:
            try:
                actual = daycount.year_fraction(s, e, basis)
                if self.assert_close(actual, expected, 0.0001, f"daycount_{basis}", f"{basis} calculation"):
                    self.log_pass(f"Day count {basis}")
            except Exception as ex:
                self.log_error(f"daycount_{basis}", str(ex))
                
        # Test ACT/ACT across year boundary (known issue area)
        start = datetime(2023, 10, 1)
        end = datetime(2024, 4, 1)
        
        # ACT/ACT should handle leap year correctly
        actual = daycount.year_fraction(start, end, "ACT/ACT")
        # Oct-Dec 2023: 92 days / 365 = 0.252055
        # Jan-Mar 2024: 91 days / 366 = 0.248634
        expected = 92/365 + 91/366
        
        if not self.assert_close(actual, expected, 0.001, "ACT/ACT_leap", "Leap year handling"):
            self.log_warning("ACT/ACT", "Potential issue with leap year calculation across year boundary")
            
    def test_ytm_calculation(self):
        """Test YTM calculation accuracy."""
        print("\n=== Testing YTM Calculation ===")
        
        # Simple test case: bond at par should have YTM = coupon rate
        price = 100.0
        times = [0.5, 1.0, 1.5, 2.0]
        cfs = [2.5, 2.5, 2.5, 102.5]  # 5% annual coupon, semi-annual payments
        
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="semiannual")
            expected_ytm = 0.05  # 5% YTM for bond at par
            
            if self.assert_close(ytm, expected_ytm, 0.0001, "YTM_at_par", "Bond at par"):
                self.log_pass("YTM at par")
        except Exception as ex:
            self.log_error("YTM_at_par", str(ex))
            
        # Test premium bond (price > par)
        price = 105.0
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="semiannual")
            # YTM should be less than coupon rate for premium bond
            if ytm >= 0.05:
                self.log_error("YTM_premium", f"Premium bond YTM {ytm:.4f} should be < coupon rate 0.05")
            else:
                self.log_pass("YTM premium bond")
        except Exception as ex:
            self.log_error("YTM_premium", str(ex))
            
        # Test discount bond (price < par)
        price = 95.0
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="semiannual")
            # YTM should be greater than coupon rate for discount bond
            if ytm <= 0.05:
                self.log_error("YTM_discount", f"Discount bond YTM {ytm:.4f} should be > coupon rate 0.05")
            else:
                self.log_pass("YTM discount bond")
        except Exception as ex:
            self.log_error("YTM_discount", str(ex))
            
    def test_z_spread_calculation(self):
        """Test Z-spread calculation accuracy."""
        print("\n=== Testing Z-Spread Calculation ===")
        
        # Test case: Z-spread should be 0 when price matches PV from curve
        price = 100.0
        times = [0.5, 1.0, 1.5, 2.0]
        cfs = [2.5, 2.5, 2.5, 102.5]
        
        # Flat yield curve at 5%
        zero_times = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
        zero_rates = [0.05, 0.05, 0.05, 0.05, 0.05, 0.05]
        
        try:
            # First calculate what price should be with zero spread
            pv = discount.pv_cashflows(times, cfs, zero_times, zero_rates, comp="semiannual")
            
            # Now solve for z-spread using that price
            z_spread = yield_spread.z_spread(pv, times, cfs, zero_times, zero_rates, comp="semiannual")
            
            if self.assert_close(z_spread, 0.0, 0.0001, "Z_spread_zero", "Z-spread for matched price"):
                self.log_pass("Z-spread zero case")
        except Exception as ex:
            self.log_error("Z_spread_zero", str(ex))
            
        # Test non-zero spread case
        price = 98.0  # Lower price should require positive spread
        try:
            z_spread = yield_spread.z_spread(price, times, cfs, zero_times, zero_rates, comp="semiannual")
            
            if z_spread <= 0:
                self.log_error("Z_spread_positive", f"Lower price should give positive spread, got {z_spread:.4f}")
            else:
                # Verify the spread gives correct price
                pv_check = discount.pv_cashflows(times, cfs, zero_times, zero_rates, 
                                                spread=z_spread, comp="semiannual")
                if self.assert_close(pv_check, price, 0.01, "Z_spread_verify", "Z-spread price recovery"):
                    self.log_pass("Z-spread positive case")
        except Exception as ex:
            self.log_error("Z_spread_positive", str(ex))
            
    def test_g_spread_calculation(self):
        """Test G-spread calculation accuracy."""
        print("\n=== Testing G-Spread Calculation ===")
        
        # G-spread = YTM - interpolated risk-free rate
        ytm = 0.06  # 6% YTM
        maturity = 5.0  # 5 years
        
        # Government curve
        zero_times = [0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
        zero_rates = [0.03, 0.035, 0.04, 0.042, 0.045, 0.047, 0.05]
        
        try:
            g_spread = yield_spread.g_spread(ytm, maturity, zero_times, zero_rates)
            
            # Expected: 0.06 - 0.045 = 0.015
            expected = ytm - 0.045
            
            if self.assert_close(g_spread, expected, 0.0001, "G_spread_basic", "Basic G-spread"):
                self.log_pass("G-spread calculation")
        except Exception as ex:
            self.log_error("G_spread_basic", str(ex))
            
    def test_cashflow_generation(self):
        """Test cashflow generation accuracy."""
        print("\n=== Testing Cashflow Generation ===")
        
        issue_date = datetime(2020, 1, 15)
        first_coupon = datetime(2020, 7, 15)
        maturity = datetime(2025, 1, 15)
        coupon_rate = 0.05
        
        try:
            schedule = cashflows.generate_fixed_schedule(
                issue_date=issue_date,
                first_coupon_date=first_coupon,
                maturity_date=maturity,
                coupon_rate=coupon_rate,
                day_basis="30/360",
                currency="USD",
                notional=100.0,
                coupon_frequency=2  # Semi-annual
            )
            
            # Should have 10 coupons (5 years * 2) with last including principal
            expected_coupons = 10
            if len(schedule) != expected_coupons:
                self.log_error("Cashflow_count", f"Expected {expected_coupons} payments, got {len(schedule)}")
            else:
                # Check coupon amounts (should be 2.5 for semi-annual 5% coupon)
                for i, payment in enumerate(schedule[:-1]):
                    expected_amount = 2.5
                    actual_amount = payment.get('amount', 0)
                    if abs(actual_amount - expected_amount) > 0.01:
                        self.log_warning("Cashflow_amount", 
                                       f"Payment {i+1}: expected {expected_amount}, got {actual_amount}")
                
                # Last payment should include principal
                last_payment = schedule[-1].get('amount', 0)
                expected_last = 102.5
                if abs(last_payment - expected_last) > 0.01:
                    self.log_error("Cashflow_final", 
                                 f"Final payment: expected {expected_last}, got {last_payment}")
                else:
                    self.log_pass("Cashflow generation")
                    
        except Exception as ex:
            self.log_error("Cashflow_generation", str(ex))
            
    def test_discount_factors(self):
        """Test discount factor calculations."""
        print("\n=== Testing Discount Factors ===")
        
        rate = 0.05
        time = 1.0
        
        test_cases = [
            ("annual", 1/(1.05)**1, "Annual compounding"),
            ("semiannual", 1/(1.025)**2, "Semi-annual compounding"),
            ("continuous", np.exp(-0.05), "Continuous compounding"),
        ]
        
        for comp, expected, desc in test_cases:
            try:
                df = discount.discount_factor(rate, time, comp)
                if self.assert_close(df, expected, 0.00001, f"DF_{comp}", desc):
                    self.log_pass(f"Discount factor {comp}")
            except Exception as ex:
                self.log_error(f"DF_{comp}", str(ex))
                
    def test_ytw_calculation(self):
        """Test Yield to Worst calculation."""
        print("\n=== Testing YTW Calculation ===")
        
        # Create a callable bond scenario
        dirty_price = 102.0
        valuation_date = datetime(2024, 1, 15)
        settlement_date = datetime(2024, 1, 17)
        
        # Simple cashflows to maturity
        maturity_cfs = [(0.5, 2.5), (1.0, 2.5), (1.5, 2.5), (2.0, 102.5)]
        
        # Call schedule
        call_schedule = [
            {'date': '2025-01-15', 'price': 101.0},  # Callable at 101 in 1 year
            {'date': '2025-07-15', 'price': 100.5},  # Callable at 100.5 in 1.5 years
        ]
        
        try:
            result = ytw.calculate_ytw(
                cashflows=maturity_cfs,
                dirty_price=dirty_price,
                call_schedule=call_schedule,
                valuation_date=valuation_date,
                settlement_date=settlement_date,
                coupon_rate=0.05,
                frequency=2,
                principal=100.0,
                day_basis="30/360",
                compounding=2
            )
            
            if result['ytw'] is not None:
                # YTW should be the lowest yield
                if result['all_yields']:
                    yields = [y['yield'] for y in result['all_yields']]
                    min_yield = min(yields)
                    
                    if abs(result['ytw'] - min_yield) > 0.0001:
                        self.log_error("YTW_min", f"YTW {result['ytw']:.4f} != min yield {min_yield:.4f}")
                    else:
                        self.log_pass("YTW calculation")
            else:
                self.log_warning("YTW", "YTW returned None")
                
        except Exception as ex:
            self.log_error("YTW_calculation", str(ex))
            
    def test_interpolation(self):
        """Test interpolation accuracy."""
        print("\n=== Testing Interpolation ===")
        
        x_points = [0.0, 1.0, 2.0, 3.0, 5.0]
        y_points = [0.02, 0.025, 0.03, 0.032, 0.035]
        
        # Test exact point
        result = interpolation.linear_interpolate(x_points, y_points, 2.0)
        if self.assert_close(result, 0.03, 0.00001, "Interp_exact", "Exact point"):
            self.log_pass("Interpolation exact point")
            
        # Test between points
        result = interpolation.linear_interpolate(x_points, y_points, 1.5)
        expected = 0.025 + (0.03 - 0.025) * 0.5  # Halfway between 0.025 and 0.03
        if self.assert_close(result, expected, 0.00001, "Interp_between", "Between points"):
            self.log_pass("Interpolation between points")
            
        # Test extrapolation (flat)
        result = interpolation.linear_interpolate(x_points, y_points, 10.0)
        if self.assert_close(result, 0.035, 0.00001, "Interp_extrap", "Extrapolation"):
            self.log_pass("Interpolation extrapolation")
            
    def test_edge_cases(self):
        """Test edge cases and potential error conditions."""
        print("\n=== Testing Edge Cases ===")
        
        # Test zero coupon bond
        price = 90.0
        times = [1.0]
        cfs = [100.0]  # Zero coupon bond
        
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="annual")
            # YTM = (100/90)^(1/1) - 1 ≈ 0.1111
            expected = (100.0/90.0) - 1
            if self.assert_close(ytm, expected, 0.001, "ZCB_YTM", "Zero coupon bond YTM"):
                self.log_pass("Zero coupon bond YTM")
        except Exception as ex:
            self.log_error("ZCB_YTM", str(ex))
            
        # Test very short maturity
        price = 99.5
        times = [0.01]  # Very short maturity
        cfs = [100.0]
        
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="annual")
            # Should handle without error
            self.log_pass("Short maturity YTM")
        except Exception as ex:
            self.log_error("Short_maturity", str(ex))
            
        # Test negative yields
        price = 101.0
        times = [1.0]
        cfs = [100.0]  # Price above par for zero coupon
        
        try:
            ytm = yield_spread.solve_ytm(price, times, cfs, comp="annual")
            if ytm >= 0:
                self.log_error("Negative_yield", f"Should get negative yield, got {ytm:.4f}")
            else:
                self.log_pass("Negative yield handling")
        except Exception as ex:
            self.log_error("Negative_yield", str(ex))
            
    def identify_potential_issues(self):
        """Identify specific potential issues in the code."""
        print("\n=== Identified Potential Issues ===")
        
        issues = []
        
        # Issue 1: YTW calculation with irregular periods
        issues.append({
            'severity': 'MEDIUM',
            'location': 'ytw.py:generate_cashflows_to_call',
            'issue': 'Simplified coupon date generation may not match actual bond schedules',
            'impact': 'YTW calculations may be inaccurate for bonds with irregular first/last coupons',
            'recommendation': 'Use actual payment schedule from schedule.csv when available'
        })
        
        # Issue 2: Day count convention edge cases
        issues.append({
            'severity': 'LOW',
            'location': 'daycount.py:year_fraction',
            'issue': 'ACT/ACT implementation may have minor discrepancies with ISDA standard',
            'impact': 'Small differences (< 1bp) in accrued interest calculations',
            'recommendation': 'Validate against ISDA documentation for edge cases'
        })
        
        # Issue 3: G-spread compounding assumption
        issues.append({
            'severity': 'MEDIUM',
            'location': 'yield_spread.py:g_spread',
            'issue': 'G-spread assumes same compounding for YTM and zero rate when not continuous',
            'impact': 'May give incorrect spreads when YTM and curve have different compounding',
            'recommendation': 'Always convert to same compounding convention before subtraction'
        })
        
        # Issue 4: Cashflow generation frequency handling
        issues.append({
            'severity': 'HIGH',
            'location': 'cashflows.py:generate_fixed_schedule',
            'issue': 'Irregular period detection uses 5% tolerance which may be too loose',
            'impact': 'Could miscalculate coupon amounts for bonds with slightly irregular periods',
            'recommendation': 'Tighten tolerance or use exact period calculation'
        })
        
        # Issue 5: Z-spread solver convergence
        issues.append({
            'severity': 'LOW',
            'location': 'yield_spread.py:z_spread',
            'issue': 'Fallback solver uses fixed step adjustments that may not converge for extreme cases',
            'impact': 'Solver may fail for bonds with very high spreads or unusual cashflows',
            'recommendation': 'Implement adaptive step sizing or use more robust bracketing'
        })
        
        # Issue 6: Business day adjustment
        issues.append({
            'severity': 'MEDIUM',
            'location': 'ytw.py:generate_cashflows_to_call',
            'issue': 'Business day adjustment may not be applied consistently',
            'impact': 'Call date calculations may be off by 1-2 days',
            'recommendation': 'Ensure consistent application of business day conventions'
        })
        
        # Issue 7: Accrued interest in YTW
        issues.append({
            'severity': 'HIGH',
            'location': 'ytw.py:341-350',
            'issue': 'Accrued interest calculation for call dates uses simplified logic',
            'impact': 'May incorrectly calculate final payment amount for calls between coupon dates',
            'recommendation': 'Use precise accrued interest calculation based on actual schedule'
        })
        
        # Issue 8: Forward rate calculation
        issues.append({
            'severity': 'LOW',
            'location': 'cashflows.py:extract_cashflows',
            'issue': 'Forward rate projection for floating rate notes may not match market conventions',
            'impact': 'FRN valuations may differ from market standard',
            'recommendation': 'Validate forward rate calculation against market conventions'
        })
        
        for issue in issues:
            print(f"\n[{issue['severity']}] {issue['location']}")
            print(f"  Issue: {issue['issue']}")
            print(f"  Impact: {issue['impact']}")
            print(f"  Fix: {issue['recommendation']}")
            
        return issues
        
    def generate_report(self):
        """Generate final verification report."""
        print("\n" + "="*60)
        print("SPREADOMATIC VERIFICATION REPORT")
        print("="*60)
        
        print(f"\nTests Passed: {self.passed_tests}")
        print(f"Tests Failed: {self.failed_tests}")
        
        if self.errors:
            print(f"\n[X] ERRORS FOUND ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
                
        if self.warnings:
            print(f"\n[!] WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        accuracy_score = (self.passed_tests / max(1, self.passed_tests + self.failed_tests)) * 100
        print(f"\nAccuracy Score: {accuracy_score:.1f}%")
        
        if accuracy_score >= 90:
            print("[OK] SpreadOMatic calculations are generally accurate")
        elif accuracy_score >= 75:
            print("[WARNING] SpreadOMatic has some accuracy issues that should be addressed")
        else:
            print("[CRITICAL] SpreadOMatic has significant accuracy issues requiring immediate attention")
            
def main():
    """Run comprehensive SpreadOMatic verification."""
    verifier = SpreadOMaticVerifier()
    
    # Run all tests
    verifier.test_daycount_conventions()
    verifier.test_ytm_calculation()
    verifier.test_z_spread_calculation()
    verifier.test_g_spread_calculation()
    verifier.test_cashflow_generation()
    verifier.test_discount_factors()
    verifier.test_ytw_calculation()
    verifier.test_interpolation()
    verifier.test_edge_cases()
    
    # Identify issues
    issues = verifier.identify_potential_issues()
    
    # Generate report
    verifier.generate_report()
    
    return verifier.failed_tests == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)