# Purpose: Unit tests for security_views.py, testing the security summary (/security/summary) and detail (/security/details/...) routes, covering data loading, metric calculation, filtering, pagination, exclusion handling, and error scenarios.
# Purpose: Unit tests for security_views.py, covering the /security/summary and /security/details/<metric_name>/<security_id> routes, including edge and error cases.

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
import pandas as pd
import os
from pathlib import Path  # Import Path

# Remove unused fixture
# @pytest.fixture
# def mock_security_data(tmp_path):
#     pass


# Update helper to use pathlib
def create_dummy_exclusions(data_folder_path: Path) -> Path:
    """Helper to create a dummy exclusions file using pathlib."""
    exclusions_path = (
        data_folder_path / "Exclusions.csv"
    )  # Match expected filename case?
    # Ensure parent directory exists
    data_folder_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "SecurityId": ["EXCLUDED01"],
            "Reason": ["Test Exclusion"],
            "ExcludedUntil": ["2099-12-31"],
        }
    ).to_csv(exclusions_path, index=False)
    return exclusions_path


# Update helper to use pathlib
def create_dummy_security_file(
    data_folder_path: Path, filename: str = "sec_Spread.csv"
) -> Path:
    """Helper to create a dummy security data file using pathlib."""
    sec_path = data_folder_path / filename
    # Ensure parent directory exists
    data_folder_path.mkdir(parents=True, exist_ok=True)
    # Create a simple file with ISIN, Date, Value, and a static column
    df = pd.DataFrame(
        {
            "ISIN": [
                "SEC001",
                "SEC002",
                "EXCLUDED01",
                "SEC001",
                "SEC002",
                "EXCLUDED01",
            ],
            "Date": pd.to_datetime(["2024-01-01"] * 3 + ["2024-01-02"] * 3),
            "Value": [10.0, 20.0, 99.0, 10.5, 20.5, 99.5],
            "StaticCol": ["A", "B", "Z", "A", "B", "Z"],
        }
    )
    # Pivot to wide format expected by loader
    df_pivoted = df.pivot_table(
        index=["ISIN", "StaticCol"], columns="Date", values="Value"
    ).reset_index()
    df_pivoted.columns = ["ISIN", "StaticCol"] + [
        d.strftime("%Y-%m-%d") for d in df_pivoted.columns[2:]
    ]
    df_pivoted.to_csv(sec_path, index=False)
    return sec_path


# Add fixture to manage data folder per test using tmp_path
@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    monkeypatch.setitem(client.application.config, "DATA_FOLDER", str(data_folder))
    # Define exclusions file path relative to tmp_path
    exclusions_file = data_folder / "Exclusions.csv"
    monkeypatch.setitem(
        client.application.config, "EXCLUSIONS_FILE", str(exclusions_file)
    )

    # Patch os.path.exists to check actual existence within tmp_path
    original_exists = os.path.exists

    def mock_exists(path):
        try:
            path_obj = Path(path).resolve()
            data_folder_resolved = data_folder.resolve()
            if path_obj.is_relative_to(data_folder_resolved):
                return path_obj.exists()
        except (TypeError, ValueError):
            pass
        except Exception:
            pass
        return original_exists(path)

    # We also need to make sure load_exclusions uses the correct path
    # Patching the config should be enough if load_exclusions reads from config
    # If load_exclusions hardcodes a path or uses a different mechanism, it might need mocking.
    # Assuming load_exclusions uses app.config['EXCLUSIONS_FILE'] for now.
    with patch("views.security_views.os.path.exists", side_effect=mock_exists), patch(
        "views.exclusion_views.os.path.exists", side_effect=mock_exists
    ):  # Also patch for exclusion view if needed
        yield data_folder


