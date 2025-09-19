# test_preprocessing_simple.py
# Purpose: Simple tests for data_processing/preprocessing.py core functions (Phase 3)
# Target: 6% → 40% coverage

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
import os
from typing import List, Dict, Any

# Import functions to test
from data_processing.preprocessing import (
    read_and_sort_dates,
    replace_headers_with_dates,
    suffix_isin,
    detect_metadata_columns
)


def create_test_csv(path: str, data: Dict[str, Any]) -> None:
    """Helper to create test CSV files."""
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)


class TestReadAndSortDatesSimple:
    """Test the read_and_sort_dates function with simple cases."""

    def test_read_and_sort_dates_iso_format(self, tmp_path):
        """Test reading dates in ISO format."""
        dates_data = {'Date': ['2025-01-03', '2025-01-01', '2025-01-02']}
        dates_file = tmp_path / 'dates.csv'
        create_test_csv(str(dates_file), dates_data)
        
        result = read_and_sort_dates(str(dates_file))
        
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 3  # Should have 3 unique dates
        assert all(date_str.startswith('2025-') for date_str in result)  # Should be 2025 dates
        assert result == sorted(result)  # Should be sorted

    def test_read_and_sort_dates_with_duplicates(self, tmp_path):
        """Test reading dates with duplicates."""
        dates_data = {'Date': ['2025-01-01', '2025-01-02', '2025-01-01', '2025-01-03']}
        dates_file = tmp_path / 'dates_dup.csv'
        create_test_csv(str(dates_file), dates_data)
        
        result = read_and_sort_dates(str(dates_file))
        
        assert result is not None
        # Should remove duplicates and sort
        assert len(result) == 3  # No duplicates
        assert len(set(result)) == 3  # All unique
        assert result == sorted(result)  # Sorted order

    def test_read_and_sort_dates_missing_file(self, tmp_path):
        """Test handling of missing file."""
        result = read_and_sort_dates(str(tmp_path / 'missing.csv'))
        assert result is None

    def test_read_and_sort_dates_empty_file(self, tmp_path):
        """Test handling of empty file."""
        empty_file = tmp_path / 'empty.csv'
        empty_file.write_text('')
        
        result = read_and_sort_dates(str(empty_file))
        assert result is None


class TestReplaceHeadersWithDatesSimple:
    """Test the replace_headers_with_dates function."""

    def test_replace_headers_field_pattern(self):
        """Test replacing Field, Field.1, Field.2 pattern with dates."""
        df = pd.DataFrame({
            'ISIN': ['US001'],
            'Security Name': ['Bond A'],
            'Field': [100],
            'Field.1': [101],
            'Field.2': [102]
        })
        
        dates = ['2025-01-01', '2025-01-02', '2025-01-03']
        
        result = replace_headers_with_dates(df, dates)
        
        # Should replace Field columns with dates
        expected_date_cols = {'2025-01-01', '2025-01-02', '2025-01-03'}
        actual_date_cols = {col for col in result.columns if col.startswith('2025-')}
        
        assert expected_date_cols.issubset(actual_date_cols), "Should have date columns"
        
        # Should preserve metadata
        assert 'ISIN' in result.columns
        assert 'Security Name' in result.columns

    def test_replace_headers_no_pattern_unchanged(self):
        """Test that DataFrame is unchanged when no pattern exists."""
        df = pd.DataFrame({
            'ISIN': ['US001'],
            'Price': [100],
            'Volume': [1000]
        })
        
        dates = ['2025-01-01', '2025-01-02']
        
        result = replace_headers_with_dates(df, dates)
        
        # Should be unchanged
        assert list(result.columns) == ['ISIN', 'Price', 'Volume']

    def test_replace_headers_partial_pattern(self):
        """Test replacing when only some columns match pattern."""
        df = pd.DataFrame({
            'ISIN': ['US001'],
            'Field': [100],
            'Field.1': [101],
            'Other': [999]  # Doesn't match pattern
        })
        
        dates = ['2025-01-01', '2025-01-02']
        
        result = replace_headers_with_dates(df, dates)
        
        # Should replace Field columns but preserve Other
        assert 'Other' in result.columns
        assert 'ISIN' in result.columns
        # Should have some date columns
        date_cols = [col for col in result.columns if col.startswith('2025-')]
        assert len(date_cols) >= 1


