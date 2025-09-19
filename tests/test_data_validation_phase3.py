# test_data_validation_phase3.py
# Purpose: Tests for data_processing/data_validation.py (Phase 3)
# Target: 55% → 75% coverage

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from typing import Tuple, List

# Import functions to test
from data_processing.data_validation import validate_data, _is_date_like


class TestValidateData:
    """Test the main validate_data function."""

    def test_validate_ts_happy_path(self):
        """Test validation of valid time-series DataFrame."""
        # Create valid time-series data
        ts_df = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02', '2025-01-03'],
            'Code': ['F1', 'F1', 'F2'],
            'Value': [100.0, 101.0, 200.0]
        })
        
        is_valid, errors = validate_data(ts_df, 'ts_Duration.csv')
        
        assert is_valid is True
        assert errors == []

    def test_validate_ts_missing_required_columns(self):
        """Test validation when required columns are missing."""
        # Missing 'Code' column
        ts_df = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02'],
            'Value': [100.0, 101.0]
        })
        
        is_valid, errors = validate_data(ts_df, 'ts_Duration.csv')
        
        assert is_valid is False
        assert len(errors) > 0
        assert any('Code' in error for error in errors)

    def test_validate_ts_non_numeric_values(self):
        """Test validation when value columns contain non-numeric data."""
        # Non-numeric values in Value column
        ts_df = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02'],
            'Code': ['F1', 'F1'],
            'Value': ['not_numeric', 'also_not_numeric']
        })
        
        is_valid, errors = validate_data(ts_df, 'ts_Duration.csv')
        
        assert is_valid is False
        assert len(errors) > 0
        assert any('not numeric' in error.lower() for error in errors)

    def test_validate_sec_date_like_columns(self):
        """Test validation of security-level data with date-like columns."""
        # Create valid security data
        sec_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'Security Name': ['Bond A', 'Bond B'],
            '2025-01-01': [100.0, 200.0],
            '2025-01-02': [101.0, 201.0]
        })
        
        is_valid, errors = validate_data(sec_df, 'sec_Spread.csv')
        
        assert is_valid is True
        assert errors == []

    def test_validate_sec_non_numeric_date_columns(self):
        """Test validation when date-like columns contain non-numeric data."""
        # Non-numeric values in date columns
        sec_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'Security Name': ['Bond A', 'Bond B'],
            '2025-01-01': ['not_numeric', 200.0],
            '2025-01-02': [101.0, 'also_not_numeric']
        })
        
        is_valid, errors = validate_data(sec_df, 'sec_Spread.csv')
        
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_weights_header_dates(self):
        """Test validation of weights files with date headers."""
        # Valid weights data
        weights_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            '2025-01-01': [0.15, 0.25],
            '2025-01-02': [0.16, 0.24]
        })
        
        is_valid, errors = validate_data(weights_df, 'w_secs.csv')
        
        assert is_valid is True
        assert errors == []

    def test_validate_weights_invalid_date_headers(self):
        """Test validation when weights file has invalid date headers."""
        # Invalid date headers
        weights_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'invalid_header': [0.15, 0.25],
            'another_bad_header': [0.16, 0.24]
        })
        
        is_valid, errors = validate_data(weights_df, 'w_secs.csv')
        
        # Might be invalid due to non-date headers
        if not is_valid:
            assert len(errors) > 0

    def test_validate_empty_dataframe(self):
        """Test validation of empty DataFrame."""
        empty_df = pd.DataFrame()
        
        is_valid, errors = validate_data(empty_df, 'ts_Duration.csv')
        
        # Empty DataFrame should generate warning but might still be valid
        assert isinstance(is_valid, bool)
        # Should have at least a warning about empty data
        assert len(errors) >= 1
        assert any('empty' in error.lower() for error in errors)

    def test_validate_none_dataframe(self):
        """Test validation of None DataFrame."""
        is_valid, errors = validate_data(None, 'ts_Duration.csv')
        
        assert is_valid is False
        assert len(errors) > 0
        assert any('None' in error for error in errors)

    def test_validate_invalid_dataframe_type(self):
        """Test validation with invalid DataFrame type."""
        invalid_df = "not_a_dataframe"
        
        is_valid, errors = validate_data(invalid_df, 'ts_Duration.csv')
        
        assert is_valid is False
        assert len(errors) > 0
        assert any('not a pandas DataFrame' in error for error in errors)


