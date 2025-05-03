# Purpose: End-to-end test for data_loader.load_and_process_data on a small time-series CSV.

import pandas as pd
from data_loader import load_and_process_data


def _write_ts_csv(tmp_dir):
    csv_content = (
        "Date,Code,Value\n" "2024-01-01,F1,1.0\n" "2024-01-02,F1,1.2\n"
    )
    f = tmp_dir / "ts_test.csv"
    f.write_text(csv_content)
    return f.name  # return filename only


def test_load_and_process_data_happy_path(tmp_path):
    filename = _write_ts_csv(tmp_path)

    df, val_cols, bm_col, *_ = load_and_process_data(
        primary_filename=filename, data_folder_path=str(tmp_path)
    )

    # DataFrame should not be None or empty
    assert df is not None and not df.empty
    # Index names should be Date, Code
    assert list(df.index.names) == ["Date", "Code"]
    # One value column present and numeric
    assert val_cols == ["Value"]
    assert pd.api.types.is_numeric_dtype(df["Value"])
    assert bm_col is None 