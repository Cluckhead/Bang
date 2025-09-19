# Purpose: Minimal test for file delivery status helper via API core get_data_file_statuses.

import os
import pandas as pd
from views.api_core import get_data_file_statuses


class _DummyLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass


class _CA:
    logger = _DummyLogger()


def test_get_data_file_statuses_handles_missing_map(monkeypatch, tmp_path):
    import views.api_core as mod
    monkeypatch.setattr(mod, "current_app", _CA())
    out = get_data_file_statuses(str(tmp_path))
    assert isinstance(out, list)


def test_get_data_file_statuses_basic(monkeypatch, tmp_path):
    import views.api_core as mod
    monkeypatch.setattr(mod, "current_app", _CA())

    # Write a simple QueryMap.csv
    df = pd.DataFrame({"FileName": ["ts_X.csv"]})
    df.to_csv(tmp_path / "QueryMap.csv", index=False)

    # Write the referenced file with a Date column
    pd.DataFrame({"Date": ["2024-01-01", "2024-01-02"], "Code": ["F1", "F1"], "Value": [1, 2]}).to_csv(
        tmp_path / "ts_X.csv", index=False
    )

    out = get_data_file_statuses(str(tmp_path))
    assert len(out) == 1
    assert out[0]["filename"] == "ts_X.csv"
    assert out[0]["exists"] is True

