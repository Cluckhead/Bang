# Purpose: Unit tests for weight_processing.py, covering weight file processing, header replacement, and edge cases.

import pytest
import pandas as pd
import os
import tempfile
import weight_processing


# Dummy logger to silence output during tests
def dummy_logger():
    class DummyLogger:
        def debug(self, msg):
            pass

        def info(self, msg):
            pass

        def warning(self, msg):
            pass

        def error(self, msg, exc_info=None):
            pass

    return DummyLogger()


# Helper to create a temp CSV file and return its path
def create_temp_csv(tmp_path, filename, df):
    file_path = tmp_path / filename
    df.to_csv(file_path, index=False)
    return str(file_path)


# Helper to read a CSV as DataFrame
def read_csv(path):
    return pd.read_csv(path)


@pytest.mark.parametrize("filetype", ["w_Funds.csv", "w_Bench.csv"])
def test_process_weight_file_funds_and_bench(tmp_path, filetype):
    # Create Dates.csv
    dates = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02"]})
    dates_path = create_temp_csv(tmp_path, "Dates.csv", dates)
    # Create input file
    df = pd.DataFrame({"ID": ["A", "B"], "Col1": [1, 2], "Col2": [3, 4]})
    input_path = create_temp_csv(tmp_path, filetype, df)
    output_path = tmp_path / ("out_" + filetype)
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(dates_path)
    )
    out_df = read_csv(output_path)
    assert out_df.columns[1] == "2024-01-01"
    assert out_df.columns[2] == "2024-01-02"
    assert out_df.shape == (2, 3)


def test_process_weight_file_w_secs(tmp_path):
    # Create Dates.csv
    dates = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02", "2024-01-03"]})
    dates_path = create_temp_csv(tmp_path, "Dates.csv", dates)
    # Create input file with 2 metadata columns
    df = pd.DataFrame(
        {
            "ID": ["A", "B"],
            "Meta": ["X", "Y"],
            "Col1": [1, 2],
            "Col2": [3, 4],
            "Col3": [5, 6],
        }
    )
    input_path = create_temp_csv(tmp_path, "w_secs.csv", df)
    output_path = tmp_path / "out_w_secs.csv"
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(dates_path)
    )
    out_df = read_csv(output_path)
    # Metadata columns should remain, data columns replaced by dates
    assert out_df.columns[2] == "2024-01-01"
    assert out_df.columns[4] == "2024-01-03"
    assert out_df.shape == (2, 5)


def test_process_weight_file_more_dates_than_columns(tmp_path):
    # More dates than data columns
    dates = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02", "2024-01-03"]})
    dates_path = create_temp_csv(tmp_path, "Dates.csv", dates)
    df = pd.DataFrame({"ID": ["A"], "Col1": [1], "Col2": [2]})
    input_path = create_temp_csv(tmp_path, "w_Funds.csv", df)
    output_path = tmp_path / "out_w_Funds.csv"
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(dates_path)
    )
    out_df = read_csv(output_path)
    # Only as many dates as columns should be used
    assert len(out_df.columns) == 3
    assert out_df.columns[2] == "2024-01-02"


def test_process_weight_file_more_columns_than_dates(tmp_path):
    # More data columns than dates
    dates = pd.DataFrame({"Date": ["2024-01-01"]})
    dates_path = create_temp_csv(tmp_path, "Dates.csv", dates)
    df = pd.DataFrame({"ID": ["A"], "Col1": [1], "Col2": [2]})
    input_path = create_temp_csv(tmp_path, "w_Funds.csv", df)
    output_path = tmp_path / "out_w_Funds.csv"
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(dates_path)
    )
    out_df = read_csv(output_path)
    # Only as many columns as dates should be used
    assert len(out_df.columns) == 2
    assert out_df.columns[1] == "2024-01-01"


def test_process_weight_file_empty_file(tmp_path):
    # Empty input file
    dates = pd.DataFrame({"Date": ["2024-01-01"]})
    dates_path = create_temp_csv(tmp_path, "Dates.csv", dates)
    input_path = tmp_path / "w_Funds.csv"
    pd.DataFrame().to_csv(input_path, index=False)
    output_path = tmp_path / "out_w_Funds.csv"
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(dates_path)
    )
    # Output file should not exist or be empty
    assert not output_path.exists() or read_csv(output_path).empty


def test_process_weight_file_missing_dates_csv(tmp_path):
    # Dates.csv missing
    df = pd.DataFrame({"ID": ["A"], "Col1": [1]})
    input_path = create_temp_csv(tmp_path, "w_Funds.csv", df)
    output_path = tmp_path / "out_w_Funds.csv"
    # Should not raise, but output file should not exist
    weight_processing.process_weight_file(
        str(input_path), str(output_path), str(tmp_path / "Dates.csv")
    )
    assert not output_path.exists()