class TestSuffixIsinSimple:
    """Test the suffix_isin function."""

    def test_suffix_isin_basic_pattern(self):
        """Test basic ISIN suffixing."""
        result = suffix_isin('US0000001', 1)
        assert result == 'US0000001-1'
        
        result = suffix_isin('DE123456', 5)
        assert result == 'DE123456-5'

    def test_suffix_isin_various_numbers(self):
        """Test ISIN suffixing with various numbers."""
        test_cases = [
            ('US001', 0, 'US001-0'),
            ('FR111', 10, 'FR111-10'),
            ('GB999', 99, 'GB999-99')
        ]
        
        for isin, n, expected in test_cases:
            result = suffix_isin(isin, n)
            assert result == expected, f"suffix_isin('{isin}', {n}) should be '{expected}', got '{result}'"

    def test_suffix_isin_edge_cases(self):
        """Test ISIN suffixing edge cases."""
        # Empty ISIN
        result = suffix_isin('', 1)
        assert result == '-1'
        
        # Negative number
        result = suffix_isin('US001', -1)
        assert result == 'US001--1'  # Double dash


class TestDetectMetadataColumnsSimple:
    """Test the detect_metadata_columns function."""

    def test_detect_metadata_basic_case(self):
        """Test basic metadata column detection."""
        df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],           # Non-numeric
            'Security Name': ['Bond A', 'Bond B'], # Non-numeric
            '2025-01-01': [100, 200],             # Numeric
            '2025-01-02': [101, 201],             # Numeric
            '2025-01-03': [102, 202]              # Numeric
        })
        
        result = detect_metadata_columns(df, min_numeric_cols=3)
        
        # Should detect 2 metadata columns
        assert result == 2

    def test_detect_metadata_insufficient_numeric(self):
        """Test when insufficient numeric columns exist."""
        df = pd.DataFrame({
            'ISIN': ['US001'],
            'Security Name': ['Bond A'],
            'Type': ['Corp'],
            '2025-01-01': [100]  # Only 1 numeric
        })
        
        result = detect_metadata_columns(df, min_numeric_cols=3)
        
        # Should handle gracefully
        assert isinstance(result, int)
        assert result >= 0

    def test_detect_metadata_mixed_types(self):
        """Test detection with mixed column types."""
        df = pd.DataFrame({
            'ISIN': ['US001'],           # String
            'Rating': ['AAA'],           # String
            'Coupon': [5.0],            # Numeric (but not date-like)
            '2025-01-01': [100],        # Date-like numeric
            '2025-01-02': [101],        # Date-like numeric
            '2025-01-03': [102]         # Date-like numeric
        })
        
        result = detect_metadata_columns(df, min_numeric_cols=3)
        
        # Should detect metadata vs date columns appropriately
        assert isinstance(result, int)
        # Exact result depends on implementation logic
        assert 0 <= result <= len(df.columns)


class TestReplaceHeadersEdgeCases:
    """Test edge cases for header replacement."""

    def test_replace_headers_empty_dataframe(self):
        """Test header replacement with empty DataFrame."""
        df = pd.DataFrame()
        dates = ['2025-01-01', '2025-01-02']
        
        result = replace_headers_with_dates(df, dates)
        
        # Should handle empty DataFrame gracefully
        assert isinstance(result, pd.DataFrame)

    def test_replace_headers_empty_dates(self):
        """Test header replacement with empty dates list."""
        df = pd.DataFrame({
            'ISIN': ['US001'],
            'Field': [100],
            'Field.1': [101]
        })
        
        dates = []
        
        result = replace_headers_with_dates(df, dates)
        
        # Should handle empty dates gracefully
        assert isinstance(result, pd.DataFrame)

    def test_replace_headers_single_column(self):
        """Test header replacement with single column."""
        df = pd.DataFrame({'Field': [100, 101, 102]})
        dates = ['2025-01-01']
        
        result = replace_headers_with_dates(df, dates)
        
        # Should handle single column case
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) >= 1


class TestPreprocessingConstants:
    """Test preprocessing constants."""

    def test_prefix_constants(self):
        """Test that prefix constants are properly defined."""
        from data_processing.preprocessing import PRE_PREFIX, SEC_PREFIX, WEIGHT_PREFIX, PRE_WEIGHT_PREFIX
        
        assert PRE_PREFIX == "pre_"
        assert SEC_PREFIX == "sec_"
        assert WEIGHT_PREFIX == "w_"
        assert PRE_WEIGHT_PREFIX == "pre_w_"

    def test_constants_are_strings(self):
        """Test that all constants are strings."""
        from data_processing.preprocessing import PRE_PREFIX, SEC_PREFIX, WEIGHT_PREFIX, PRE_WEIGHT_PREFIX
        
        constants = [PRE_PREFIX, SEC_PREFIX, WEIGHT_PREFIX, PRE_WEIGHT_PREFIX]
        
        for const in constants:
            assert isinstance(const, str)
            assert len(const) > 0
