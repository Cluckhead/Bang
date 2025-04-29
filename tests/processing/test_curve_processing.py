# Purpose: Unit tests for curve_processing.py, covering term conversion, curve data loading, latest date extraction, and inconsistency checks.

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
import curve_processing


# --- _term_to_days ---
def test_term_to_days_basic():
    assert curve_processing._term_to_days("7D") == 7
    assert curve_processing._term_to_days("2W") == 14
    assert curve_processing._term_to_days("3M") == 90
    assert curve_processing._term_to_days("1Y") == 365
    assert curve_processing._term_to_days("30") == 30
    assert curve_processing._term_to_days("bad") is None
    assert curve_processing._term_to_days(None) is None
    assert curve_processing._term_to_days("") is None


def test_term_to_days_invalid_cases():
    # Explicitly test a variety of invalid terms
    invalid_terms = ["BAD", "", None, "foo", "123abc", "-1Y", "0M", " ", "1Q", "2024-01-01"]
    for term in invalid_terms:
        assert curve_processing._term_to_days(term) is None


# --- load_curve_data ---
def test_load_curve_data_valid(mocker, tmp_path):
    # Create a mock curves.csv file
    data = pd.DataFrame(
        {
            "Currency": ["USD", "USD", "EUR"],
            "Date": [
                "2024-01-01T00:00:00",
                "2024-01-01T00:00:00",
                "2024-01-01T00:00:00",
            ],
            "Term": ["1D", "1Y", "1M"],
            "Value": [1.0, 2.0, 3.0],
        }
    )
    folder = tmp_path
    file_path = folder / "curves.csv"
    data.to_csv(file_path, index=False)
    df = curve_processing.load_curve_data(str(folder))
    assert not df.empty
    assert set(df.index.names) == {"Currency", "Date", "Term"}
    assert "TermDays" in df.columns
    assert "Value" in df.columns
    # Check term conversion
    assert set(df["TermDays"]) == {1, 30, 365}


def test_load_curve_data_file_not_found(tmp_path):
    # No curves.csv in the folder
    df = curve_processing.load_curve_data(str(tmp_path))
    assert df.empty


# --- get_latest_curve_date ---
def test_get_latest_curve_date():
    idx = pd.MultiIndex.from_tuples(
        [
            ("USD", pd.Timestamp("2024-01-01"), "1D"),
            ("USD", pd.Timestamp("2024-01-02"), "1D"),
            ("EUR", pd.Timestamp("2024-01-01"), "1D"),
        ],
        names=["Currency", "Date", "Term"],
    )
    df = pd.DataFrame({"Value": [1, 2, 3], "TermDays": [1, 1, 1]}, index=idx)
    latest = curve_processing.get_latest_curve_date(df)
    assert latest == pd.Timestamp("2024-01-02")


# --- check_curve_inconsistencies ---
def test_check_curve_inconsistencies_ok():
    # Should return OK for monotonic increasing
    idx = pd.MultiIndex.from_tuples(
        [
            ("USD", pd.Timestamp("2024-01-01"), "1D"),
            ("USD", pd.Timestamp("2024-01-01"), "1M"),
            ("USD", pd.Timestamp("2024-01-01"), "1Y"),
        ],
        names=["Currency", "Date", "Term"],
    )
    df = pd.DataFrame({"Value": [1.0, 1.5, 2.0], "TermDays": [1, 30, 365]}, index=idx)
    summary = curve_processing.check_curve_inconsistencies(df)
    assert "USD" in summary
    assert summary["USD"] == ["OK"]