# Removed @patch('views.security_views.os.path.exists') and @patch('views.exclusion_views.load_exclusions')
@patch("views.security_views.load_and_process_security_data")
@patch("views.security_views.calculate_security_latest_metrics")
def test_securities_page_success(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    data_folder = setup_data_folder
    create_dummy_exclusions(data_folder)  # Create the file for load_exclusions to find
    sec_file_path = create_dummy_security_file(data_folder, "sec_Spread.csv")

    # Mock load_and_process_security_data
    # ... (mock setup for df_long remains the same, include EXCLUDED01 initially) ...
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "SEC001"),
            (pd.Timestamp("2024-01-01"), "SEC002"),
            (pd.Timestamp("2024-01-01"), "EXCLUDED01"),
            (pd.Timestamp("2024-01-02"), "SEC001"),
            (pd.Timestamp("2024-01-02"), "SEC002"),
            (pd.Timestamp("2024-01-02"), "EXCLUDED01"),
        ],
        names=["Date", "ISIN"],
    )
    df_long = pd.DataFrame({"Value": [10.0, 20.0, 99.0, 10.5, 20.5, 99.5]}, index=idx)
    static_cols = ["StaticCol"]
    mock_load_data.return_value = (df_long, static_cols)

    # Mock calculate_security_latest_metrics (should NOT include EXCLUDED01 if filtering happens before calc)
    # Assuming filtering happens *after* calculation in the view based on original test structure
    metrics_df = pd.DataFrame(
        {
            "ISIN": ["SEC001", "SEC002", "EXCLUDED01"],
            "StaticCol": ["A", "B", "Z"],
            "Latest Value": [10.5, 20.5, 99.5],
            "Change": [0.5, 0.5, 0.5],
            "Change Z-Score": [1.0, 1.0, 0.0],
            "Mean": [10.25, 20.25, 99.25],
            "Max": [10.5, 20.5, 99.5],
            "Min": [10.0, 20.0, 99.0],
            "_abs_z_score_": [1.0, 1.0, 0.0],  # Add internal sorting column
        }
    )
    mock_calc_metrics.return_value = metrics_df

    response = client.get(
        url_for("security_bp.securities_page", security_type="Spread")
    )  # Use blueprint name
    assert response.status_code == 200
    assert b"Spread Securities" in response.data
    assert b"SEC001" in response.data
    assert b"SEC002" in response.data
    assert b"EXCLUDED01" not in response.data  # Verify exclusion worked in the view


@patch("views.security_views.load_and_process_security_data")
@patch("views.security_views.calculate_security_latest_metrics")
def test_securities_page_no_file(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    # setup_data_folder runs, but we don't create the sec_Spread.csv file
    data_folder = setup_data_folder
    # create_dummy_exclusions(data_folder) # Exclusions file doesn't strictly need to exist for this test

    # The patched os.path.exists in setup_data_folder will return False for the sec file

    response = client.get(
        url_for("security_bp.securities_page", security_type="Spread")
    )  # Use blueprint name
    assert response.status_code == 200  # The page should still load
    assert b"Error: The required file" in response.data
    assert b"sec_Spread.csv" in response.data
    mock_load_data.assert_not_called()
    mock_calc_metrics.assert_not_called()


@patch("views.security_views.load_and_process_security_data")
@patch("views.security_views.calculate_security_latest_metrics")
def test_securities_page_empty_data(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    data_folder = setup_data_folder
    create_dummy_exclusions(data_folder)  # Exclusions file might be checked, create it
    sec_file_path = create_dummy_security_file(data_folder, "sec_Yield.csv")

    # Simulate load_and_process_security_data returning empty data
    mock_load_data.return_value = (
        pd.DataFrame(columns=["Date", "ISIN"]).set_index(["Date", "ISIN"]),
        [],
    )

    response = client.get(
        url_for("security_bp.securities_page", security_type="Yield")
    )  # Use blueprint name
    assert response.status_code == 200
    assert (
        b"No security data found for Yield" in response.data
        or b"No data available" in response.data
    )
    mock_calc_metrics.assert_not_called()


@patch("views.security_views.load_and_process_security_data")
@patch("views.security_views.calculate_security_latest_metrics")
def test_securities_page_empty_after_filtering(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    data_folder = setup_data_folder
    create_dummy_exclusions(data_folder)
    sec_file_path = create_dummy_security_file(data_folder, "sec_Rate.csv")

    # Simulate loading data (including the one to be excluded)
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "SEC001"),
            (pd.Timestamp("2024-01-01"), "EXCLUDED01"),
        ],
        names=["Date", "ISIN"],
    )
    df_long = pd.DataFrame({"Value": [1.0, 99.0]}, index=idx)
    static_cols = ["StaticCol"]
    mock_load_data.return_value = (df_long, static_cols)

    # Simulate metrics calculation returning data including the excluded one
    metrics_df = pd.DataFrame(
        {
            "ISIN": ["SEC001", "EXCLUDED01"],
            "StaticCol": ["A", "Z"],
            "Latest Value": [1.0, 99.0],
            "Change": [0.0, 0.0],
            "Change Z-Score": [0.0, 0.0],
            "Mean": [1.0, 99.0],
            "Max": [1.0, 99.0],
            "Min": [1.0, 99.0],
            "_abs_z_score_": [0.0, 0.0],
        }
    )
    mock_calc_metrics.return_value = metrics_df

    # Test with search term that matches nothing *after* exclusion
    response = client.get(
        url_for(
            "security_bp.securities_page", security_type="Rate", search_term="SEC001"
        )
    )  # Use blueprint name
    assert response.status_code == 200
    assert b"SEC001" in response.data  # SEC001 should be found
    assert b"EXCLUDED01" not in response.data  # But EXCLUDED01 should not
    assert b"No securities match the current criteria" not in response.data

    # Test with search term that filters out SEC001 as well
    response = client.get(
        url_for("security_bp.securities_page", security_type="Rate", search_term="ZZZ")
    )  # Use blueprint name
    assert response.status_code == 200
    assert b"No securities match the current criteria" in response.data
    assert b"SEC001" not in response.data
    assert b"EXCLUDED01" not in response.data


