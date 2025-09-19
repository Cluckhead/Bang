# Purpose: Minimal smoke test for staleness_processing on a tiny file.

import pandas as pd
from analytics import staleness_processing as sp


def test_staleness_processing_smoke(tmp_path):
    df = pd.DataFrame({
        "ISIN": ["X1"],
        "Security Name": ["A"],
        # Two identical values to qualify as stale sequence in some configs
        "2024-01-01": [100],
        "2024-01-02": [100],
    })
    f = tmp_path / "sec_Spread.csv"
    df.to_csv(f, index=False)

    details, latest_date, total = sp.get_stale_securities_details("sec_Spread.csv", str(tmp_path), threshold_days=1)
    assert isinstance(details, list)
    assert total >= 1

