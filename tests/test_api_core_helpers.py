# Purpose: Simple unit tests for API helper functions that don't hit external systems.

import pandas as pd
from views.api_core import _find_key_columns


def test_find_key_columns_basic(monkeypatch):
    df = pd.DataFrame({
        "Trade Date": ["2024-01-01"],
        "Fund Code": ["F1"],
        "Value": [1.0],
    })

    # Patch current_app logger to a dummy with .info
    class _L:  # noqa: N801
        def info(self, *a, **k):
            pass
        def warning(self, *a, **k):
            pass

    class _CA:  # noqa: N801
        logger = _L()

    import views.api_core as mod
    monkeypatch.setattr(mod, "current_app", _CA())

    date_col, fund_col = _find_key_columns(df, "file.csv")
    assert date_col == "Trade Date"
    assert fund_col == "Fund Code"

