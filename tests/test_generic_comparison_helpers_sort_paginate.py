# Purpose: Simple unit tests for generic comparison helper sorting and pagination.

import pandas as pd
from views.generic_comparison_helpers import _apply_summary_sorting, _paginate_summary_data


def test_apply_summary_sorting_numeric_and_fallback():
    df = pd.DataFrame({"ISIN": ["X2", "X1"], "Level_Correlation": [0.9, 0.8]})
    sorted_df, sort_by, order = _apply_summary_sorting(df, "Level_Correlation", "desc", "ISIN")
    assert list(sorted_df["ISIN"]) == ["X2", "X1"]

    # Non-existent column → fallback to ID sort asc
    sorted_df2, sort_by2, order2 = _apply_summary_sorting(df, "Missing", "desc", "ISIN")
    assert list(sorted_df2["ISIN"]) == ["X1", "X2"]


def test_paginate_summary_data_basic():
    df = pd.DataFrame({"ISIN": [f"X{i}" for i in range(1, 11)]})
    page_df, ctx = _paginate_summary_data(df, page=2, per_page=3)
    assert len(page_df) == 3
    assert ctx["page"] == 2
    assert ctx["total_pages"] >= 4

