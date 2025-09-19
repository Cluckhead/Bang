# Purpose: Validate melt_wide_data converts wide security data to long format with proper Date parsing.

import pandas as pd
from core.data_utils import melt_wide_data


def test_melt_wide_data_success():
    """Build a tiny wide table (2 ISIN rows, 3 date cols) and verify 6 rows after melt and proper Date dtype."""
    data = {
        "ISIN": ["X1", "X2"],
        "Type": ["Bond", "Bond"],
        "2024-01-01": [1.0, 2.0],
        "2024-01-02": [1.1, 2.1],
        "2024-01-03": [1.2, 2.2],
    }
    df_wide = pd.DataFrame(data)

    melted = melt_wide_data(df_wide, id_vars=["ISIN", "Type"])

    assert melted is not None, "melt_wide_data returned None"
    # Expect 2 * 3 = 6 rows
    assert len(melted) == 6
    # Ensure Date column exists and is datetime
    assert "Date" in melted.columns
    assert pd.api.types.is_datetime64_any_dtype(melted["Date"])
    # Values should align (check one sample)
    assert (
        melted.loc[
            (melted["ISIN"] == "X1") & (melted["Date"] == pd.Timestamp("2024-01-02")),
            "Value",
        ].iloc[0]
        == 1.1
    )
