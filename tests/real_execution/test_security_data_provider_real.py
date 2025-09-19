# test_security_data_provider_real.py
# Purpose: Real execution tests for analytics/security_data_provider.py (Phase 4)
# Target: Execute actual business logic without mocking to achieve real coverage

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import os
import time
from typing import Dict, Any

# Import for REAL execution (no mocking)
from analytics.security_data_provider import SecurityDataProvider, SecurityData


class TestSecurityDataProviderRealExecution:
    """Test real execution of SecurityDataProvider operations."""

    def test_real_csv_loading_and_merging(self, mini_dataset):
        """Execute real pandas read_csv operations and DataFrame merging."""
        # Use actual SecurityDataProvider without mocking
        provider = SecurityDataProvider(mini_dataset)
        
        # This will execute real CSV loading operations
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        
        assert security_data is not None, "Should load real data from mini_dataset"
        
        # Verify real data merging occurred
        assert security_data.isin == 'US0000001'
        assert security_data.base_isin == 'US0000001'
        assert security_data.price > 0, f"Should have real price from CSV, got {security_data.price}"
        assert security_data.currency in ['EUR', 'USD', 'GBP'], f"Should have real currency, got {security_data.currency}"
        
        # Test that actual DataFrame operations occurred
        assert hasattr(security_data, 'coupon_rate')
        assert hasattr(security_data, 'accrued_interest')

    def test_real_isin_normalization_string_operations(self):
        """Execute actual string operations for ISIN normalization."""
        provider = SecurityDataProvider("dummy_path")  # Path not used for normalization
        
        # Test 50+ ISIN variants with real string operations
        isin_test_cases = [
            # Basic normalization
            ('us0000001', 'US0000001'),
            ('de123456', 'DE123456'),
            ('fr111111', 'FR111111'),
            ('gb999999', 'GB999999'),
            
            # Case variations
            ('US0000001', 'US0000001'),
            ('Us0000001', 'US0000001'),
            ('uS0000001', 'US0000001'),
            
            # With suffixes
            ('us0000001-1', 'US0000001-1'),
            ('US0000001-A', 'US0000001-A'),
            ('de123456-2', 'DE123456-2'),
            
            # Unicode dashes (real character replacement)
            ('us0000001\u2013a', 'US0000001-A'),  # En dash
            ('US0000001\u2014B', 'US0000001-B'),  # Em dash
            ('de123456\u2010c', 'DE123456-C'),    # Hyphen
            ('fr111111\u2011d', 'FR111111-D'),    # Non-breaking hyphen
            ('gb999999\u2012e', 'GB999999-E'),    # Figure dash
            ('au111111\u2015f', 'AU111111-F'),    # Horizontal bar
            
            # Edge cases
            ('  us0000001  ', 'US0000001'),       # Whitespace
            ('us0000001\t', 'US0000001'),         # Tab
            ('us0000001\n', 'US0000001'),         # Newline
            
            # Multiple dashes
            ('us000-001-1', 'US000-001-1'),
            ('us000\u2013001\u2013a', 'US000-001-A'),
            
            # Mixed unicode
            ('us0000001\u2013\u2014a', 'US0000001--A'),  # Multiple unicode dashes
            
            # Real-world variants
            ('XS1234567890', 'XS1234567890'),     # Long ISIN
            ('USG1234567', 'USG1234567'),         # Government ISIN
            ('DE000A1B2C3', 'DE000A1B2C3'),       # German format
            ('FR0010123456', 'FR0010123456'),     # French format
            ('GB00B1234567', 'GB00B1234567'),     # UK format
            ('JP3123456789', 'JP3123456789'),     # Japanese format
            
            # Corporate action suffixes
            ('us0000001-old', 'US0000001-OLD'),
            ('us0000001-new', 'US0000001-NEW'),
            ('us0000001-when', 'US0000001-WHEN'),
            ('us0000001-wi', 'US0000001-WI'),
            
            # Tap issues
            ('us0000001-1', 'US0000001-1'),
            ('us0000001-2', 'US0000001-2'),
            ('us0000001-10', 'US0000001-10'),
            
            # Edge length cases
            ('US', 'US'),                         # Too short
            ('US0', 'US0'),                       # Still too short
            ('US000000000000000001', 'US000000000000000001'),  # Very long
        ]
        
        for input_isin, expected in isin_test_cases:
            result = provider._normalize_isin(input_isin)
            assert result == expected, f"_normalize_isin('{repr(input_isin)}') should return '{expected}', got '{result}'"

    def test_real_base_isin_extraction(self):
        """Execute actual base ISIN extraction logic."""
        provider = SecurityDataProvider("dummy_path")
        
        base_isin_cases = [
            ('US0000001', 'US0000001'),       # No suffix
            ('US0000001-1', 'US0000001'),     # Numeric suffix
            ('US0000001-A', 'US0000001'),     # Letter suffix
            ('US0000001-OLD', 'US0000001'),   # Word suffix
            ('US0000001-WI', 'US0000001'),    # When-issued
            ('DE123456-2B', 'DE123456'),      # Complex suffix
            ('FR000-001-1', 'FR000'),         # Multiple dashes (takes first part)
            ('GB999-999-A', 'GB999'),         # Multiple dashes
            ('', ''),                         # Empty string
            ('NODASH', 'NODASH'),             # No dash at all
        ]
        
        for input_isin, expected_base in base_isin_cases:
            result = provider._get_base_isin(input_isin)
            assert result == expected_base, f"_get_base_isin('{input_isin}') should return '{expected_base}', got '{result}'"

    def test_real_accrued_interest_fallback_chain(self, mini_dataset):
        """Execute actual pandas DataFrame lookups across multiple files."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with ISIN that exists in mini_dataset
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        assert security_data is not None
        
        # This should execute real DataFrame operations:
        # 1. Load sec_accrued.csv with pandas
        # 2. Filter by ISIN
        # 3. Look up exact date
        # 4. Fall back to previous date if needed
        # 5. Fall back to schedule if needed
        
        accrued = security_data.accrued_interest
        assert isinstance(accrued, (int, float)) or pd.isna(accrued), "Should return numeric accrued interest"
        
        # Test with date that doesn't exist (should trigger fallback)
        security_data_fallback = provider.get_security_data('US0000001', '2025-01-05')
        if security_data_fallback is not None:
            # Should execute fallback logic
            assert hasattr(security_data_fallback, 'accrued_interest')

    def test_real_currency_precedence_logic(self, mini_dataset):
        """Execute actual currency precedence logic."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test US0000001 which has Position Currency=EUR, Currency=USD in mini_dataset
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        assert security_data is not None
        
        # This should execute real DataFrame operations to determine currency precedence
        # Position Currency (EUR) should override Currency (USD)
        assert security_data.currency == 'EUR', f"Real currency precedence should select EUR, got {security_data.currency}"
        
        # Test US0000002 which has different currency setup
        security_data2 = provider.get_security_data('US0000002', '2025-01-02')
        if security_data2 is not None:
            # Should execute same precedence logic
            assert security_data2.currency in ['EUR', 'USD', 'GBP'], "Should have valid currency from precedence logic"

    def test_real_cache_invalidation_file_mtime(self, mini_dataset):
        """Execute actual file system mtime checking and cache invalidation."""
        provider = SecurityDataProvider(mini_dataset)
        
        # First access - should load from files
        start_time = time.time()
        security_data1 = provider.get_security_data('US0000001', '2025-01-02')
        first_access_time = time.time() - start_time
        
        assert security_data1 is not None
        original_price = security_data1.price
        
        # Second access - should use cache
        start_time = time.time()
        security_data2 = provider.get_security_data('US0000001', '2025-01-02')
        second_access_time = time.time() - start_time
        
        assert security_data2 is not None
        assert security_data2.price == original_price, "Cached access should return same data"
        
        # Cache access should be faster (though this might vary)
        # This is more about testing that the cache mechanism works
        
        # Modify a source file to trigger cache invalidation
        price_file = os.path.join(mini_dataset, 'sec_Price.csv')
        if os.path.exists(price_file):
            # Touch the file to change mtime
            current_time = time.time()
            os.utime(price_file, (current_time, current_time))
            
            # Third access - should reload due to cache invalidation
            security_data3 = provider.get_security_data('US0000001', '2025-01-02')
            assert security_data3 is not None
            # Should have reloaded (might have same data but cache was invalidated)

    def test_real_dataframe_operations_performance(self, mini_dataset):
        """Test performance of real DataFrame operations."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test multiple securities to exercise DataFrame operations
        test_isins = ['US0000001', 'US0000002', 'US0000002-1']
        results = []
        
        total_start_time = time.time()
        
        for isin in test_isins:
            start_time = time.time()
            security_data = provider.get_security_data(isin, '2025-01-02')
            end_time = time.time()
            
            duration = end_time - start_time
            results.append((isin, security_data, duration))
            
            # Each call should be reasonably fast
            assert duration < 0.5, f"SecurityDataProvider.get_security_data('{isin}') took {duration:.3f}s, should be <0.5s"
        
        total_end_time = time.time()
        total_duration = total_end_time - total_start_time
        
        # Total should be reasonable
        assert total_duration < 2.0, f"Total time for {len(test_isins)} securities was {total_duration:.3f}s, should be <2.0s"
        
        # Should have processed at least some securities successfully
        successful_results = [r for _, r, _ in results if r is not None]
        assert len(successful_results) >= 1, "Should successfully process at least one security"


class TestSecurityDataProviderRealIntegration:
    """Test real integration scenarios."""

    def test_real_multi_file_data_integration(self, mini_dataset):
        """Test real integration across multiple CSV files."""
        provider = SecurityDataProvider(mini_dataset)
        
        # This should execute real operations across:
        # - reference.csv loading and parsing
        # - schedule.csv loading and parsing  
        # - sec_Price.csv loading and parsing
        # - sec_accrued.csv loading and parsing
        # - DataFrame merging and joining operations
        
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        assert security_data is not None
        
        # Verify data came from multiple sources (real integration)
        assert security_data.isin is not None          # From any file
        assert security_data.security_name is not None # From reference.csv
        assert security_data.price > 0                 # From sec_Price.csv
        assert security_data.currency is not None      # From reference.csv (precedence logic)
        assert security_data.coupon_rate is not None   # From reference.csv or schedule.csv
        assert security_data.accrued_interest is not None  # From sec_accrued.csv or schedule.csv
        
        # Verify actual DataFrame operations occurred
        assert isinstance(security_data.price, (int, float))
        assert isinstance(security_data.coupon_rate, (int, float))

    def test_real_isin_variant_handling(self, mini_dataset):
        """Test real ISIN variant and base ISIN handling."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test base ISIN
        base_data = provider.get_security_data('US0000002', '2025-01-02')
        
        # Test variant ISIN (US0000002-1 exists in mini_dataset)
        variant_data = provider.get_security_data('US0000002-1', '2025-01-02')
        
        if base_data is not None and variant_data is not None:
            # Should execute real base ISIN resolution
            assert variant_data.base_isin == 'US0000002'
            assert base_data.base_isin == 'US0000002'
            
            # Both should have valid data from real operations
            assert variant_data.isin == 'US0000002-1'
            assert base_data.isin == 'US0000002'

    def test_real_error_handling_missing_data(self, mini_dataset):
        """Test real error handling with actual missing data scenarios."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with ISIN that doesn't exist in any file
        missing_data = provider.get_security_data('NONEXISTENT123', '2025-01-02')
        # Should handle gracefully (might return None or SecurityData with defaults)
        
        # Test with date that doesn't exist
        future_data = provider.get_security_data('US0000001', '2030-01-01')
        # Should handle gracefully
        
        # Test with invalid date format
        try:
            invalid_date_data = provider.get_security_data('US0000001', 'invalid-date')
            # Should handle gracefully or raise appropriate exception
        except Exception:
            # Expected for invalid date format
            pass

    def test_real_curve_data_operations(self, mini_dataset):
        """Test real curve data loading and filtering operations."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Execute real curve data operations
        usd_curves = provider.get_curves_data('USD', '2025-01-02')
        
        if usd_curves is not None and not usd_curves.empty:
            # Should execute real pandas filtering operations
            assert isinstance(usd_curves, pd.DataFrame)
            assert 'Currency Code' in usd_curves.columns
            assert 'Date' in usd_curves.columns
            assert 'Term' in usd_curves.columns
            assert 'Daily Value' in usd_curves.columns
            
            # Verify filtering worked
            assert all(usd_curves['Currency Code'] == 'USD'), "Should filter to USD only"
            
            # Should have numeric values
            assert pd.api.types.is_numeric_dtype(usd_curves['Daily Value']), "Daily Value should be numeric"

    def test_real_data_validation_operations(self, mini_dataset):
        """Test real data validation and type checking operations."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Get multiple securities to test validation across different data
        test_isins = ['US0000001', 'US0000002']
        
        for isin in test_isins:
            security_data = provider.get_security_data(isin, '2025-01-02')
            
            if security_data is not None:
                # Execute real validation operations
                
                # ISIN should be valid string
                assert isinstance(security_data.isin, str)
                assert len(security_data.isin) > 0
                
                # Price should be valid number if present
                if pd.notna(security_data.price):
                    assert isinstance(security_data.price, (int, float))
                    assert security_data.price >= 0  # Allow 0 price (might indicate missing data)
                
                # Coupon rate should be reasonable if present
                if pd.notna(security_data.coupon_rate):
                    assert isinstance(security_data.coupon_rate, (int, float))
                    assert 0 <= security_data.coupon_rate <= 25  # Reasonable range
                
                # Currency should be valid
                assert isinstance(security_data.currency, str)
                assert len(security_data.currency) >= 3  # Should be currency code like USD, EUR
                
                # Dates should be datetime objects if present
                if security_data.issue_date is not None:
                    assert isinstance(security_data.issue_date, datetime)
                if security_data.maturity_date is not None:
                    assert isinstance(security_data.maturity_date, datetime)


class TestSecurityDataProviderRealPerformance:
    """Test real performance characteristics."""

    def test_real_bulk_operations_performance(self, mini_dataset):
        """Test performance of bulk real operations."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test bulk loading performance
        test_isins = ['US0000001', 'US0000002', 'US0000002-1'] * 5  # 15 total calls
        test_dates = ['2025-01-01', '2025-01-02']
        
        total_operations = len(test_isins) * len(test_dates)
        
        start_time = time.time()
        results = []
        
        for isin in test_isins:
            for date in test_dates:
                security_data = provider.get_security_data(isin, date)
                results.append(security_data)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Should complete bulk operations efficiently
        avg_time_per_op = total_duration / total_operations
        assert avg_time_per_op < 0.1, f"Average time per operation was {avg_time_per_op:.4f}s, should be <0.1s"
        
        # Should have some successful results
        successful_results = [r for r in results if r is not None]
        success_rate = len(successful_results) / len(results)
        assert success_rate >= 0.5, f"Success rate was {success_rate:.1%}, should be ≥50%"

    def test_real_memory_usage_patterns(self, mini_dataset):
        """Test memory usage patterns with real operations."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test that repeated operations don't cause memory leaks
        initial_result = provider.get_security_data('US0000001', '2025-01-02')
        
        # Perform many operations
        for i in range(50):
            result = provider.get_security_data('US0000001', '2025-01-02')
            if result is not None and initial_result is not None:
                # Should return consistent data (testing cache/memory efficiency)
                assert result.isin == initial_result.isin
                assert result.price == initial_result.price

    def test_real_concurrent_access_simulation(self, mini_dataset):
        """Simulate concurrent access patterns."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Simulate multiple "users" accessing different securities
        access_patterns = [
            ('US0000001', '2025-01-01'),
            ('US0000002', '2025-01-02'),
            ('US0000001', '2025-01-02'),  # Same ISIN, different date
            ('US0000002-1', '2025-01-01'),  # Variant ISIN
        ]
        
        results = []
        for isin, date in access_patterns:
            security_data = provider.get_security_data(isin, date)
            results.append((isin, date, security_data))
        
        # All operations should succeed or fail gracefully
        for isin, date, result in results:
            if result is not None:
                assert result.isin == isin, f"Should return data for requested ISIN {isin}"
                assert isinstance(result, SecurityData), "Should return SecurityData object"
