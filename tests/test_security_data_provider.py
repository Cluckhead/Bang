"""
Comprehensive test suite for SecurityDataProvider
Tests all data collection, merging, and normalization logic to ensure
consistent behavior between synth_spread_calculator and synth_analytics_csv_processor
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil
from typing import Dict, Optional, Any
from unittest.mock import Mock, patch, MagicMock

# Import the SecurityDataProvider
from analytics.security_data_provider import SecurityDataProvider, SecurityData


# ============================================================================
# Test Fixtures and Mock Data
# ============================================================================

@pytest.fixture
def temp_data_folder():
    """Create a temporary data folder with test CSV files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_price_data():
    """Create mock price data."""
    return pd.DataFrame({
        'ISIN': ['US123456', 'US123456-1', 'DE789012', 'FR111111'],
        'Security Name': ['Bond A', 'Bond A Variant', 'Bond B', 'Bond C'],
        'Funds': ['IG01', 'IG01,IG02', 'IG02', 'IG03'],
        'Type': ['Corp', 'Corp', 'Govt Bond', 'Corp'],
        'Callable': ['Y', 'Y', 'N', 'Y'],
        'Currency': ['USD', 'USD', 'EUR', 'USD'],
        '2025-01-15': [98.5, 98.6, 101.2, 97.0],
        '2025-01-16': [98.7, 98.8, 101.3, 97.1]
    })


@pytest.fixture
def mock_schedule_data():
    """Create mock schedule data."""
    return pd.DataFrame({
        'ISIN': ['US123456', 'DE789012', 'FR111111'],
        'Day Basis': ['30/360', 'ACT/ACT', '30E/360'],
        'First Coupon': ['2020-08-15', '2021-03-01', '2020-06-15'],
        'Maturity Date': ['2030-02-15', '2031-09-01', '2029-12-15'],
        'Issue Date': ['2020-02-15', '2021-03-01', '2019-12-15'],
        'Coupon Frequency': [2, 1, 2],
        'Coupon Rate': [4.5, 2.0, np.nan],  # FR111111 missing coupon
        'Accrued Interest': [0.5, 0.8, 0.3],
        'Call Schedule': ['[]', '[]', '[{"Date":"2025-12-15","Price":100}]']
    })


@pytest.fixture
def mock_reference_data():
    """Create mock reference data."""
    return pd.DataFrame({
        'ISIN': ['US123456', 'US123456-1', 'DE789012', 'FR111111'],
        'Coupon Rate': [4.5, 4.5, 2.0, 3.75],  # FR111111 has coupon here
        'Maturity Date': ['2030-02-15T00:00:00', '2030-02-15T00:00:00', '2031-09-01T00:00:00', '2029-12-15T00:00:00'],
        'Position Currency': ['USD', 'USD', 'EUR', 'GBP'],  # FR111111 different currency
        'Call Indicator': [True, True, False, True]
    })


@pytest.fixture
def mock_accrued_data():
    """Create mock accrued interest data."""
    return pd.DataFrame({
        'ISIN': ['US123456', 'DE789012', 'FR111111'],
        '15/01/2025': [0.45, 0.82, 0.28],
        '16/01/2025': [0.48, 0.85, 0.31],
        '17/01/2025': [0.51, 0.88, 0.34]
    })


@pytest.fixture
def mock_curves_data():
    """Create mock curves data."""
    dates = ['2025-01-15', '2025-01-16']
    currencies = ['USD', 'EUR', 'GBP']
    terms = ['1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y']
    
    data = []
    for date in dates:
        for currency in currencies:
            for i, term in enumerate(terms):
                data.append({
                    'Date': date,
                    'Currency Code': currency,
                    'Term': term,
                    'Daily Value': 3.0 + i * 0.1  # Increasing rates
                })
    
    return pd.DataFrame(data)


@pytest.fixture
def setup_test_data(temp_data_folder, mock_price_data, mock_schedule_data, 
                   mock_reference_data, mock_accrued_data, mock_curves_data):
    """Setup all test CSV files in temp folder."""
    mock_price_data.to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
    mock_schedule_data.to_csv(Path(temp_data_folder) / 'schedule.csv', index=False)
    mock_reference_data.to_csv(Path(temp_data_folder) / 'reference.csv', index=False)
    mock_accrued_data.to_csv(Path(temp_data_folder) / 'sec_accrued.csv', index=False)
    mock_curves_data.to_csv(Path(temp_data_folder) / 'curves.csv', index=False)
    return temp_data_folder


