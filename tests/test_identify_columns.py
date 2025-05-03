"""Tests for `data_utils.identify_columns`.

Validates correct column detection and behaviour when required columns are missing.
"""

import logging

import pytest

from data_utils import identify_columns


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_patterns():
    """Reusable regex pattern dictionary matching common column names."""
    return {
        "date": [r"Date"],
        "code": [r"ISIN", r"Code"],
        "benchmark": [r"Benchmark"],
    }


# -----------------------------------------------------------------------------
# Happy-path test
# -----------------------------------------------------------------------------


def test_identify_columns_success(sample_patterns):
    """Given a header list containing Trade Date, ISIN, Benchmark, ensure correct mapping is returned."""
    header = ["Trade Date", "ISIN", "Benchmark", "Extra"]
    required = ["date", "code"]

    result = identify_columns(header, sample_patterns, required)

    assert result["date"] == "Trade Date"
    assert result["code"] == "ISIN"
    assert result["benchmark"] == "Benchmark"


def test_identify_columns_missing_required(sample_patterns, caplog):
    """If a required category is missing, identify_columns should raise ValueError and emit an error log."""
    header = ["ISIN", "Benchmark", "Other"]  # 'Date' column deliberately omitted
    required = ["date", "code"]

    with caplog.at_level(logging.ERROR):
        # Expect a ValueError to be raised because the 'date' column is mandatory
        with pytest.raises(ValueError):
            identify_columns(header, sample_patterns, required)

    # Ensure an error was logged for the missing required column
    logged_errors = [rec.getMessage() for rec in caplog.records]
    assert any("Required category 'date' not found" in msg for msg in logged_errors)
