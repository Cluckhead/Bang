# Purpose: Unit tests for io_lock module ensuring idempotent installation and basic lock I/O works.

import pandas as pd
from core.io_lock import install_pandas_file_locks, to_csv_locked, append_rows_locked


def test_install_pandas_file_locks_idempotent():
    # Calling install twice should not raise
    install_pandas_file_locks()
    install_pandas_file_locks()


def test_locked_write_roundtrip(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    csv_path = tmp_path / "sample.csv"
    # Write with lock (no index to avoid Unnamed: 0)
    to_csv_locked(df, str(csv_path), index=False)
    # Read normally
    df2 = pd.read_csv(str(csv_path))
    assert list(df2.columns) == ["a", "b"]
    assert df2.shape == (2, 2)


def test_locked_append_rows(tmp_path):
    csv_path = tmp_path / "append.csv"
    header = ["x", "y"]
    rows = [[1, 2], [3, 4]]
    append_rows_locked(str(csv_path), rows, header=header)
    out = pd.read_csv(str(csv_path))
    assert out.shape == (2, 2)
    assert list(out.columns) == header

