# Purpose: Simple unit tests for calculate_generic_comparison_stats minimal behavior.

import pandas as pd
import pytest

def _with_app_context():
    from app import create_app
    app = create_app()
    return app.app_context()


def test_calculate_generic_comparison_stats_minimal():
    df = pd.DataFrame({
        "ISIN": ["X1", "X1", "X2"],
        "Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02"]),
        "Value_Orig": [1.0, 2.0, 5.0],
        "Value_New": [1.1, 2.1, 6.0],
    })
    static = pd.DataFrame({"ISIN": ["X1", "X2"], "Security Name": ["A", "B"]})
    from views.generic_comparison_views import calculate_generic_comparison_stats
    with _with_app_context():
        out = calculate_generic_comparison_stats(df, static, id_col="ISIN")
    assert set(out["ISIN"]) == {"X1", "X2"}
    # Ensure core keys present
    for col in [
        "Level_Correlation",
        "Change_Correlation",
        "Mean_Abs_Diff",
        "Max_Abs_Diff",
        "Same_Date_Range",
    ]:
        assert col in out.columns

