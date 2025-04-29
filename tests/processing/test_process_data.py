# Purpose: Unit tests for process_data.py, covering header replacement and data aggregation logic.

import pytest
import pandas as pd
import numpy as np
import process_data
import logging


# Dummy logger for testing
class DummyLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg, exc_info=None):
        pass

    def isEnabledFor(self, level):
        return False


# --- replace_headers_with_dates ---
def test_replace_headers_with_dates():
    df = pd.DataFrame(
        {
            "Funds": ["A", "B"],
            "Security Name": ["Sec1", "Sec2"],
            "Col": [1, 2],
            "Col.1": [3, 4],
        }
    )
    required_cols = ["Funds", "Security Name"]
    candidate_start_index = 2
    candidate_cols = ["Col", "Col.1"]
    date_columns = ["2024-01-01", "2024-01-02"]
    dates_file_path = "dummy_dates.csv"
    logger = DummyLogger()
    input_path = "dummy_input.csv"
    result = process_data.replace_headers_with_dates(
        df.copy(),
        required_cols,
        candidate_start_index,
        candidate_cols,
        date_columns,
        dates_file_path,
        logger,
        input_path,
    )
    assert all(date in result.columns for date in date_columns)


# --- aggregate_data ---
def test_aggregate_data():
    df = pd.DataFrame(
        {
            "Funds": ["A", "A", "B"],
            "Security Name": ["Sec1", "Sec1", "Sec2"],
            "ISIN": ["X", "X", "Y"],
            "Other": [1, 2, 3],
        }
    )
    required_cols = ["Funds", "Security Name"]
    logger = DummyLogger()
    input_path = "dummy_input.csv"
    result = process_data.aggregate_data(df, required_cols, logger, input_path)
    assert not result.empty
    assert "Funds" in result.columns
    assert "Security Name" in result.columns
    assert "ISIN" in result.columns
    assert any(
        "[" in str(f) for f in result["Funds"]
    )  # Funds aggregated as list-like string
