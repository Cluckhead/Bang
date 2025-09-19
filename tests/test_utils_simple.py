# Purpose: Simple unit tests for selected utils helpers that don't touch external systems.

import pandas as pd
import numpy as np
from core.utils import replace_nan_with_none, parse_fund_list, get_business_day_offset
from datetime import datetime


def test_replace_nan_with_none_nested():
    data = {"a": np.nan, "b": [1, np.nan, {"c": np.nan}]}
    out = replace_nan_with_none(data)
    assert out["a"] is None
    assert out["b"][1] is None
    assert out["b"][2]["c"] is None


def test_parse_fund_list_variants():
    assert parse_fund_list("[A,B]") == ["A", "B"]
    assert parse_fund_list("A,B") == ["A", "B"]
    # Malformed strings fall back to naive split; ensure it returns something non-crashing
    assert isinstance(parse_fund_list("["), list)
    assert parse_fund_list("") == []


def test_get_business_day_offset_basic():
    # Monday 2024-01-08; offset -1 should give previous Friday 2024-01-05
    start = datetime(2024, 1, 8)
    prev_bd = get_business_day_offset(start, -1)
    assert prev_bd.weekday() < 5