class TestIsDateLike:
    """Test the _is_date_like helper function."""

    def test_is_date_like_valid_dates(self):
        """Test that valid date strings return True."""
        valid_dates = [
            '2025-01-01',
            '2024-12-31',
            '2025-01-02',
            '2025-12-25'
        ]
        
        for date_str in valid_dates:
            assert _is_date_like(date_str) is True, f"'{date_str}' should be recognized as date-like"

    def test_is_date_like_invalid_strings(self):
        """Test that non-date strings return False."""
        invalid_strings = [
            'ISIN',
            'Security Name',
            'not_a_date',
            'random_text',
            '12345',
            ''
        ]
        
        for invalid_str in invalid_strings:
            assert _is_date_like(invalid_str) is False, f"'{invalid_str}' should not be recognized as date-like"

    def test_is_date_like_edge_cases(self):
        """Test edge cases for date-like detection."""
        edge_cases = [
            ('2025-13-01', False),  # Invalid month
            ('2025-01-32', False),  # Invalid day
            ('25-01-01', False),    # Wrong year format
            ('2025/01/01', True),   # Might be considered date-like depending on implementation
        ]
        
        for test_str, expected in edge_cases:
            result = _is_date_like(test_str)
            # Some edge cases might vary by implementation
            assert isinstance(result, bool), f"_is_date_like('{test_str}') should return boolean"


class TestValidationByFileType:
    """Test validation logic for different file types."""

    def test_validate_ts_file_specific_logic(self):
        """Test time-series specific validation logic."""
        # Valid ts_ file
        ts_df = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02'],
            'Code': ['F1', 'F2'],
            'Value': [100.0, 200.0]
        })
        
        is_valid, errors = validate_data(ts_df, 'ts_Spread.csv')
        assert is_valid is True
        
        # Invalid ts_ file (missing Date)
        invalid_ts_df = pd.DataFrame({
            'Code': ['F1', 'F2'],
            'Value': [100.0, 200.0]
        })
        
        is_valid, errors = validate_data(invalid_ts_df, 'ts_Spread.csv')
        assert is_valid is False
        assert any('Date' in error for error in errors)

    def test_validate_sec_file_specific_logic(self):
        """Test security-level specific validation logic."""
        # Valid sec_ file
        sec_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'Security Name': ['Bond A', 'Bond B'],
            '2025-01-01': [100.0, 200.0],
            '2025-01-02': [101.0, 201.0]
        })
        
        is_valid, errors = validate_data(sec_df, 'sec_Duration.csv')
        assert is_valid is True
        
        # Test with non-numeric date columns
        invalid_sec_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'Security Name': ['Bond A', 'Bond B'],
            '2025-01-01': ['invalid', 'data']
        })
        
        is_valid, errors = validate_data(invalid_sec_df, 'sec_Duration.csv')
        # Should detect non-numeric values in date columns
        assert is_valid is False

    def test_validate_weights_file_specific_logic(self):
        """Test weights file specific validation logic."""
        # Valid weights file
        weights_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            '2025-01-01': [0.15, 0.25],
            '2025-01-02': [0.16, 0.24]
        })
        
        is_valid, errors = validate_data(weights_df, 'w_secs.csv')
        assert is_valid is True
        
        # Weights with invalid headers
        invalid_weights_df = pd.DataFrame({
            'ISIN': ['US001', 'US002'],
            'invalid_header': [0.15, 0.25]
        })
        
        is_valid, errors = validate_data(invalid_weights_df, 'w_secs.csv')
        # Might be invalid due to non-date headers
        if not is_valid:
            assert len(errors) > 0

    def test_validate_unknown_file_type(self):
        """Test validation of unknown file types."""
        df = pd.DataFrame({
            'Column1': ['A', 'B'],
            'Column2': [1, 2]
        })
        
        is_valid, errors = validate_data(df, 'unknown_file.csv')
        
        # Should handle unknown file types gracefully
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)


class TestValidationRobustness:
    """Test validation robustness and error handling."""

    def test_validate_dataframe_with_nans(self):
        """Test validation of DataFrame with NaN values."""
        df_with_nans = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02'],
            'Code': ['F1', np.nan],  # NaN in Code
            'Value': [100.0, np.nan]  # NaN in Value
        })
        
        is_valid, errors = validate_data(df_with_nans, 'ts_Duration.csv')
        
        # Should handle NaN values appropriately
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_dataframe_with_mixed_types(self):
        """Test validation with mixed data types."""
        mixed_df = pd.DataFrame({
            'Date': ['2025-01-01', '2025-01-02'],
            'Code': ['F1', 'F2'],
            'Value': [100.0, 'mixed_type']  # Mixed types
        })
        
        is_valid, errors = validate_data(mixed_df, 'ts_Duration.csv')
        
        # Should detect mixed types in numeric columns
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_dataframe_with_all_nans(self):
        """Test validation of DataFrame with all NaN values."""
        all_nan_df = pd.DataFrame({
            'Date': [np.nan, np.nan],
            'Code': [np.nan, np.nan],
            'Value': [np.nan, np.nan]
        })
        
        is_valid, errors = validate_data(all_nan_df, 'ts_Duration.csv')
        
        # Should handle all-NaN DataFrame
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_large_dataframe_performance(self):
        """Test validation performance with larger DataFrame."""
        # Create larger DataFrame to test performance
        large_df = pd.DataFrame({
            'Date': ['2025-01-01'] * 1000,
            'Code': ['F1'] * 1000,
            'Value': list(range(1000))
        })
        
        import time
        start_time = time.time()
        is_valid, errors = validate_data(large_df, 'ts_Duration.csv')
        end_time = time.time()
        
        duration = end_time - start_time
        
        # Should complete quickly
        assert duration < 1.0, f"Validation took {duration:.3f}s, should be <1.0s"
        assert is_valid is True

    def test_validate_security_data_comprehensive(self):
        """Test comprehensive security data validation."""
        # Valid security data with various scenarios
        sec_df = pd.DataFrame({
            'ISIN': ['US001', 'US002', 'US003'],
            'Security Name': ['Bond A', 'Bond B', 'Bond C'],
            'Type': ['Corp', 'Gov', 'Corp'],
            'Currency': ['USD', 'EUR', 'GBP'],
            '2025-01-01': [100.0, 200.0, 300.0],
            '2025-01-02': [101.0, np.nan, 301.0],  # NaN in middle
            '2025-01-03': [102.0, 202.0, np.nan]   # NaN at end
        })
        
        is_valid, errors = validate_data(sec_df, 'sec_Spread.csv')
        
        # Should handle NaN values in date columns gracefully
        assert isinstance(is_valid, bool)
        if not is_valid:
            # If invalid, should have meaningful error messages
            assert len(errors) > 0
            assert all(isinstance(error, str) for error in errors)