@patch("views.security_views.load_and_process_security_data")
@patch("views.security_views.calculate_security_latest_metrics")
def test_securities_page_pagination(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    data_folder = setup_data_folder
    create_dummy_exclusions(data_folder)  # Excludes EXCLUDED01 if generated
    sec_file_path = create_dummy_security_file(
        data_folder, "sec_Volume.csv"
    )  # Creates SEC001, SEC002, EXCLUDED01

    # Create more data for pagination (let's generate 55 non-excluded)
    num_items = 55
    isins = [
        f"PAGE{i:03d}" for i in range(num_items)
    ]  # + SEC001, SEC002 = 57 total non-excluded
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
    # Data from create_dummy_security_file (SEC001, SEC002, EXCLUDED01)
    base_data = [
        {"ISIN": "SEC001", "Date": dates[0], "Value": 10.0, "StaticCol": "A"},
        {"ISIN": "SEC002", "Date": dates[0], "Value": 20.0, "StaticCol": "B"},
        {"ISIN": "EXCLUDED01", "Date": dates[0], "Value": 99.0, "StaticCol": "Z"},
        {"ISIN": "SEC001", "Date": dates[1], "Value": 10.5, "StaticCol": "A"},
        {"ISIN": "SEC002", "Date": dates[1], "Value": 20.5, "StaticCol": "B"},
        {"ISIN": "EXCLUDED01", "Date": dates[1], "Value": 99.5, "StaticCol": "Z"},
    ]
    page_data = []
    for isin in isins:
        for i, date in enumerate(dates):
            page_data.append(
                {"ISIN": isin, "Date": date, "Value": 100 + i, "StaticCol": "X"}
            )

    all_data = base_data + page_data
    df = pd.DataFrame(all_data)
    idx = pd.MultiIndex.from_frame(df[["Date", "ISIN"]])
    df_long = df[["Value"]].set_index(idx)
    static_cols = ["StaticCol"]
    mock_load_data.return_value = (df_long, static_cols)

    # Mock metrics for all items (including EXCLUDED01 initially)
    metrics_list = []
    all_isins = ["SEC001", "SEC002", "EXCLUDED01"] + isins
    for i, isin in enumerate(all_isins):
        latest_val = df[df["ISIN"] == isin]["Value"].iloc[-1]
        change = df[df["ISIN"] == isin]["Value"].diff().iloc[-1]
        mean = df[df["ISIN"] == isin]["Value"].mean()
        metrics_list.append(
            {
                "ISIN": isin,
                "StaticCol": df[df["ISIN"] == isin]["StaticCol"].iloc[0],
                "Latest Value": latest_val,
                "Change": change,
                "Change Z-Score": 0.5,  # Dummy Z
                "Mean": mean,
                "Max": latest_val,
                "Min": mean - 0.5,
                "_abs_z_score_": 0.5,  # Dummy sort
            }
        )
    metrics_df = pd.DataFrame(metrics_list)
    mock_calc_metrics.return_value = metrics_df

    # Total items = 57 (SEC001, SEC002, PAGE000-PAGE054). Default page size 50.
    # Expect Page 1: 50 items. Page 2: 7 items.

    # Test page 1
    response = client.get(
        url_for("security_bp.securities_page", security_type="Volume", page=1)
    )  # Use blueprint name
    assert response.status_code == 200
    assert b"SEC001" in response.data  # Assuming default sort shows these first
    assert b"SEC002" in response.data
    assert b"EXCLUDED01" not in response.data  # Should be excluded
    assert b"PAGE047" in response.data  # Check towards end of page 1
    assert b"PAGE050" not in response.data  # Should be on page 2
    assert b"Page 1 of 2" in response.data

    # Test page 2
    response = client.get(
        url_for("security_bp.securities_page", security_type="Volume", page=2)
    )  # Use blueprint name
    assert response.status_code == 200
    assert b"PAGE050" in response.data
    assert b"PAGE054" in response.data  # Last item
    assert b"SEC001" not in response.data
    assert b"EXCLUDED01" not in response.data
    assert b"Page 2 of 2" in response.data


@patch("views.security_views.load_and_process_security_data")
@patch(
    "views.security_views.calculate_security_latest_metrics"
)  # Calc may not be needed if only loading
def test_security_details_success(
    mock_calc_metrics, mock_load_data, client, setup_data_folder
):
    data_folder = setup_data_folder
    security_type = "Spread"
    security_id = "SEC001"
    sec_file_path = create_dummy_security_file(data_folder, f"sec_{security_type}.csv")

    # Mock load_and_process_security_data returning data for the specific security
    # ... (mock setup for df_long, just for SEC001) ...
    idx = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2024-01-01"), "SEC001"),
            (pd.Timestamp("2024-01-02"), "SEC001"),
        ],
        names=["Date", "ISIN"],
    )
    df_long_sec = pd.DataFrame({"Value": [10.0, 10.5]}, index=idx)
    static_cols = ["StaticCol"]  # Static cols might be returned by load_and_process
    mock_load_data.return_value = (df_long_sec, static_cols)

    # Mock metric calculation if the details page uses it (optional)
    # For now, assume details page primarily uses the loaded df_long_sec for plotting
    # mock_calc_metrics.return_value = pd.DataFrame(...) # Mock if needed

    response = client.get(
        url_for(
            "security_bp.security_details",
            security_type=security_type,
            security_id=security_id,
        )
    )  # Use blueprint name
    assert response.status_code == 200
    assert f"{security_id} Details ({security_type})".encode() in response.data
    assert b"chartData" in response.data  # Check if chart data structure is present
    assert b"SEC001" in response.data


@patch("views.security_views.load_and_process_security_data")
def test_security_details_missing_file(mock_load_data, client, setup_data_folder):
    data_folder = setup_data_folder
    security_type = "Rate"
    security_id = "SEC999"
    # Do not create the file sec_Rate.csv

    # os.path.exists will return False due to fixture

    response = client.get(
        url_for(
            "security_bp.security_details",
            security_type=security_type,
            security_id=security_id,
        )
    )  # Use blueprint name
    # The route might return 200 with an error message, or 404 depending on implementation
    assert response.status_code == 200  # Assuming it renders page with error
    assert f"Error: Data file for {security_type} not found".encode() in response.data
    mock_load_data.assert_not_called()
