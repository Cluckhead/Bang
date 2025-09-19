# test_maxmin_basic.py
# Purpose: Basic tests for analytics/maxmin_processing.py core functionality

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
import os
from typing import Dict, Any

from analytics.maxmin_processing import (
    find_value_breaches,
    _load_distressed_isins,
    DEFAULT_MAX_THRESHOLD,
    DEFAULT_MIN_THRESHOLD
)


def create_basic_csv(path: str, data: Dict[str, Any]) -> None:
    """Helper to create basic test CSV files."""
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)


class TestBasicBreachDetection:
    """Test basic breach detection functionality."""

    def test_simple_max_breach(self, tmp_path):
        """Test detection of a simple max threshold breach."""
        # Create test data with ISIN first, then enough metadata columns
        test_data = {
            'ISIN': ['US0000001'],       # Col 0 (id_column)
            'Security Name': ['Bond A'], # Col 1
            'Funds': ['[F1]'],           # Col 2
            'Type': ['Corp'],            # Col 3
            'Currency': ['USD'],         # Col 4
            'Date': [''],                # Col 5
            'Code': [''],                # Col 6
            'Fund Code': [''],           # Col 7
            '2025-01-01': [150.0]        # Col 8+ (date columns start here)
        }
        
        test_file = tmp_path / "sec_TestMetric.csv"
        create_basic_csv(str(test_file), test_data)
        
        breaches, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=100.0,
            min_threshold=0.0,
            include_distressed=True
        )
        
        assert total_count == 1
        assert len(breaches) >= 1
        
        # Find the max breach
        max_breach = next((b for b in breaches if b['breach_type'] == 'max'), None)
        assert max_breach is not None
        assert max_breach['id'] == 'US0000001'
        assert max_breach['value'] == 150.0
        assert max_breach['threshold'] == 100.0

    def test_simple_min_breach(self, tmp_path):
        """Test detection of a simple min threshold breach."""
        test_data = {
            'ISIN': ['US0000001'],
            'Security Name': ['Bond A'],
            'Funds': ['[F1]'],
            'Type': ['Corp'],
            'Currency': ['USD'],
            'Date': [''],
            'Code': [''],
            'Fund Code': [''],
            '2025-01-01': [10.0]  # Below threshold of 20
        }
        
        test_file = tmp_path / "sec_TestMetric.csv"
        create_basic_csv(str(test_file), test_data)
        
        breaches, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=1000.0,
            min_threshold=20.0,
            include_distressed=True
        )
        
        assert total_count == 1
        assert len(breaches) >= 1
        
        # Find the min breach
        min_breach = next((b for b in breaches if b['breach_type'] == 'min'), None)
        assert min_breach is not None
        assert min_breach['id'] == 'US0000001'
        assert min_breach['value'] == 10.0
        assert min_breach['threshold'] == 20.0

    def test_no_breaches_within_thresholds(self, tmp_path):
        """Test that values within thresholds don't create breaches."""
        test_data = {
            'ISIN': ['US0000001'],
            'Security Name': ['Bond A'],
            'Funds': ['[F1]'],
            'Type': ['Corp'],
            'Currency': ['USD'],
            'Date': [''],
            'Code': [''],
            'Fund Code': [''],
            '2025-01-01': [50.0]  # Within thresholds
        }
        
        test_file = tmp_path / "sec_TestMetric.csv"
        create_basic_csv(str(test_file), test_data)
        
        breaches, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=100.0,
            min_threshold=0.0,
            include_distressed=True
        )
        
        assert total_count == 1
        assert len(breaches) == 0  # No breaches expected

    def test_ignores_nan_values(self, tmp_path):
        """Test that NaN values are ignored."""
        test_data = {
            'ISIN': ['US0000001'],
            'Security Name': ['Bond A'],
            'Funds': ['[F1]'],
            'Type': ['Corp'],
            'Currency': ['USD'],
            'Date': [''],
            'Code': [''],
            'Fund Code': [''],
            '2025-01-01': [np.nan],  # NaN should be ignored
            '2025-01-02': [150.0]    # This should breach
        }
        
        test_file = tmp_path / "sec_TestMetric.csv"
        create_basic_csv(str(test_file), test_data)
        
        breaches, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=100.0,
            min_threshold=0.0,
            include_distressed=True
        )
        
        assert total_count == 1
        # Should only find one breach (from 2025-01-02)
        assert len(breaches) == 1
        assert breaches[0]['value'] == 150.0
        assert breaches[0]['date'] == '2025-01-02'


class TestLoadDistressedIsinsBasic:
    """Test the distressed ISINs loading functionality."""

    def test_loads_distressed_from_reference(self, tmp_path):
        """Test loading distressed ISINs from reference.csv."""
        reference_data = {
            'ISIN': ['US0000001', 'US0000002'],
            'Security Name': ['Bond A', 'Bond B'],
            'Is Distressed': ['TRUE', 'FALSE']
        }
        
        create_basic_csv(str(tmp_path / "reference.csv"), reference_data)
        
        distressed_isins = _load_distressed_isins(str(tmp_path))
        
        assert 'US0000001' in distressed_isins
        assert 'US0000002' not in distressed_isins

    def test_handles_missing_reference(self, tmp_path):
        """Test handling when reference.csv is missing."""
        distressed_isins = _load_distressed_isins(str(tmp_path))
        assert distressed_isins == set()

    def test_distressed_exclusion_works(self, tmp_path):
        """Test that distressed securities are properly excluded."""
        # Create reference with distressed marking
        reference_data = {
            'ISIN': ['US0000001', 'US0000002'],
            'Security Name': ['Bond A', 'Bond B'],
            'Is Distressed': ['TRUE', 'FALSE']
        }
        create_basic_csv(str(tmp_path / "reference.csv"), reference_data)
        
        # Create test data where both would breach
        test_data = {
            'ISIN': ['US0000001', 'US0000002'],
            'Security Name': ['Bond A', 'Bond B'],
            'Funds': ['[F1]', '[F2]'],
            'Type': ['Corp', 'Corp'],
            'Currency': ['USD', 'USD'],
            'Date': ['', ''],
            'Code': ['', ''],
            'Fund Code': ['', ''],
            '2025-01-01': [150.0, 150.0]  # Both above threshold
        }
        
        test_file = tmp_path / "sec_TestMetric.csv"
        create_basic_csv(str(test_file), test_data)
        
        # Test excluding distressed
        breaches_excluded, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=100.0,
            include_distressed=False
        )
        
        # Test including distressed
        breaches_included, total_count = find_value_breaches(
            filename="sec_TestMetric.csv",
            data_folder=str(tmp_path),
            max_threshold=100.0,
            include_distressed=True
        )
        
        # Should have fewer breaches when excluding distressed
        assert len(breaches_excluded) < len(breaches_included) or (len(breaches_excluded) == 0 and len(breaches_included) > 0)


class TestConstants:
    """Test module constants."""

    def test_constants_defined(self):
        """Test that constants are properly defined."""
        assert DEFAULT_MAX_THRESHOLD == 10000
        assert DEFAULT_MIN_THRESHOLD == -100
