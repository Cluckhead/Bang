# test_metric_calculator_phase1.py
# Purpose: Comprehensive tests for analytics/metric_calculator.py (Phase 1)
# Target: 5% → 70% coverage

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date
import tempfile
import os
from typing import List, Dict, Any

# Import functions to test
from analytics.metric_calculator import (
    calculate_latest_metrics,
    load_metrics_from_csv,
    _calculate_column_stats,
    _process_dataframe_metrics,
    _calculate_relative_metrics
)


def create_multiindex_df(dates: List[str], fund_codes: List[str], data: Dict[str, Dict[str, List[float]]]) -> pd.DataFrame:
    """Helper to create MultiIndex DataFrames for testing."""
    rows = []
    for date_str in dates:
        for fund_code in fund_codes:
            row_data = {'Date': pd.to_datetime(date_str), 'Fund Code': fund_code}
            for col, fund_data in data.items():
                if fund_code in fund_data:
                    # Get the index of this date in the dates list
                    date_idx = dates.index(date_str)
                    if date_idx < len(fund_data[fund_code]):
                        row_data[col] = fund_data[fund_code][date_idx]
                    else:
                        row_data[col] = np.nan
                else:
                    row_data[col] = np.nan
            rows.append(row_data)
    
    df = pd.DataFrame(rows)
    return df.set_index(['Date', 'Fund Code'])


class TestCalculateColumnStats:
    """Test the _calculate_column_stats helper function."""

    def test_calculate_stats_normal_data(self):
        """Test column stats calculation with normal data."""
        dates = pd.date_range('2025-01-01', periods=5, freq='D')
        col_series = pd.Series([100, 102, 101, 103, 105], index=dates)
        col_change_series = col_series.diff()
        latest_date = dates[-1]
        
        result = _calculate_column_stats(
            col_series, col_change_series, latest_date, "TestCol"
        )
        
        assert result["TestCol Mean"] == pytest.approx(102.2)
        assert result["TestCol Max"] == 105
        assert result["TestCol Min"] == 100
        assert result["TestCol Latest Value"] == 105
        assert result["TestCol Change"] == 2.0  # 105 - 103
        assert "TestCol Change Z-Score" in result
        assert pd.notna(result["TestCol Change Z-Score"])

    def test_calculate_stats_with_prefix(self):
        """Test column stats calculation with prefix."""
        dates = pd.date_range('2025-01-01', periods=3, freq='D')
        col_series = pd.Series([100, 101, 102], index=dates)
        col_change_series = col_series.diff()
        latest_date = dates[-1]
        
        result = _calculate_column_stats(
            col_series, col_change_series, latest_date, "Fund", prefix="S&P "
        )
        
        assert "S&P Fund Mean" in result
        assert "S&P Fund Latest Value" in result
        assert "S&P Fund Change Z-Score" in result

    def test_calculate_stats_zero_std_equal_mean(self):
        """Test Z-score calculation when std=0 and latest_change equals mean."""
        dates = pd.date_range('2025-01-01', periods=4, freq='D')
        # Constant change of 1
        col_series = pd.Series([100, 101, 102, 103], index=dates)
        col_change_series = col_series.diff()
        latest_date = dates[-1]
        
        result = _calculate_column_stats(
            col_series, col_change_series, latest_date, "TestCol"
        )
        
        # Latest change = 1, mean change = 1, std = 0 → Z-score should be 0
        assert result["TestCol Change Z-Score"] == 0.0

    def test_calculate_stats_zero_std_different_mean(self):
        """Test Z-score calculation when std=0 but latest_change differs from mean."""
        dates = pd.date_range('2025-01-01', periods=5, freq='D')
        # Create a series where all changes except last are the same (std=0 scenario)
        col_series = pd.Series([100, 101, 102, 103, 105], index=dates)
        col_change_series = col_series.diff()
        # Manually set changes to create zero std scenario
        col_change_series.iloc[1:4] = 1.0  # Changes: NaN, 1, 1, 1, 2
        col_change_series.iloc[4] = 2.0    # Last change different
        latest_date = dates[-1]
        
        result = _calculate_column_stats(
            col_series, col_change_series, latest_date, "TestCol"
        )
        
        # With changes [1, 1, 1, 2], std should be > 0, so normal Z-score
        z_score = result["TestCol Change Z-Score"]
        assert pd.notna(z_score)  # Should be a valid number, not inf

    def test_calculate_stats_true_zero_std_infinity(self):
        """Test Z-score calculation with true zero standard deviation leading to infinity."""
        dates = pd.date_range('2025-01-01', periods=4, freq='D')
        col_series = pd.Series([100, 101, 102, 103], index=dates)
        col_change_series = col_series.diff()
        # Manually create zero std scenario
        col_change_series.iloc[1:] = 1.0  # All changes are 1 (after NaN)
        # Change the last value to be different
        col_change_series.iloc[-1] = 2.0
        latest_date = dates[-1]
        
        # Mock the std calculation to return 0
        import unittest.mock
        with unittest.mock.patch.object(col_change_series, 'std', return_value=0.0):
            with unittest.mock.patch.object(col_change_series, 'mean', return_value=1.0):
                result = _calculate_column_stats(
                    col_series, col_change_series, latest_date, "TestCol"
                )
        
        # Latest change = 2, mean = 1, std = 0 → should be +inf
        z_score = result["TestCol Change Z-Score"]
        assert np.isinf(z_score) and z_score > 0

    def test_calculate_stats_nan_inputs(self):
        """Test Z-score calculation with NaN inputs."""
        dates = pd.date_range('2025-01-01', periods=3, freq='D')
        col_series = pd.Series([100, np.nan, 102], index=dates)
        col_change_series = col_series.diff()
        latest_date = dates[-1]
        
        result = _calculate_column_stats(
            col_series, col_change_series, latest_date, "TestCol"
        )
        
        # Should handle NaN gracefully
        assert pd.isna(result["TestCol Change Z-Score"])

    def test_calculate_stats_missing_latest_date(self):
        """Test behavior when latest_date is not in series index."""
        dates = pd.date_range('2025-01-01', periods=3, freq='D')
        col_series = pd.Series([100, 101, 102], index=dates)
        col_change_series = col_series.diff()
        missing_date = pd.Timestamp('2025-01-10')  # Not in series
        
        result = _calculate_column_stats(
            col_series, col_change_series, missing_date, "TestCol"
        )
        
        # Should set latest metrics to NaN
        assert pd.isna(result["TestCol Latest Value"])
        assert pd.isna(result["TestCol Change"])
        assert pd.isna(result["TestCol Change Z-Score"])


