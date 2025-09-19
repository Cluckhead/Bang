# Purpose: Unit tests for base-ISIN fallback logic in load_filter_and_extract.
# Verifies that when ISINs are suffixed in some files and not others, the loader
# matches by base ISIN and selects the variant with the most data.

from __future__ import annotations

from typing import Set, Dict, Tuple
import os
import types
import pandas as pd
import numpy as np
import pytest

# Target under test
from views.security_helpers import load_filter_and_extract
import views.security_helpers as sh
from core import config


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
    # Replace current_app used inside module with a dummy carrying a logger
    monkeypatch.setattr(sh, "current_app", _DummyApp())


def _make_df_long(records: list[tuple[str, str, float | None]]) -> pd.DataFrame:
    """Helper to build a long-format DataFrame with MultiIndex (Date, ISIN)."""
    df = pd.DataFrame(records, columns=[config.DATE_COL, config.ISIN_COL, config.VALUE_COL])
    df[config.DATE_COL] = pd.to_datetime(df[config.DATE_COL])
    df = df.set_index([config.DATE_COL, config.ISIN_COL])
    return df


def test_base_isin_fallback_when_only_base_exists(monkeypatch, tmp_path):
    # Create an empty file to satisfy os.path.exists(filepath)
    data_folder = tmp_path
    filename = "sec_Spread.csv"
    (data_folder / filename).write_text("")

    # Build df_long with only base ISIN present
    df_long = _make_df_long([
        ("2024-01-01", "XS000", 10.0),
        ("2024-01-02", "XS000", 11.0),
    ])

    # Stub the CSV processor used by loader
    monkeypatch.setattr(sh, "load_and_process_security_data", lambda f, p: (df_long, []))

    series, dates, static = load_filter_and_extract(str(data_folder), filename, "XS000-1", id_column_name=config.ISIN_COL)

    assert series is not None
    assert len(series) == 2
    # Ensure the dates matched the base ISIN rows
    assert pd.Timestamp("2024-01-01") in dates and pd.Timestamp("2024-01-02") in dates


def test_pick_variant_with_most_data(monkeypatch, tmp_path):
    data_folder = tmp_path
    filename = "sec_Spread.csv"
    (data_folder / filename).write_text("")

    # Construct base and two variants with different non-null counts
    # XS111 has 1 non-null, XS111-1 has 2, XS111-2 has 1
    df_long = _make_df_long([
        ("2024-01-01", "XS111", 10.0),
        ("2024-01-02", "XS111", np.nan),
        ("2024-01-01", "XS111-1", 12.0),
        ("2024-01-02", "XS111-1", 13.0),
        ("2024-01-01", "XS111-2", 9.0),
        ("2024-01-02", "XS111-2", np.nan),
    ])

    monkeypatch.setattr(sh, "load_and_process_security_data", lambda f, p: (df_long, []))

    # Ask for base; ensure XS111-1 (most data) is selected
    series, dates, _ = load_filter_and_extract(str(data_folder), filename, "XS111", id_column_name=config.ISIN_COL)

    assert series is not None
    # The selected series should have both dates non-null
    assert series.notna().sum() == 2


def test_exact_match_preferred_over_base(monkeypatch, tmp_path):
    data_folder = tmp_path
    filename = "sec_Spread.csv"
    (data_folder / filename).write_text("")

    # Exact variant requested has fewer points, but should be chosen over base fallback
    df_long = _make_df_long([
        ("2024-01-01", "XS222", 10.0),
        ("2024-01-02", "XS222", 11.0),
        ("2024-01-01", "XS222-1", 7.0),
        ("2024-01-02", "XS222-1", np.nan),
    ])

    monkeypatch.setattr(sh, "load_and_process_security_data", lambda f, p: (df_long, []))

    # Request exact variant
    series, dates, _ = load_filter_and_extract(str(data_folder), filename, "XS222-1", id_column_name=config.ISIN_COL)

    assert series is not None
    # Should reflect the exact variant's one non-null point
    assert series.notna().sum() == 1


