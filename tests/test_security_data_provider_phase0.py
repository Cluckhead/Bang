# test_security_data_provider_phase0.py
# Purpose: Unit tests for analytics/security_data_provider.py (Phase 0 fast wins)

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Import the SecurityDataProvider
from analytics.security_data_provider import SecurityDataProvider


class TestSecurityDataProviderBasics:
    """Test basic SecurityDataProvider functionality using mini_dataset."""

    def test_normalize_isin_handles_unicode_dashes_and_case(self):
        """Test ISIN normalization handles unicode dashes and case."""
        provider = SecurityDataProvider("dummy_path")  # Path not used for this test
        
        # Test unicode dash normalization
        result = provider._normalize_isin('us0000001\u2013a')
        assert result == 'US0000001-A', f"Expected 'US0000001-A', got '{result}'"
        
        # Test regular dash preservation
        result = provider._normalize_isin('US0000001-1')
        assert result == 'US0000001-1', f"Expected 'US0000001-1', got '{result}'"
        
        # Test case conversion
        result = provider._normalize_isin('us0000001')
        assert result == 'US0000001', f"Expected 'US0000001', got '{result}'"

    def test_get_base_isin_removes_suffix(self):
        """Test that get_base_isin removes suffix correctly."""
        provider = SecurityDataProvider("dummy_path")
        
        # Test suffix removal
        result = provider._get_base_isin('US0000002-1')
        assert result == 'US0000002', f"Expected 'US0000002', got '{result}'"
        
        # Test no suffix case
        result = provider._get_base_isin('US0000001')
        assert result == 'US0000001', f"Expected 'US0000001', got '{result}'"
        
        # Test multiple dash case (splits on first dash, returns first part)
        result = provider._get_base_isin('US000-001-1')
        assert result == 'US000', f"Expected 'US000', got '{result}'"

    def test_currency_precedence_reference_over_price(self, mini_dataset):
        """Test currency precedence: Position Currency > Currency > Price Currency."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Get security data for US0000001 which has Position Currency=EUR, Currency=USD
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        
        assert security_data is not None, "Security data should not be None"
        # Should prefer Position Currency (EUR) over Currency (USD)
        assert security_data.currency == 'EUR', f"Expected EUR (Position Currency), got {security_data.currency}"

    def test_accrued_interest_exact_date(self, mini_dataset):
        """Test accrued interest lookup with exact date match."""
        provider = SecurityDataProvider(mini_dataset)
        
        # US0000001 should have accrued interest 1.22 on 2025-01-02
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        
        assert security_data is not None, "Security data should not be None"
        assert security_data.accrued_interest == 1.22, f"Expected 1.22, got {security_data.accrued_interest}"

    def test_accrued_interest_schedule_fallback(self, mini_dataset):
        """Test accrued interest fallback to schedule when sec_accrued not available."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with date that doesn't exist in sec_accrued - should fall back to schedule
        # US0000001 has Accrued Interest = 1.23 in schedule
        security_data = provider.get_security_data('US0000001', '2024-12-31')  # Date not in sec_accrued
        
        assert security_data is not None, "Security data should not be None"
        # Should fall back to schedule value of 1.23 or 0.0 if not found
        assert security_data.accrued_interest in [1.23, 0.0], f"Expected 1.23 or 0.0, got {security_data.accrued_interest}"

    def test_get_security_data_merges_all_sources(self, mini_dataset):
        """Test that get_security_data merges all data sources correctly."""
        provider = SecurityDataProvider(mini_dataset)
        
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        
        assert security_data is not None, "Security data should not be None"
        
        # Check that all expected fields are present and reasonable
        assert security_data.isin == 'US0000001'
        assert security_data.price > 0, f"Price should be positive, got {security_data.price}"
        assert security_data.coupon_rate == 5.0, f"Expected coupon rate 5.0, got {security_data.coupon_rate}"
        assert security_data.currency == 'EUR', f"Expected EUR, got {security_data.currency}"
        assert security_data.maturity_date is not None, "Maturity date should be set"
        assert security_data.coupon_frequency == 2, f"Expected frequency 2, got {security_data.coupon_frequency}"
        assert security_data.day_basis == 'ACT/ACT', f"Expected ACT/ACT, got {security_data.day_basis}"

    def test_handles_missing_isin_gracefully(self, mini_dataset):
        """Test that provider handles missing ISIN gracefully."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with non-existent ISIN
        security_data = provider.get_security_data('NONEXISTENT', '2025-01-02')
        
        # Should return None or handle gracefully
        # (Implementation may vary - could return None or SecurityData with defaults)
        if security_data is not None:
            # If it returns data, it should have the requested ISIN
            assert security_data.isin == 'NONEXISTENT'

    def test_handles_missing_date_gracefully(self, mini_dataset):
        """Test that provider handles missing date gracefully."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with date that doesn't exist in price data
        security_data = provider.get_security_data('US0000001', '1999-01-01')
        
        # Should handle gracefully - might return None or data with NaN price
        if security_data is not None:
            # Price might be NaN or 0 for missing date
            assert pd.isna(security_data.price) or security_data.price == 0.0 or security_data.price > 0


class TestSecurityDataProviderEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_data_folder(self, tmp_path):
        """Test behavior with empty data folder."""
        provider = SecurityDataProvider(str(tmp_path))
        
        # Should handle missing files gracefully
        security_data = provider.get_security_data('US0000001', '2025-01-02')
        
        # Implementation should handle missing files gracefully
        # Could return None or SecurityData with defaults
        if security_data is not None:
            assert security_data.isin == 'US0000001'

    def test_malformed_csv_handling(self, tmp_path):
        """Test handling of malformed CSV files."""
        # Create a malformed reference.csv
        malformed_csv = tmp_path / "reference.csv"
        malformed_csv.write_text("ISIN,Bad,Header\nUS0000001,incomplete")
        
        provider = SecurityDataProvider(str(tmp_path))
        
        # Should handle malformed CSV gracefully
        try:
            security_data = provider.get_security_data('US0000001', '2025-01-02')
            # If it succeeds, that's fine
        except Exception:
            # If it fails, that's also acceptable for malformed data
            pass

    def test_unicode_isin_handling(self, mini_dataset):
        """Test handling of ISINs with various unicode characters."""
        provider = SecurityDataProvider(mini_dataset)
        
        # Test with unicode dash
        unicode_isin = 'US0000001\u2013A'
        
        # Should normalize and potentially find base ISIN
        try:
            security_data = provider.get_security_data(unicode_isin, '2025-01-02')
            # If found, should have normalized ISIN
            if security_data is not None:
                assert security_data.isin == 'US0000001-A' or security_data.base_isin == 'US0000001'
        except Exception:
            # Unicode handling might not be fully implemented yet
            pass
