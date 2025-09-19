# Purpose: Additional simple tests for data_utils helpers.

import pandas as pd
import numpy as np
import pytest
from core.data_utils import parse_dates_robustly, melt_wide_data, identify_columns


def test_parse_dates_robustly_empty_series():
    s = pd.Series([], dtype=object)
    out = parse_dates_robustly(s)
    assert out.dtype.kind == "M"  # datetime-like
    assert len(out) == 0


def test_melt_wide_data_no_dates_returns_none():
    df = pd.DataFrame({"ISIN": ["X1"], "Foo": [1.0]})
    assert melt_wide_data(df, id_vars=["ISIN"]) is None


def test_identify_columns_missing_required_raises():
    cols = ["Foo", "Bar"]
    patterns = {"date": [r"Date"], "id": [r"ISIN"]}
    with pytest.raises(ValueError):
        identify_columns(cols, patterns, required=["date"]) 

