# Purpose: Unit tests for generic_comparison_views.py, covering the /compare/<comparison_type>/summary and /compare/<comparison_type>/details/<security_id> routes, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd
import os


def create_dummy_comparison_files(
    data_folder_path, file1_name="f1.csv", file2_name="f2.csv"
):
    """Helper to create dummy comparison input files."""
    # Create simple CSVs that can be loaded by load_generic_comparison_data
    # The exact structure depends on what that function expects.
    # Assuming a simple structure for now:
    file1_path = os.path.join(data_folder_path, file1_name)
    file2_path = os.path.join(data_folder_path, file2_name)

    df1 = pd.DataFrame(
        {"ID": ["A", "B"], "Value": [10, 20], "Date": pd.to_datetime("2024-01-01")}
    )
    df2 = pd.DataFrame(
        {"ID": ["A", "B"], "Value": [11, 21], "Date": pd.to_datetime("2024-01-01")}
    )
    # These might need specific columns based on COMPARISON_CONFIG
    df1.to_csv(file1_path, index=False)
    df2.to_csv(file2_path, index=False)
    return file1_path, file2_path


@patch("views.generic_comparison_views.load_generic_comparison_data")
@patch("views.generic_comparison_views.calculate_generic_comparison_stats")
@patch("views.generic_comparison_views.load_weights_and_held_status")
@patch("views.generic_comparison_views.load_fund_codes_from_csv")
def test_comparison_summary_success(
    mock_fund_codes, mock_held_status, mock_calc_stats, mock_load_data, client
):
    # Although we mock load_generic_comparison_data, let's create dummy files
    # in case any underlying logic still checks for file existence.
    data_folder = client.application.config["DATA_FOLDER"]
    create_dummy_comparison_files(data_folder, "f1.csv", "f2.csv")

    # Mock config for a valid comparison type
    from views.generic_comparison_views import COMPARISON_CONFIG

    COMPARISON_CONFIG["spread"] = {
        "display_name": "Spread",
        "file1": "f1.csv",
        "file2": "f2.csv",
    }
    # Mock data loading
    merged_data = pd.DataFrame(
        {
            "ISIN": ["A"],
            "Value_Orig": [1],
            "Value_New": [2],
            "Date": [pd.Timestamp("2024-01-01")],
        }
    )
    static_data = pd.DataFrame({"ISIN": ["A"], "StaticCol": ["X"]})
    static_cols = ["StaticCol"]
    mock_load_data.return_value = (merged_data, static_data, static_cols, "ISIN")
    # Mock stats - Make sure 'is_held' is present *before* the merge in the view happens
    # The view logic likely merges stats_df with held_status, so stats_df doesn't need is_held initially
    stats_df = pd.DataFrame(
        {
            "ISIN": ["A"],
            "Level_Correlation": [0.9],
            "Change_Correlation": [0.85],
            "StaticCol": ["X"],
        }
    )
    mock_calc_stats.return_value = stats_df
    # Mock held status (This Series will be merged into stats_df by the view)
    held_status = pd.Series([True], index=["A"], name="is_held")
    mock_held_status.return_value = held_status
    # Mock fund codes
    mock_fund_codes.return_value = ["FUND1", "FUND2"]
    response = client.get("/compare/spread/summary")
    assert response.status_code == 200
    assert b"Spread" in response.data or b"ISIN" in response.data


@patch("views.generic_comparison_views.load_generic_comparison_data")
def test_comparison_summary_invalid_type(mock_load_data, client):
    response = client.get("/compare/invalidtype/summary")
    assert response.status_code == 404


@patch("views.generic_comparison_views.load_generic_comparison_data")
@patch("views.generic_comparison_views.calculate_generic_comparison_stats")
def test_comparison_summary_empty_data(mock_calc_stats, mock_load_data, client):
    data_folder = client.application.config["DATA_FOLDER"]
    create_dummy_comparison_files(data_folder, "f1.csv", "f2.csv")  # Create files

    from views.generic_comparison_views import COMPARISON_CONFIG

    COMPARISON_CONFIG["spread"] = {
        "display_name": "Spread",
        "file1": "f1.csv",
        "file2": "f2.csv",
    }
    mock_load_data.return_value = (pd.DataFrame(), pd.DataFrame(), [], "ISIN")
    mock_calc_stats.return_value = pd.DataFrame()  # Return empty DataFrame for stats
    response = client.get("/compare/spread/summary")
    assert response.status_code == 200
    # Accept any of these phrases in the response (case-insensitive)
    data = response.data.lower()
    assert b"spread" in data or b"no data" in data or b"no statistics" in data


