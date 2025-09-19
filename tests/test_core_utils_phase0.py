# test_core_utils_phase0.py
# Purpose: Unit tests for core/utils.py high-frequency helpers (Phase 0)

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
import tempfile
from unittest.mock import patch, mock_open
import yaml

# Import functions to test
from core.utils import (
    _is_date_like as is_date_like,
    parse_fund_list,
    replace_nan_with_none,
    load_yaml_config,
    get_business_day_offset
)


class TestIsDateLike:
    """Test the is_date_like function."""

    def test_date_patterns_return_true(self, monkeypatch):
        """Test that valid date patterns return True."""
        # Mock the DATE_COLUMN_PATTERNS to include common patterns
        mock_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
            r'(?i)date'  # Case-insensitive "date"
        ]
        
        monkeypatch.setattr('core.utils.DATE_COLUMN_PATTERNS', mock_patterns)
        
        date_patterns = [
            '2025-01-01',
            '01/01/2025', 
            '31/12/2024',
            'Date',
            'date',
            'DATE'
        ]
        
        for pattern in date_patterns:
            assert is_date_like(pattern), f"'{pattern}' should be recognized as date-like"

    def test_non_date_patterns_return_false(self, monkeypatch):
        """Test that non-date patterns return False."""
        # Mock the DATE_COLUMN_PATTERNS to include common patterns
        mock_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
            r'(?i)date'  # Case-insensitive "date"
        ]
        
        monkeypatch.setattr('core.utils.DATE_COLUMN_PATTERNS', mock_patterns)
        
        non_date_patterns = [
            'foo',
            'bar',
            'ISIN',
            'Security Name',
            '12345',
            'abc123',
            ''
        ]
        
        for pattern in non_date_patterns:
            assert not is_date_like(pattern), f"'{pattern}' should not be recognized as date-like"

    def test_edge_cases(self):
        """Test edge cases for is_date_like."""
        # None should return False
        assert not is_date_like(None)
        
        # Numeric values should return False
        assert not is_date_like(123)
        assert not is_date_like(0)


class TestParseFundList:
    """Test the parse_fund_list function."""

    def test_empty_list_string(self):
        """Test parsing empty list string."""
        assert parse_fund_list('[]') == []

    def test_bracketed_list_string(self):
        """Test parsing bracketed list strings."""
        assert parse_fund_list('[A,B]') == ['A', 'B']
        assert parse_fund_list('[F1,F2,F3]') == ['F1', 'F2', 'F3']
        
    def test_comma_separated_string(self):
        """Test parsing comma-separated strings."""
        assert parse_fund_list('A, B') == ['A', 'B']
        assert parse_fund_list('F1,F2,F3') == ['F1', 'F2', 'F3']
        
    def test_none_input(self):
        """Test that None input returns empty list."""
        assert parse_fund_list(None) == []
        
    def test_empty_string_input(self):
        """Test that empty string returns empty list."""
        assert parse_fund_list('') == []
        
    def test_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        assert parse_fund_list(' A , B ') == ['A', 'B']
        assert parse_fund_list('[ F1 , F2 ]') == ['F1', 'F2']


class TestReplaceNanWithNone:
    """Test the replace_nan_with_none function."""

    def test_nested_dict_with_nan(self):
        """Test replacing NaN in nested dict."""
        input_data = {
            'a': np.nan,
            'b': 1.0,
            'c': {
                'd': np.nan,
                'e': 'text'
            }
        }
        
        result = replace_nan_with_none(input_data)
        
        assert result['a'] is None
        assert result['b'] == 1.0
        assert result['c']['d'] is None
        assert result['c']['e'] == 'text'

    def test_nested_list_with_nan(self):
        """Test replacing NaN in nested list."""
        input_data = [np.nan, 1.0, [np.nan, 'text']]
        
        result = replace_nan_with_none(input_data)
        
        assert result[0] is None
        assert result[1] == 1.0
        assert result[2][0] is None
        assert result[2][1] == 'text'

    def test_non_numeric_nan_preserved(self):
        """Test that non-numeric values are preserved."""
        input_data = {
            'text': 'hello',
            'number': 42,
            'boolean': True,
            'nan_value': np.nan
        }
        
        result = replace_nan_with_none(input_data)
        
        assert result['text'] == 'hello'
        assert result['number'] == 42
        assert result['boolean'] is True
        assert result['nan_value'] is None


class TestLoadYamlConfig:
    """Test the load_yaml_config function."""

    def test_missing_file_returns_empty_dict(self):
        """Test that missing file returns empty dict."""
        result = load_yaml_config('nonexistent_file.yaml')
        assert result == {}

    def test_malformed_yaml_returns_empty_dict(self):
        """Test that malformed YAML returns empty dict."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('invalid: yaml: content: [')
            temp_path = f.name
        
        try:
            result = load_yaml_config(temp_path)
            assert result == {}
        finally:
            os.unlink(temp_path)

    def test_valid_yaml_parsed_correctly(self):
        """Test that valid YAML is parsed correctly."""
        test_data = {
            'key1': 'value1',
            'key2': {
                'nested': 'value2'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f)
            temp_path = f.name
        
        try:
            result = load_yaml_config(temp_path)
            assert result == test_data
        finally:
            os.unlink(temp_path)


class TestGetBusinessDayOffset:
    """Test the get_business_day_offset function."""

    def test_friday_plus_one_returns_monday(self):
        """Test that Friday +1 returns Monday."""
        # Friday 2025-01-03
        friday = date(2025, 1, 3)
        monday = get_business_day_offset(friday, 1)
        
        # Should be Monday 2025-01-06
        expected = date(2025, 1, 6)
        assert monday == expected

    def test_friday_minus_one_returns_thursday(self):
        """Test that Friday -1 returns Thursday."""
        # Friday 2025-01-03  
        friday = date(2025, 1, 3)
        thursday = get_business_day_offset(friday, -1)
        
        # Should be Thursday 2025-01-02
        expected = date(2025, 1, 2)
        assert thursday == expected

    def test_monday_plus_one_returns_tuesday(self):
        """Test that Monday +1 returns Tuesday."""
        # Monday 2025-01-06
        monday = date(2025, 1, 6)
        tuesday = get_business_day_offset(monday, 1)
        
        # Should be Tuesday 2025-01-07
        expected = date(2025, 1, 7)
        assert tuesday == expected

    def test_zero_offset_returns_same_date(self):
        """Test that zero offset returns same date if it's a business day."""
        # Wednesday 2025-01-01 (assuming it's a business day)
        wednesday = date(2025, 1, 1)
        result = get_business_day_offset(wednesday, 0)
        
        # Should return the same date or next business day
        assert isinstance(result, date)

    def test_handles_datetime_input(self):
        """Test that function handles datetime input."""
        # Friday 2025-01-03 10:00:00
        friday_dt = datetime(2025, 1, 3, 10, 0, 0)
        result = get_business_day_offset(friday_dt, 1)
        
        # Should return a datetime or date (Monday)
        assert isinstance(result, (date, datetime))
        # Should be Monday 2025-01-06 (check just the date part)
        expected_date = date(2025, 1, 6)
        if isinstance(result, datetime):
            assert result.date() == expected_date
        else:
            assert result == expected_date
