# Add project root to sys.path for module imports
import os, sys
import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def write_csv(path: str, rows: list) -> None:
    """Utility to quickly materialize small CSVs from lists of dicts."""
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


@pytest.fixture
def mini_dataset(tmp_path):
    """Creates minimal CSVs under tmp_path for testing."""
    
    # Create reference.csv
    reference_data = [
        {
            "ISIN": "US0000001",
            "Security Name": "Bond A",
            "Position Currency": "EUR",
            "Currency": "USD",
            "Coupon Rate": 5.0,
            "Call Indicator": 1,
            "Funds": "[F1]",
            "Type": "Corp",
            "Is Distressed": False
        },
        {
            "ISIN": "US0000002",
            "Security Name": "Bond B",
            "Position Currency": "GBP",
            "Currency": "USD", 
            "Coupon Rate": 3.0,
            "Call Indicator": 0,
            "Funds": "[F2]",
            "Type": "Gov",
            "Is Distressed": True
        }
    ]
    write_csv(str(tmp_path / "reference.csv"), reference_data)
    
    # Create schedule.csv
    schedule_data = [
        {
            "ISIN": "US0000001",
            "Coupon Frequency": 2,
            "Day Basis": "ACT/ACT",
            "Issue Date": "01/01/2020",
            "First Coupon": "01/07/2020",
            "Maturity Date": "01/01/2030",
            "Accrued Interest": 1.23
        },
        {
            "ISIN": "US0000002",
            "Coupon Frequency": 2,
            "Day Basis": "30/360",
            "Issue Date": "01/01/2021",
            "First Coupon": "01/07/2021", 
            "Maturity Date": "01/01/2031",
            "Accrued Interest": 0.45
        }
    ]
    write_csv(str(tmp_path / "schedule.csv"), schedule_data)
    
    # Create sec_Price.csv
    price_data = [
        {
            "ISIN": "US0000001",
            "Security Name": "Bond A",
            "Type": "Corp",
            "Funds": "[F1]",
            "Callable": "Y",
            "Currency": "USD",
            "2025-01-01": 100.1,
            "2025-01-02": 101.2
        },
        {
            "ISIN": "US0000002-1",
            "Security Name": "Bond B (tap)",
            "Type": "Gov",
            "Funds": "[F2]",
            "Callable": "N",
            "Currency": "USD",
            "2025-01-01": 99.8,
            "2025-01-02": 99.5
        }
    ]
    write_csv(str(tmp_path / "sec_Price.csv"), price_data)
    
    # Create sec_accrued.csv
    accrued_data = [
        {
            "ISIN": "US0000001",
            "2025-01-01": 1.11,
            "2025-01-02": 1.22
        },
        {
            "ISIN": "US0000002",
            "2025-01-01": 0.33,
            "2025-01-02": None
        }
    ]
    write_csv(str(tmp_path / "sec_accrued.csv"), accrued_data)
    
    # Create curves.csv
    curves_data = [
        {"Currency Code": "USD", "Date": "2025-01-02", "Term": "1M", "Daily Value": 5.0},
        {"Currency Code": "USD", "Date": "2025-01-02", "Term": "1Y", "Daily Value": 5.5},
        {"Currency Code": "USD", "Date": "2025-01-02", "Term": "5Y", "Daily Value": 6.0},
        {"Currency Code": "EUR", "Date": "2025-01-02", "Term": "1Y", "Daily Value": 3.0}
    ]
    write_csv(str(tmp_path / "curves.csv"), curves_data)
    
    # Create w_secs.csv
    w_secs_data = [
        {"ISIN": "US0000001", "2024-01-01": 0, "2025-01-02": 0.15},
        {"ISIN": "US0000002", "2024-01-01": 0.10, "2025-01-02": 0}
    ]
    write_csv(str(tmp_path / "w_secs.csv"), w_secs_data)
    
    # Create FundGroups.csv
    fund_groups_data = [{"Group": "Core", "Funds": "[F1,F2]"}]
    write_csv(str(tmp_path / "FundGroups.csv"), fund_groups_data)
    
    # Create holidays.csv
    holidays_data = [{"date": "2025-01-01", "currency": "GBP"}]
    write_csv(str(tmp_path / "holidays.csv"), holidays_data)
    
    return str(tmp_path)


@pytest.fixture
def app_config(monkeypatch, tmp_path):
    """Monkeypatch core.settings_loader.load_settings to return test config."""
    def mock_load_settings():
        return {
            'app_config': {
                'data_folder': str(tmp_path)
            }
        }
    
    monkeypatch.setattr("core.settings_loader.load_settings", mock_load_settings)
    return str(tmp_path)


@pytest.fixture
def freeze_time():
    """Use freezegun.freeze_time for tests that rely on 'today/last business day'."""
    try:
        from freezegun import freeze_time
        return freeze_time("2025-01-03 10:00:00")
    except ImportError:
        # If freezegun not available, return a no-op context manager
        import contextlib
        return contextlib.nullcontext()


@pytest.fixture
def client():
    """Flask test client fixture."""
    try:
        import app
        test_app = app.create_app()
        test_app.config['TESTING'] = True
        with test_app.test_client() as client:
            yield client
    except ImportError:
        pytest.skip("Flask not available for client fixture")
