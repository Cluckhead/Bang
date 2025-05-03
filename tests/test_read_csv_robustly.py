# Purpose: Test cases for the read_csv_robustly utility function.
# This test file verifies successful CSV reading and graceful handling of missing files.

import pandas as pd
import pytest

from data_utils import read_csv_robustly


def test_read_csv_robustly_happy_path(tmp_path):
    """Ensure read_csv_robustly correctly reads a valid CSV and returns a DataFrame."""
    # Create a temporary CSV file
    csv_content = """col1,col2,col3
1,2,3
4,5,6
"""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(csv_content)

    # Read the CSV using the utility function
    df = read_csv_robustly(str(csv_file))

    # Assertions
    assert df is not None, "Expected a DataFrame, got None instead."
    assert df.shape == (2, 3), "DataFrame shape mismatch for happy-path CSV read."


def test_read_csv_robustly_file_not_found(tmp_path):
    """Ensure read_csv_robustly returns None and does not raise when the file is missing."""
    # Provide a path to a non-existent file within the temp directory
    missing_file = tmp_path / "does_not_exist.csv"

    # Attempt to read the non-existent file
    result = read_csv_robustly(str(missing_file))

    # Assertions
    assert result is None, "Expected None for missing file path."
