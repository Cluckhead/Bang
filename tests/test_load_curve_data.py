# Purpose: Test curve_processing.load_curve_data and check_curve_inconsistencies for correct preprocessing and anomaly detection.

import pandas as pd
from curve_processing import load_curve_data, check_curve_inconsistencies, _term_to_days


def _write_sample_curves_csv(tmp_path):
    """Helper to create a sample curves.csv file with one malformed row."""
    csv_content = (
        "Date,Currency,Term,Value\n"
        "2024-01-01T00:00:00,USD,7D,1.0\n"
        "2024-01-01T00:00:00,EUR,7D,1.1\n"
        "2024-01-02T00:00:00,USD,7D,1.2\n"
        "2024-01-02T00:00:00,EUR,7D,bad\n"  # Malformed value (non-numeric)
    )
    curves_file = tmp_path / "curves.csv"
    curves_file.write_text(csv_content)
    return curves_file


def test_load_curve_data_structure(tmp_path):
    """Ensure load_curve_data drops malformed rows and sets correct MultiIndex and TermDays column."""
    _write_sample_curves_csv(tmp_path)

    df = load_curve_data(str(tmp_path))

    # Expect 3 valid rows (one dropped due to non-numeric Value)
    assert df.shape[0] == 3
    # MultiIndex names must be as specified
    assert list(df.index.names) == ["Currency", "Date", "Term"]
    # TermDays column should exist and be correct (all 7)
    assert "TermDays" in df.columns
    assert df["TermDays"].unique().tolist() == [7]


def test_check_curve_inconsistencies_detects_jump(monkeypatch):
    """Create a small DataFrame with a clear jump between terms and ensure the summary flags it."""

    import curve_processing as cp

    # Temporarily lower the STD multiplier to make it easier to flag our crafted anomaly
    monkeypatch.setattr(cp, "CURVE_ANOMALY_STD_MULTIPLIER", 0)

    # Patch builtins.sorted within curve_processing to return a pandas Index so .get_loc works
    import builtins as _bi

    original_sorted = _bi.sorted

    def _sorted_index(iterable, *args, **kwargs):
        return pd.Index(original_sorted(iterable, *args, **kwargs))

    monkeypatch.setattr(_bi, "sorted", _sorted_index)

    prev_date = pd.Timestamp("2024-01-01")
    latest_date = pd.Timestamp("2024-01-02")

    data = {
        "Currency": ["USD", "USD", "USD", "USD", "USD", "USD"],
        "Date": [
            prev_date,
            prev_date,
            prev_date,
            latest_date,
            latest_date,
            latest_date,
        ],
        "Term": ["7D", "1M", "2M", "7D", "1M", "2M"],
        "TermDays": [
            _term_to_days("7D"),
            _term_to_days("1M"),
            _term_to_days("2M"),
            _term_to_days("7D"),
            _term_to_days("1M"),
            _term_to_days("2M"),
        ],
        # Introduce a sharp jump for the 2M term on the latest day
        "Value": [1.0, 1.0, 1.0, 1.0, 1.0, 3.0],
    }

    df = pd.DataFrame(data)
    df.set_index(["Currency", "Date", "Term"], inplace=True)

    summary = check_curve_inconsistencies(df)

    assert "USD" in summary, "Currency key missing in inconsistency summary."
    # Should contain message about anomalous change profile
    assert any(
        "Anomalous change profile" in msg for msg in summary["USD"]
    ), "Expected anomalous change profile message not found." 