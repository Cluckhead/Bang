# Purpose: Unit tests for staleness_processing.py, covering staleness summary and stale securities details.

import pytest
import pandas as pd
import numpy as np
from staleness_processing import (
    get_staleness_summary,
    get_stale_securities_details,
)


# --- get_staleness_summary ---
def test_get_staleness_summary(tmp_path):
    # Create a mock Data folder with sec_*.csv files
    folder = tmp_path
    df = pd.DataFrame(
        {"ISIN": ["A", "B"], "2024-01-01": [1, np.nan], "2024-01-02": [np.nan, 2]}
    )
    file_path = folder / "sec_test.csv"
    df.to_csv(file_path, index=False)
    summary = get_staleness_summary(data_folder=str(folder))
    assert "sec_test.csv" in summary
    assert isinstance(summary["sec_test.csv"], dict)


# --- get_stale_securities_details ---
def test_get_stale_securities_details(tmp_path):
    # Create a mock Data folder with sec_*.csv files
    folder = tmp_path
    df = pd.DataFrame(
        {"ISIN": ["A", "B"], "2024-01-01": [1, np.nan], "2024-01-02": [np.nan, 2]}
    )
    file_path = folder / "sec_test.csv"
    df.to_csv(file_path, index=False)
    details, latest_date, total_count = get_stale_securities_details(
        "sec_test.csv", data_folder=str(folder)
    )
    assert isinstance(details, list)
    assert total_count == 2