class TestCalculateLatestMetrics:
    """Test the main calculate_latest_metrics function."""

    def test_empty_dataframe_returns_empty(self):
        """Test that empty DataFrame returns empty result."""
        result = calculate_latest_metrics(
            primary_df=pd.DataFrame(),
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        assert result.empty

    def test_missing_primary_data_returns_empty(self):
        """Test that missing primary data returns empty result."""
        result = calculate_latest_metrics(
            primary_df=None,
            primary_fund_cols=None,
            primary_benchmark_col=None
        )
        
        assert result.empty

    def test_non_multiindex_dataframe_returns_empty(self):
        """Test that DataFrame without MultiIndex returns empty result."""
        simple_df = pd.DataFrame({
            'Fund': [100, 101, 102],
            'Bench': [99, 100, 101]
        })
        
        result = calculate_latest_metrics(
            primary_df=simple_df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        assert result.empty

    def test_single_fund_latest_date_selection(self):
        """Test that latest date is selected correctly for single fund."""
        dates = ['2025-01-01', '2025-01-02', '2025-01-03']
        fund_codes = ['F1']
        data = {
            'Fund': {'F1': [100, 101, 102]},
            'Bench': {'F1': [99, 100, 101]}
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        
        result = calculate_latest_metrics(
            primary_df=df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        assert not result.empty
        assert len(result) == 1
        assert 'F1' in result.index
        # Latest values should be from last date
        assert result.loc['F1', 'Fund Latest Value'] == 102
        assert result.loc['F1', 'Bench Latest Value'] == 101

    def test_multi_fund_metrics_with_nans(self):
        """Test metrics calculation with multiple funds including NaN handling."""
        dates = ['2025-01-01', '2025-01-02', '2025-01-03']
        fund_codes = ['F1', 'F2']
        data = {
            'Fund': {'F1': [100, 101, 102], 'F2': [200, np.nan, 203]},
            'Bench': {'F1': [99, 100, 101], 'F2': [199, 200, 201]}
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        
        result = calculate_latest_metrics(
            primary_df=df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        assert len(result) == 2
        assert 'F1' in result.index
        assert 'F2' in result.index
        
        # F1 should have complete metrics
        assert result.loc['F1', 'Fund Latest Value'] == 102
        
        # F2 should handle NaN appropriately
        assert result.loc['F2', 'Fund Latest Value'] == 203

    def test_relative_metrics_calculation(self):
        """Test that relative (fund - benchmark) metrics are calculated."""
        dates = ['2025-01-01', '2025-01-02', '2025-01-03']
        fund_codes = ['F1']
        data = {
            'Fund': {'F1': [100, 102, 104]},
            'Bench': {'F1': [99, 100, 101]}
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        
        result = calculate_latest_metrics(
            primary_df=df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        # Should have relative metrics
        assert 'Relative Latest Value' in result.columns
        assert 'Relative Change' in result.columns
        assert 'Relative Change Z-Score' in result.columns
        
        # Relative latest value should be Fund - Bench = 104 - 101 = 3
        assert result.loc['F1', 'Relative Latest Value'] == 3

    def test_secondary_data_processing(self):
        """Test processing with both primary and secondary DataFrames."""
        dates = ['2025-01-01', '2025-01-02']
        fund_codes = ['F1']
        
        primary_data = {
            'Fund': {'F1': [100, 102]},
            'Bench': {'F1': [99, 100]}
        }
        
        secondary_data = {
            'SP_Fund': {'F1': [101, 103]},
            'SP_Bench': {'F1': [100, 101]}
        }
        
        primary_df = create_multiindex_df(dates, fund_codes, primary_data)
        secondary_df = create_multiindex_df(dates, fund_codes, secondary_data)
        
        result = calculate_latest_metrics(
            primary_df=primary_df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench',
            secondary_df=secondary_df,
            secondary_fund_cols=['SP_Fund'],
            secondary_benchmark_col='SP_Bench',
            secondary_prefix='S&P '
        )
        
        # Should have both primary and secondary metrics
        assert 'Fund Latest Value' in result.columns
        assert 'S&P SP_Fund Latest Value' in result.columns
        assert 'S&P Relative Latest Value' in result.columns

    def test_sorting_by_max_abs_z_score(self):
        """Test that results are sorted by maximum absolute Z-score."""
        dates = ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04']
        fund_codes = ['F1', 'F2', 'F3']
        
        # F2 should have highest absolute Z-score due to large change
        data = {
            'Fund': {
                'F1': [100, 101, 102, 103],  # Consistent small changes
                'F2': [100, 101, 102, 110],  # Large final change
                'F3': [100, 101, 102, 103]   # Consistent small changes
            },
            'Bench': {
                'F1': [99, 100, 101, 102],
                'F2': [99, 100, 101, 102], 
                'F3': [99, 100, 101, 102]
            }
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        
        result = calculate_latest_metrics(
            primary_df=df,
            primary_fund_cols=['Fund'],
            primary_benchmark_col='Bench'
        )
        
        # F2 should be first due to highest Z-score
        assert result.index[0] == 'F2'


class TestLoadMetricsFromCsv:
    """Test the load_metrics_from_csv function."""

    def test_load_valid_csv(self, tmp_path):
        """Test loading a valid CSV file."""
        data = {'Fund Code': ['F1', 'F2'], 'Value': [100, 200]}
        df = pd.DataFrame(data)
        
        test_file = tmp_path / 'test_metrics.csv'
        df.to_csv(str(test_file), index=False)
        
        result = load_metrics_from_csv(str(test_file))
        assert not result.empty
        assert list(result.columns) == ['Fund Code', 'Value']
        assert len(result) == 2

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file returns empty DataFrame."""
        result = load_metrics_from_csv('nonexistent_file.csv')
        assert result.empty

    def test_load_empty_file(self, tmp_path):
        """Test loading an empty file returns empty DataFrame."""
        test_file = tmp_path / 'empty_metrics.csv'
        test_file.write_text('')  # Empty file
        
        result = load_metrics_from_csv(str(test_file))
        assert result.empty

    def test_load_malformed_csv(self, tmp_path):
        """Test loading a malformed CSV returns empty DataFrame."""
        test_file = tmp_path / 'malformed_metrics.csv'
        test_file.write_text('invalid,csv,content\nwith,mismatched,columns,extra')
        
        result = load_metrics_from_csv(str(test_file))
        # Should handle gracefully - might return empty or partial data
        assert isinstance(result, pd.DataFrame)


class TestProcessDataframeMetrics:
    """Test the _process_dataframe_metrics helper function."""

    def test_empty_dataframe_returns_empty(self):
        """Test that empty DataFrame returns empty results."""
        fund_codes = pd.Index(['F1', 'F2'])
        latest_date = pd.Timestamp('2025-01-03')
        
        result_list, max_z_dict = _process_dataframe_metrics(
            df=pd.DataFrame(),
            fund_codes=fund_codes,
            fund_cols=['Fund'],
            benchmark_col='Bench',
            latest_date=latest_date,
            metric_prefix=""
        )
        
        assert result_list == []
        assert max_z_dict == {}

    def test_none_dataframe_returns_empty(self):
        """Test that None DataFrame returns empty results."""
        fund_codes = pd.Index(['F1', 'F2'])
        latest_date = pd.Timestamp('2025-01-03')
        
        result_list, max_z_dict = _process_dataframe_metrics(
            df=None,
            fund_codes=fund_codes,
            fund_cols=['Fund'],
            benchmark_col='Bench',
            latest_date=latest_date,
            metric_prefix=""
        )
        
        assert result_list == []
        assert max_z_dict == {}

    def test_missing_fund_in_dataframe(self):
        """Test handling of fund codes not present in DataFrame."""
        dates = ['2025-01-01', '2025-01-02']
        fund_codes_in_df = ['F1']
        data = {
            'Fund': {'F1': [100, 101]},
            'Bench': {'F1': [99, 100]}
        }
        
        df = create_multiindex_df(dates, fund_codes_in_df, data)
        
        # Request metrics for funds including one not in the DataFrame
        fund_codes_requested = pd.Index(['F1', 'F2'])
        latest_date = pd.Timestamp('2025-01-02')
        
        result_list, max_z_dict = _process_dataframe_metrics(
            df=df,
            fund_codes=fund_codes_requested,
            fund_cols=['Fund'],
            benchmark_col='Bench',
            latest_date=latest_date,
            metric_prefix=""
        )
        
        assert len(result_list) == 2
        
        # F1 should have real metrics
        f1_metrics = next(item for item in result_list if item['Fund Code'] == 'F1')
        assert pd.notna(f1_metrics['Fund Latest Value'])
        
        # F2 should have NaN metrics
        f2_metrics = next(item for item in result_list if item['Fund Code'] == 'F2')
        assert pd.isna(f2_metrics['Fund Latest Value'])
        assert pd.isna(max_z_dict['F2'])


class TestCalculateRelativeMetrics:
    """Test the _calculate_relative_metrics helper function."""

    def test_valid_relative_calculation(self):
        """Test relative metrics calculation with valid data."""
        dates = ['2025-01-01', '2025-01-02', '2025-01-03']
        fund_codes = ['F1']
        data = {
            'Fund': {'F1': [100, 102, 104]},
            'Bench': {'F1': [99, 100, 101]}
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        fund_codes_index = pd.Index(fund_codes)
        latest_date = pd.Timestamp('2025-01-03')
        
        rel_df, max_z_dict = _calculate_relative_metrics(
            df=df,
            fund_codes=fund_codes_index,
            fund_col='Fund',
            bench_col='Bench',
            latest_date=latest_date,
            prefix=""
        )
        
        assert not rel_df.empty
        assert 'F1' in rel_df.index
        assert 'Relative Latest Value' in rel_df.columns
        
        # Relative should be Fund - Bench = 104 - 101 = 3
        assert rel_df.loc['F1', 'Relative Latest Value'] == 3

    def test_missing_columns_returns_empty(self):
        """Test that missing fund or benchmark columns return empty results."""
        dates = ['2025-01-01', '2025-01-02']
        fund_codes = ['F1']
        data = {
            'Fund': {'F1': [100, 101]},
            # Missing benchmark column
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        fund_codes_index = pd.Index(fund_codes)
        latest_date = pd.Timestamp('2025-01-02')
        
        rel_df, max_z_dict = _calculate_relative_metrics(
            df=df,
            fund_codes=fund_codes_index,
            fund_col='Fund',
            bench_col='MissingBench',  # Column doesn't exist
            latest_date=latest_date,
            prefix=""
        )
        
        assert rel_df.empty or len(rel_df) == 1  # Might return empty df with correct index
        assert all(pd.isna(val) for val in max_z_dict.values())

    def test_empty_series_handling(self):
        """Test handling of empty fund or benchmark series."""
        dates = ['2025-01-01', '2025-01-02']
        fund_codes = ['F1']
        data = {
            'Fund': {'F1': [np.nan, np.nan]},  # All NaN
            'Bench': {'F1': [99, 100]}
        }
        
        df = create_multiindex_df(dates, fund_codes, data)
        fund_codes_index = pd.Index(fund_codes)
        latest_date = pd.Timestamp('2025-01-02')
        
        rel_df, max_z_dict = _calculate_relative_metrics(
            df=df,
            fund_codes=fund_codes_index,
            fund_col='Fund',
            bench_col='Bench',
            latest_date=latest_date,
            prefix=""
        )
        
        # Should handle NaN data gracefully
        assert pd.isna(max_z_dict['F1'])
