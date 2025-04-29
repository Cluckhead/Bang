# Purpose: Unit tests for security_processing.py, covering security data loading, melting, and latest metrics calculation.

import pytest
import pandas as pd
import numpy as np
import os
import security_processing


# --- load_and_process_security_data ---
def test_load_and_process_security_data_valid(tmp_path):
    # Create a wide-format CSV file
    df = pd.DataFrame(
        {
            "ISIN": ["A", "B"],
            "StaticCol": ["X", "Y"],
            "2024-01-01": [1, 2],
            "2024-01-02": [3, 4],
        }
    )
    file_path = tmp_path / "sec_test.csv"
    df.to_csv(file_path, index=False)
    result, static_cols = security_processing.load_and_process_security_data(
        "sec_test.csv", str(tmp_path)
    )
    assert not result.empty
    assert "ISIN" in result.columns or "ISIN" in result.index.names
    assert "date" in [c.lower() for c in result.columns] or "date" in [
        c.lower() for c in result.index.names
    ]
    assert "value" in [c.lower() for c in result.columns]
    assert isinstance(static_cols, list)


# --- calculate_security_latest_metrics ---
def test_calculate_security_latest_metrics():
    # Create a long-format DataFrame with MultiIndex
    df = pd.DataFrame(
        {
            "ISIN": ["A", "A", "B", "B"],
            "StaticCol": ["X", "X", "Y", "Y"],
            "Date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-02"]
            ),
            "Value": [1, 3, 2, 4],
        }
    )
    df.set_index(["Date", "ISIN"], inplace=True)
    result = security_processing.calculate_security_latest_metrics(
        df, static_cols=["StaticCol"]
    )
    assert not result.empty
    assert "Latest Value" in result.columns
    assert "Change" in result.columns
    assert "Change Z-Score" in result.columns
    assert "Mean" in result.columns
    assert "Max" in result.columns
    assert "Min" in result.columns