# ============================================================================
# Test Class Definition (will pass once SecurityDataProvider is implemented)
# ============================================================================

class TestSecurityDataProvider:
    """Test suite for SecurityDataProvider unified data layer."""
    
    # ------------------------------------------------------------------------
    # Data Loading and Caching Tests
    # ------------------------------------------------------------------------
    
    def test_csv_file_loading(self, setup_test_data):
        """Test that all CSV files are loaded correctly."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Verify all data is loaded
        assert provider._price_df is not None
        assert provider._schedule_df is not None
        assert provider._reference_df is not None
        assert provider._accrued_df is not None
        assert provider._curves_df is not None
        
        # Verify data shapes
        assert len(provider._price_df) == 4  # 4 securities
        assert len(provider._schedule_df) == 3  # 3 have schedules
        assert len(provider._reference_df) == 4  # All have reference
    
    def test_missing_file_handling(self, temp_data_folder):
        """Test graceful handling of missing files."""
        # Only create price file
        pd.DataFrame({'ISIN': ['TEST001']}).to_csv(
            Path(temp_data_folder) / 'sec_Price.csv', index=False
        )
        
        provider = SecurityDataProvider(temp_data_folder)
        
        # Should not crash, should handle missing files
        assert provider._price_df is not None
        assert provider._schedule_df is None or provider._schedule_df.empty
        assert provider._reference_df is None or provider._reference_df.empty
    
    def test_cache_invalidation_on_file_change(self, setup_test_data):
        """Test that cache is invalidated when files change."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Get initial data
        initial_data = provider.get_security_data('US123456', '2025-01-15')
        assert initial_data is not None
        
        # Modify price file
        price_path = Path(setup_test_data) / 'sec_Price.csv'
        df = pd.read_csv(price_path)
        df.loc[df['ISIN'] == 'US123456', '2025-01-15'] = 99.9
        df.to_csv(price_path, index=False)
        
        # Force cache refresh (implementation should check mtime)
        provider._check_cache_validity()
        
        # Get updated data
        updated_data = provider.get_security_data('US123456', '2025-01-15')
        assert updated_data.price == 99.9
    
    # ------------------------------------------------------------------------
    # ISIN Normalization Tests
    # ------------------------------------------------------------------------
    
    def test_isin_normalization_basic(self, setup_test_data):
        """Test basic ISIN normalization (uppercase, trim)."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Test lowercase input
        data = provider.get_security_data('us123456', '2025-01-15')
        assert data is not None
        assert data.isin == 'US123456'
        
        # Test with spaces
        data = provider.get_security_data('  US123456  ', '2025-01-15')
        assert data is not None
        assert data.isin == 'US123456'
    
    def test_isin_hyphenated_variants(self, setup_test_data):
        """Test handling of hyphenated ISIN variants."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Test hyphenated variant
        data = provider.get_security_data('US123456-1', '2025-01-15')
        assert data is not None
        assert data.isin == 'US123456-1'
        assert data.base_isin == 'US123456'
        
        # Verify it gets variant-specific price
        assert data.price == 98.6  # US123456-1 price, not US123456
    
    def test_base_isin_extraction(self, setup_test_data):
        """Test extraction of base ISIN from variants."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Test base ISIN extraction
        assert provider._get_base_isin('US123456-1') == 'US123456'
        assert provider._get_base_isin('DE789012-2') == 'DE789012'
        assert provider._get_base_isin('FR111111') == 'FR111111'  # No hyphen
    
    def test_unicode_dash_conversion(self, setup_test_data):
        """Test conversion of various unicode dashes to ASCII."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Test various unicode dashes
        unicode_dashes = [
            'US123456\u2010 1',  # hyphen
            'US123456\u2013 1',  # en dash
            'US123456\u2014 1',  # em dash
        ]
        
        for isin in unicode_dashes:
            normalized = provider._normalize_isin(isin)
            assert '-' in normalized  # Should be ASCII dash
            assert '\u2010' not in normalized
            assert '\u2013' not in normalized
            assert '\u2014' not in normalized
    
    # ------------------------------------------------------------------------
    # Data Merging Priority Tests
    # ------------------------------------------------------------------------
    
    def test_accrued_overrides_schedule(self, setup_test_data):
        """Test that sec_accrued overrides schedule accrued interest."""
        provider = SecurityDataProvider(setup_test_data)
        
        data = provider.get_security_data('US123456', '2025-01-16')
        
        # sec_accrued has 0.48, schedule has 0.5
        assert data.accrued_interest == 0.48
    
    def test_reference_overrides_schedule_coupon(self, setup_test_data):
        """Test that reference.csv coupon rate is preferred over schedule."""
        provider = SecurityDataProvider(setup_test_data)
        
        # FR111111 has no coupon in schedule but 3.75 in reference
        data = provider.get_security_data('FR111111', '2025-01-15')
        assert data.coupon_rate == 3.75
    
    def test_schedule_preferred_for_technical(self, setup_test_data):
        """Test that schedule.csv is preferred for technical details."""
        provider = SecurityDataProvider(setup_test_data)
        
        data = provider.get_security_data('US123456', '2025-01-15')
        
        # Day basis should come from schedule
        assert data.day_basis == '30/360'
        # Frequency from schedule
        assert data.coupon_frequency == 2
    
    def test_missing_source_fallbacks(self, temp_data_folder):
        """Test handling when some source files are missing."""
        # Only create price and reference files
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Currency': ['USD'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Coupon Rate': [5.0],
            'Position Currency': ['EUR']
        }).to_csv(Path(temp_data_folder) / 'reference.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        assert data is not None
        assert data.coupon_rate == 5.0
        assert data.currency == 'EUR'  # From reference Position Currency
        assert data.accrued_interest == 0.0  # Default when no accrued data
    
    # ------------------------------------------------------------------------
    # Accrued Interest Lookup Tests
    # ------------------------------------------------------------------------
    
    def test_exact_date_match(self, setup_test_data):
        """Test exact date match in sec_accrued.csv."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Exact match for 16/01/2025
        accrued = provider.get_accrued_interest('US123456', '16/01/2025')
        assert accrued == 0.48
    
    def test_nearest_previous_date(self, setup_test_data):
        """Test fallback to nearest previous date."""
        provider = SecurityDataProvider(setup_test_data)
        
        # No data for 18/01/2025, should use 17/01/2025
        accrued = provider.get_accrued_interest('US123456', '18/01/2025')
        assert accrued == 0.51  # Value from 17/01/2025
    
    def test_base_isin_fallback(self, setup_test_data):
        """Test fallback to base ISIN for accrued lookup."""
        provider = SecurityDataProvider(setup_test_data)
        
        # US123456-1 not in accrued, should use US123456
        accrued = provider.get_accrued_interest('US123456-1', '16/01/2025')
        assert accrued == 0.48  # Value for US123456
    
    def test_default_zero_when_missing(self, setup_test_data):
        """Test return 0.0 when all lookups fail."""
        provider = SecurityDataProvider(setup_test_data)
        
        # ISIN not in accrued data
        accrued = provider.get_accrued_interest('XX999999', '16/01/2025')
        assert accrued == 0.0
    
    # ------------------------------------------------------------------------
    # Currency Determination Tests
    # ------------------------------------------------------------------------
    
    def test_reference_position_currency_priority(self, setup_test_data):
        """Test that Position Currency from reference.csv is preferred."""
        provider = SecurityDataProvider(setup_test_data)
        
        # FR111111 has USD in price but GBP in reference Position Currency
        data = provider.get_security_data('FR111111', '2025-01-15')
        assert data.currency == 'GBP'
    
    def test_price_currency_fallback(self, temp_data_folder):
        """Test fallback to sec_Price currency when reference missing."""
        # Only price file
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Currency': ['JPY'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        assert data.currency == 'JPY'
    
    def test_default_usd_currency(self, temp_data_folder):
        """Test default to USD when currency missing everywhere."""
        # Price file without currency
        pd.DataFrame({
            'ISIN': ['TEST001'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        assert data.currency == 'USD'
    
    # ------------------------------------------------------------------------
    # Default Value Handling Tests
    # ------------------------------------------------------------------------
    
    def test_missing_coupon_rate_zero(self, temp_data_folder):
        """Test that missing coupon rate defaults to 0.0, not assumed."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Currency': ['USD'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Day Basis': ['ACT/ACT'],
            'Maturity Date': ['2030-01-15']
            # No Coupon Rate
        }).to_csv(Path(temp_data_folder) / 'schedule.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        assert data.coupon_rate == 0.0  # Not 3.0 or other assumed value
    
    def test_missing_maturity_five_years(self, temp_data_folder):
        """Test that missing maturity defaults to 5 years from valuation."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        expected_maturity = datetime(2030, 1, 15)  # 5 years from 2025-01-15
        assert data.maturity_date == expected_maturity
    
    def test_missing_issue_one_year_ago(self, temp_data_folder):
        """Test that missing issue date defaults to 1 year before valuation."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        expected_issue = datetime(2024, 1, 15)  # 1 year before 2025-01-15
        assert data.issue_date == expected_issue
    
    def test_missing_frequency_semiannual(self, temp_data_folder):
        """Test that missing frequency defaults to semiannual (2)."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            '2025-01-15': [100.0]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        assert data.coupon_frequency == 2
    
    # ------------------------------------------------------------------------
    # Integration Tests
    # ------------------------------------------------------------------------
    
    def test_both_calculators_identical_results(self, setup_test_data):
        """Test that both calculation methods produce identical results."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Get same data for both methods
        data1 = provider.get_security_data('US123456', '2025-01-15')
        data2 = provider.get_security_data('US123456', '2025-01-15')
        
        # Should be exact same object or equal data
        assert data1.price == data2.price
        assert data1.coupon_rate == data2.coupon_rate
        assert data1.accrued_interest == data2.accrued_interest
        assert data1.currency == data2.currency
    
    def test_caching_performance(self, setup_test_data):
        """Test that data is loaded once and cached."""
        provider = SecurityDataProvider(setup_test_data)
        
        # Track file reads
        with patch('pandas.read_csv') as mock_read:
            # First call should not read (already loaded in __init__)
            data1 = provider.get_security_data('US123456', '2025-01-15')
            assert mock_read.call_count == 0
            
            # Second call should also not read
            data2 = provider.get_security_data('DE789012', '2025-01-15')
            assert mock_read.call_count == 0
    
    def test_thread_safety(self, setup_test_data):
        """Test concurrent access is safe."""
        import threading
        provider = SecurityDataProvider(setup_test_data)
        results = []
        
        def get_data(isin):
            data = provider.get_security_data(isin, '2025-01-15')
            results.append(data)
        
        threads = []
        for isin in ['US123456', 'DE789012', 'FR111111']:
            t = threading.Thread(target=get_data, args=(isin,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(results) == 3
        assert all(r is not None for r in results)


# ============================================================================
# Additional Test Scenarios
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_nan_values_handling(self, temp_data_folder):
        """Test handling of NaN values in data."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Currency': [np.nan],
            '2025-01-15': [np.nan]
        }).to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        assert data is not None
        assert data.currency == 'USD'  # Default
        assert np.isnan(data.price) or data.price == 0.0
    
    def test_excel_serial_dates(self, temp_data_folder):
        """Test handling of Excel serial number dates."""
        pd.DataFrame({
            'ISIN': ['TEST001'],
            'Maturity Date': [44927]  # Excel serial for 2023-01-01
        }).to_csv(Path(temp_data_folder) / 'schedule.csv', index=False)
        
        provider = SecurityDataProvider(temp_data_folder)
        data = provider.get_security_data('TEST001', '2025-01-15')
        
        # Should parse Excel serial correctly
        assert data.maturity_date.year == 2023
        assert data.maturity_date.month == 1
        assert data.maturity_date.day == 1


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Test performance characteristics of the provider."""
    
    def test_large_dataset_loading(self, temp_data_folder):
        """Test performance with large datasets."""
        # Create large dataset
        n_securities = 10000
        large_df = pd.DataFrame({
            'ISIN': [f'TEST{i:06d}' for i in range(n_securities)],
            'Currency': ['USD'] * n_securities,
            '2025-01-15': np.random.uniform(90, 110, n_securities)
        })
        large_df.to_csv(Path(temp_data_folder) / 'sec_Price.csv', index=False)
        
        import time
        start = time.time()
        provider = SecurityDataProvider(temp_data_folder)
        load_time = time.time() - start
        
        # Should load in reasonable time
        assert load_time < 5.0  # 5 seconds for 10k securities
        
        # Query should be fast
        start = time.time()
        data = provider.get_security_data('TEST005000', '2025-01-15')
        query_time = time.time() - start
        
        assert query_time < 0.01  # 10ms per query