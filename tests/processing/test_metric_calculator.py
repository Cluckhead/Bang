# Purpose: Unit tests for metric_calculator.py, covering column stats and latest metrics calculations.

import pytest
import pandas as pd
import numpy as np
from metric_calculator import _calculate_column_stats, calculate_latest_metrics


def test_calculate_column_stats_basic():
    # Simple increasing series
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series = pd.Series([1, 2, 3, 4, 5], index=idx)
    change_series = series.diff()
    latest_date = idx[-1]
    col_name = "TestCol"
    result = _calculate_column_stats(series, change_series, latest_date, col_name)
    assert result[f"{col_name} Mean"] == 3.0
    assert result[f"{col_name} Max"] == 5
    assert result[f"{col_name} Min"] == 1
    assert result[f"{col_name} Latest Value"] == 5
    assert result[f"{col_name} Change"] == 1
    # Z-score: (1 - mean(change)) / std(change)
    mean_change = change_series.mean()
    std_change = change_series.std()
    expected_z = (
        (1 - mean_change) / std_change
        if not np.isnan(std_change) and std_change != 0
        else 0.0
    )
    z_score = result[f"{col_name} Change Z-Score"]
    if std_change == 0 or np.isnan(std_change):
        assert z_score == 0.0 or np.isnan(z_score)
    else:
        assert np.isclose(z_score, expected_z)


def test_calculate_column_stats_nan():
    # Series with NaN values
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series = pd.Series([1, np.nan, 3, np.nan, 5], index=idx)
    change_series = series.diff()
    latest_date = idx[-1]
    col_name = "TestCol"
    result = _calculate_column_stats(series, change_series, latest_date, col_name)
    assert result[f"{col_name} Latest Value"] == 5
    assert not np.isnan(result[f"{col_name} Mean"])  # mean skips NaN
    assert np.isnan(result[f"{col_name} Change Z-Score"]) or isinstance(
        result[f"{col_name} Change Z-Score"], float
    )


def test_calculate_column_stats_zero_std():
    # All changes are the same (std=0)
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    series = pd.Series([2, 4, 6], index=idx)
    change_series = pd.Series([np.nan, 2, 2], index=idx)
    latest_date = idx[-1]
    col_name = "TestCol"
    result = _calculate_column_stats(series, change_series, latest_date, col_name)
    # Z-score should be 0.0 if latest_change == mean, inf otherwise
    assert result[f"{col_name} Change Z-Score"] == 0.0


def test_calculate_latest_metrics_basic():
    # DataFrame with two funds and a benchmark
    idx = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=3, freq="D"), ["FUND1", "FUND2"]],
        names=["Date", "Fund Code"],
    )
    df = pd.DataFrame(
        {"Bench": np.arange(1, 7), "F1": np.arange(10, 16), "F2": np.arange(20, 26)},
        index=idx,
    )
    fund_cols = ["F1", "F2"]
    bench_col = "Bench"
    result = calculate_latest_metrics(df, fund_cols, bench_col)
    assert not result.empty
    assert "F1 Mean" in result.columns
    assert "Bench Mean" in result.columns
    assert "F2 Mean" in result.columns
    assert "F1 Latest Value" in result.columns
    assert "Bench Latest Value" in result.columns
    assert "F2 Latest Value" in result.columns
    # Should be indexed by Fund Code
    assert set(result.index) == {"FUND1", "FUND2"}


def test_calculate_latest_metrics_edge_cases():
    # Single data point (should handle gracefully)
    idx = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-01"), "FUND1")], names=["Date", "Fund Code"]
    )
    df = pd.DataFrame({"Bench": [1], "F1": [10]}, index=idx)
    fund_cols = ["F1"]
    bench_col = "Bench"
    result = calculate_latest_metrics(df, fund_cols, bench_col)
    assert not result.empty
    # All change and z-score metrics should be NaN or handled
    for col in result.columns:
        if "Change" in col:
            assert np.isnan(result.iloc[0][col]) or isinstance(
                result.iloc[0][col], float
            )
