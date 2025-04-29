# Purpose: Unit tests for data_loader.py, covering column finding, empty DataFrame creation, column parsing, value conversion, file processing, and data loading.

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import io
import data_loader


# --- _find_column ---
def test_find_column():
    columns = ["A", "B", "C"]
    assert data_loader._find_column("B", columns, "file.csv", "Test") == "B"
    with pytest.raises(ValueError):
        data_loader._find_column("X", columns, "file.csv", "Test")


# --- _create_empty_dataframe ---
def test_create_empty_dataframe():
    cols = ["A", "B"]
    df = data_loader._create_empty_dataframe(cols, benchmark_col_present=True)
    assert "Benchmark" in df.columns
    assert df.empty


# --- _find_columns_for_file ---
def test_find_columns_for_file():
    columns = ["Date", "Code", "Value1", "Value2", "Benchmark"]
    result = data_loader._find_columns_for_file(columns, "file.csv")
    id_col, code_col, bench_present, bench_col, value_cols = result
    assert id_col == "Date"
    assert code_col == "Code"
    assert bench_present is True
    assert bench_col == "Benchmark"
    assert "Value1" in value_cols and "Value2" in value_cols


# --- _parse_date_column ---
def test_parse_date_column():
    df = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02"]})
    result = data_loader._parse_date_column(df, "Date", "file.csv")
    assert pd.api.types.is_datetime64_any_dtype(result)


# --- _convert_value_columns ---
def test_convert_value_columns():
    df = pd.DataFrame({"A": ["1", "2", "bad"]})
    cols = data_loader._convert_value_columns(df, ["A"], benchmark_col_present=False)
    assert pd.api.types.is_float_dtype(df["A"])
    assert np.isnan(df["A"].iloc[2])


# --- _process_single_file ---
def test_process_single_file_valid(tmp_path):
    # Create a valid CSV file with expected columns
    df = pd.DataFrame(
        {
            "Code": ["A", "B"],
            "Value": [1, 2],
            "Date": ["2024-01-01", "2024-01-02"],
            "Benchmark": [10, 20],
        }
    )
    file_path = tmp_path / "test.csv"
    df.to_csv(file_path, index=False)
    result = data_loader._process_single_file(str(file_path), "test.csv")
    assert result is not None
    df_result, value_cols, bench_col = result
    assert not df_result.empty
    assert "Value" in df_result.columns
    assert "Code" in df_result.index.names
    assert "Date" in df_result.index.names


# --- load_and_process_data ---
def test_load_and_process_data_valid(tmp_path):
    # Create a valid primary CSV file with expected columns
    df = pd.DataFrame(
        {
            "Code": ["A", "B"],
            "Value": [1, 2],
            "Date": ["2024-01-01", "2024-01-02"],
            "Benchmark": [10, 20],
        }
    )
    file_path = tmp_path / "primary.csv"
    df.to_csv(file_path, index=False)
    result = data_loader.load_and_process_data(
        "primary.csv", data_folder_path=str(tmp_path)
    )
    assert isinstance(result, tuple)
    assert isinstance(result[0], pd.DataFrame)
    assert not result[0].empty
