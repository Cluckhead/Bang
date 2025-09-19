# Purpose: Smoke test for preprocessing.read_and_sort_dates behavior with missing file.

from data_processing.preprocessing import read_and_sort_dates


def test_read_and_sort_dates_missing_returns_none(tmp_path):
    out = read_and_sort_dates(str(tmp_path / "Dates.csv"))
    assert out is None