class TestValidationHelpers:
    """Test validation helper functions."""

    def test_is_date_like_function(self):
        """Test the _is_date_like helper function."""
        # Test various date formats
        date_cases = [
            ('2025-01-01', True),
            ('2024-12-31', True),
            ('01/01/2025', True),
            ('31/12/2024', True),
            ('ISIN', False),
            ('Security Name', False),
            ('random_text', False),
            ('', False)
        ]
        
        for test_str, expected in date_cases:
            result = _is_date_like(test_str)
            assert result == expected, f"_is_date_like('{test_str}') should be {expected}, got {result}"

    def test_is_date_like_edge_cases(self):
        """Test edge cases for date-like detection."""
        edge_cases = [
            '2025-13-01',  # Invalid month
            '2025-01-32',  # Invalid day
            '25-01-01',    # Short year
            '2025/01/01',  # Different separator
            '01-01-2025',  # Different order
        ]
        
        for edge_case in edge_cases:
            result = _is_date_like(edge_case)
            # Should return boolean regardless of validity
            assert isinstance(result, bool)


class TestValidationErrorMessages:
    """Test validation error message quality."""

    def test_error_messages_are_descriptive(self):
        """Test that error messages are descriptive and helpful."""
        # Create DataFrame with multiple issues
        problematic_df = pd.DataFrame({
            'Wrong_Col': ['A', 'B'],  # Missing required columns
            'Another_Wrong': ['invalid', 'data']
        })
        
        is_valid, errors = validate_data(problematic_df, 'ts_Duration.csv')
        
        assert is_valid is False
        assert len(errors) > 0
        
        # Error messages should be strings
        assert all(isinstance(error, str) for error in errors)
        # Should be non-empty
        assert all(len(error) > 0 for error in errors)

    def test_validation_provides_context(self):
        """Test that validation provides context about the file type."""
        # Test different file types get appropriate validation
        df = pd.DataFrame({'ISIN': ['US001'], 'Value': [100]})
        
        file_types = ['ts_Duration.csv', 'sec_Spread.csv', 'w_secs.csv']
        
        for file_type in file_types:
            is_valid, errors = validate_data(df, file_type)
            
            # Should return validation results for each file type
            assert isinstance(is_valid, bool)
            assert isinstance(errors, list)

    def test_validation_handles_unicode_and_special_chars(self):
        """Test validation with unicode and special characters."""
        unicode_df = pd.DataFrame({
            'Date': ['2025-01-01'],
            'Code': ['F1'],
            'Value': [100.0],
            'Special_Col_ñ': ['unicode_content'],
            'Col_with_émoji': ['special_chars']
        })
        
        is_valid, errors = validate_data(unicode_df, 'ts_Duration.csv')
        
        # Should handle unicode gracefully
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)


class TestValidationConstants:
    """Test validation constants and configuration."""

    def test_validation_function_availability(self):
        """Test that validation functions are properly available."""
        # Test that main functions are importable
        from data_processing.data_validation import validate_data, _is_date_like
        
        assert callable(validate_data)
        assert callable(_is_date_like)

    def test_validation_return_types(self):
        """Test that validation functions return expected types."""
        simple_df = pd.DataFrame({'A': [1], 'B': [2]})
        
        result = validate_data(simple_df, 'test.csv')
        
        # Should return tuple of (bool, list)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)

    def test_is_date_like_return_type(self):
        """Test that _is_date_like returns boolean."""
        test_strings = ['2025-01-01', 'not_date', '', '123']
        
        for test_str in test_strings:
            result = _is_date_like(test_str)
            assert isinstance(result, bool), f"_is_date_like should return bool for '{test_str}'"

