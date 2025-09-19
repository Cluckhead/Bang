# Purpose: Minimal tests for security_processing calculate_security_latest_metrics.

import pandas as pd
import numpy as np
from analytics.security_processing import calculate_security_latest_metrics


def _make_long_df():
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "XS1"),
            (pd.Timestamp("2024-01-02"), "XS1"),
            (pd.Timestamp("2024-01-01"), "XS2"),
        ],
        names=["Date", "ISIN"],
    )
    df = pd.DataFrame({
        "Value": [10.0, 11.0, np.nan],
        "Security Name": ["A", "A", "B"],
        "Currency": ["USD", "USD", "USD"],
    }, index=idx)
    return df


def test_calculate_metrics_happy_path():
    df = _make_long_df()
    out = calculate_security_latest_metrics(df, static_cols=["Security Name", "Currency"])
    # Expect index by ISIN
    assert "XS1" in out.index
    # Latest Value for XS1 is 11.0
    assert out.loc["XS1", "Latest Value"] == 11.0
    # Static columns preserved
    assert out.loc["XS1", "Security Name"] == "A"


def test_calculate_metrics_empty_df():
    empty = pd.DataFrame()
    out = calculate_security_latest_metrics(empty, static_cols=["Security Name"]) 
    assert out.empty

