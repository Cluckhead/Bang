# Purpose: Simple test for security_helpers.load_filter_and_extract behavior when no match.

import os
import pandas as pd
import views.security_helpers as sh
import pytest


class _DummyLogger:
    def info(self, *args, **kwargs):
        pass
    def warning(self, *args, **kwargs):
        pass
    def error(self, *args, **kwargs):
        pass


class _DummyApp:
    logger = _DummyLogger()


@pytest.fixture(autouse=True)
def stub_current_app(monkeypatch):
    monkeypatch.setattr(sh, "current_app", _DummyApp())


def test_no_match_returns_none(monkeypatch, tmp_path):
    # Create empty file for existence check
    filename = "sec_Spread.csv"
    (tmp_path / filename).write_text("")

    # Stub processor to return empty df
    monkeypatch.setattr(sh, "load_and_process_security_data", lambda f, p: (pd.DataFrame(), []))

    series, dates, static = sh.load_filter_and_extract(str(tmp_path), filename, "NOPE", id_column_name="ISIN")
    assert series is None
    assert isinstance(dates, set) and len(dates) == 0