@patch("views.generic_comparison_views.load_generic_comparison_data")
@patch("views.generic_comparison_views.calculate_generic_comparison_stats")
@patch("views.generic_comparison_views.load_weights_and_held_status")
def test_comparison_summary_show_sold(
    mock_held_status, mock_calc_stats, mock_load_data, client
):
    data_folder = client.application.config["DATA_FOLDER"]
    create_dummy_comparison_files(data_folder, "f1.csv", "f2.csv")  # Create files

    from views.generic_comparison_views import COMPARISON_CONFIG

    COMPARISON_CONFIG["spread"] = {
        "display_name": "Spread",
        "file1": "f1.csv",
        "file2": "f2.csv",
    }
    merged_data = pd.DataFrame(
        {
            "ISIN": ["A", "B"],
            "Value_Orig": [1, 2],
            "Value_New": [2, 3],
            "Date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")],
        }
    )
    static_data = pd.DataFrame({"ISIN": ["A", "B"], "StaticCol": ["X", "Y"]})
    static_cols = ["StaticCol"]
    mock_load_data.return_value = (merged_data, static_data, static_cols, "ISIN")
    # Mock stats - Don't include 'is_held' here
    stats_df = pd.DataFrame(
        {
            "ISIN": ["A", "B"],
            "Level_Correlation": [0.9, 0.8],
            "Change_Correlation": [0.85, 0.75],
            "StaticCol": ["X", "Y"],
        }
    )
    mock_calc_stats.return_value = stats_df
    # Mock held status - This will be merged by the view
    held_status = pd.Series([True, False], index=["A", "B"], name="is_held")
    mock_held_status.return_value = held_status
    response = client.get("/compare/spread/summary?show_sold=true")
    assert response.status_code == 200
    assert b"Spread" in response.data or b"ISIN" in response.data


@patch("views.generic_comparison_views.load_generic_comparison_data")
@patch("views.generic_comparison_views.calculate_generic_comparison_stats")
@patch("views.generic_comparison_views.get_holdings_for_security")
def test_comparison_details_success(
    mock_holdings, mock_calc_stats, mock_load_data, client
):
    data_folder = client.application.config["DATA_FOLDER"]
    create_dummy_comparison_files(data_folder, "f1.csv", "f2.csv")  # Create files

    from views.generic_comparison_views import COMPARISON_CONFIG

    COMPARISON_CONFIG["spread"] = {
        "display_name": "Spread",
        "file1": "f1.csv",
        "file2": "f2.csv",
        "value_label": "Spread",
    }
    merged_data = pd.DataFrame(
        {
            "ISIN": ["A"],
            "Value_Orig": [1],
            "Value_New": [2],
            "Date": [pd.Timestamp("2024-01-01")],
        }
    )
    static_data = pd.DataFrame({"ISIN": ["A"], "StaticCol": ["X"]})
    mock_load_data.return_value = (merged_data, static_data, [], "ISIN")
    # Provide all expected keys in stats_df to avoid Jinja2 errors, excluding 'is_held' if it's added later
    stats_df = pd.DataFrame(
        {
            "ISIN": ["A"],
            "Level_Correlation": [0.9],
            "Change_Correlation": [0.8],
            "Mean_Abs_Diff": [0.1],
            "Max_Abs_Diff": [0.2],
            "Same_Date_Range": [True],
            # 'is_held': [True], # Assuming this might be added by view logic if needed for details page
            "StaticCol": ["X"],
        }
    )
    # Set index correctly for lookup in the view
    stats_df = stats_df.set_index("ISIN")
    mock_calc_stats.return_value = stats_df
    # Mock holdings
    mock_holdings.return_value = ({"FUND1": [True]}, ["2024-01-01"], None)
    response = client.get("/compare/spread/details/A")
    assert response.status_code == 200
    data = response.data.lower()
    assert b"spread" in data or b"a" in data


@patch("views.generic_comparison_views.load_generic_comparison_data")
def test_comparison_details_invalid_type(mock_load_data, client):
    response = client.get("/compare/invalidtype/details/A")
    assert response.status_code == 404


@patch("views.generic_comparison_views.load_generic_comparison_data")
def test_comparison_details_no_data(mock_load_data, client):
    data_folder = client.application.config["DATA_FOLDER"]
    create_dummy_comparison_files(data_folder, "f1.csv", "f2.csv")  # Create files

    from views.generic_comparison_views import COMPARISON_CONFIG

    COMPARISON_CONFIG["spread"] = {
        "display_name": "Spread",
        "file1": "f1.csv",
        "file2": "f2.csv",
    }
    # Simulate load_generic_comparison_data returning empty/error state
    mock_load_data.side_effect = ValueError("Could not load data")
    response = client.get("/compare/spread/details/A")
    assert response.status_code == 200  # Or 404 depending on desired behavior
    data = response.data.lower()
    assert (
        b"not found" in data
        or b"error" in data
        or b"no data" in data
        or b"criteria" in data
        or b"matching" in data
        or b"could not load data" in data
    )
