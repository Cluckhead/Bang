# Purpose: Validate data_validation.validate_data for ts_, sec_, and w_ file scenarios.

import pandas as pd
from data_processing.data_validation import validate_data


# ------------------ Time-Series ------------------


def test_validate_data_ts_good():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Code": ["F1", "F1"],
            "Value": [1.0, 1.1],
        }
    )
    valid, errors = validate_data(df, "ts_metric.csv")
    assert valid
    assert errors == []


def test_validate_data_ts_missing_code():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01"]),
            "Value": [1.0],
        }
    )
    valid, errors = validate_data(df, "ts_metric.csv")
    assert not valid
    assert any("Missing required columns" in e for e in errors)


# ------------------ Security-Level ------------------


def test_validate_data_sec_missing_isin():
    df = pd.DataFrame({"2024-01-01": [1.0]})
    valid, errors = validate_data(df, "sec_Data.csv")
    assert not valid
    assert any("No ID column" in e for e in errors)
