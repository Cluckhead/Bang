# Purpose: Validate data_loader._find_columns_for_file correctly detects date, code, benchmark, and value columns.

from data_loader import _find_columns_for_file


def test_find_columns_for_file_basic():
    """Provide a synthetic header list and ensure columns are classified properly."""
    header = [
        "Trade Date",  # Date column (matches DATE_COLUMN_PATTERNS)
        "Code",  # Code column
        "Benchmark",  # Benchmark column
        "Value",  # Fund value
        "Other",  # Another fund value
    ]

    (
        date_col,
        code_col,
        benchmark_present,
        benchmark_col,
        fund_val_cols,
        scope_col,
    ) = _find_columns_for_file(header, "dummy.csv")

    assert date_col == "Trade Date"
    assert code_col == "Code"
    assert benchmark_present is True
    assert benchmark_col == "Benchmark"
    # Fund value columns should be the ones not identified as date/code/benchmark
    assert set(fund_val_cols) == {"Value", "Other"}
    assert scope_col is None 