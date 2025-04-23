# Purpose: Unit tests for metric_views.py, covering the /metric/<metric_name> route, handling success, missing files, load errors, calculation errors, and missing secondary data scenarios.

import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
import pandas as pd
import os
from pathlib import Path # Import Path

# Remove unused fixture
# @pytest.fixture
# def mock_data_files(tmp_path):
#     pass

# Update helper to use pathlib
def create_dummy_metric_file(data_folder_path: Path, metric_name: str, is_secondary: bool = False) -> Path:
    """Helper to create dummy metric files (ts_* or sp_ts_*) using pathlib."""
    prefix = "sp_ts_" if is_secondary else "ts_"
    file_path = data_folder_path / f"{prefix}{metric_name}.csv"
    # Basic structure expected by load_and_process_data
    code_prefix = f"Sec{metric_name}" if is_secondary else f"Fund{metric_name}"
    bench_prefix = f"SecBench{metric_name}" if is_secondary else f"Bench{metric_name}"
    df = pd.DataFrame({
        'Date': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'Code': [code_prefix]*2,
        'Value': [50, 51] if is_secondary else [100, 101],
        'Benchmark': [bench_prefix]*2
    })
    # Ensure parent directory exists
    data_folder_path.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False)
    return file_path

# Add fixture to manage data folder per test using tmp_path
@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    monkeypatch.setitem(client.application.config, 'DATA_FOLDER', str(data_folder))
    # Also patch os.path.exists globally for simplicity in this file,
    # assuming we only care if files *created* by the test exist.
    # More granular mocking can be done per-test if needed.
    original_exists = os.path.exists
    def mock_exists(path):
        # Check if the path is within our temp data folder
        try:
            # Use resolve to handle potential relative paths correctly
            path_obj = Path(path).resolve()
            data_folder_resolved = data_folder.resolve()
            if path_obj.is_relative_to(data_folder_resolved):
                return path_obj.exists() # Check actual existence in tmp_path
        except (TypeError, ValueError):
             # Handle potential invalid path types gracefully
            pass
        except Exception as e:
             # Catch potential 'is_relative_to' errors if paths are tricky
             # print(f"Debug: Error checking path {path}: {e}") # Optional debug
            pass
        # Fallback for paths outside the managed data folder (if any)
        return original_exists(path)

    with patch('views.metric_views.os.path.exists', side_effect=mock_exists):
         yield data_folder # Provide the data folder path to tests

# Note: Removed @patch('views.metric_views.os.path.exists') from individual tests
# as it's now handled by the setup_data_folder fixture's context manager.

@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_success(mock_calc_metrics, mock_load_data, client, setup_data_folder): # Use client, setup_data_folder
    metric_name = 'Yield'
    data_folder = setup_data_folder # Use path from fixture
    primary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=False)
    secondary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=True)

    # Mock data loading (needs to be called twice: primary then secondary)
    idx_p = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'Fund{metric_name}'), (pd.Timestamp('2024-01-02'), f'Fund{metric_name}')], names=['Date', 'Code'])
    primary_data = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'Bench{metric_name}']*2}, index=idx_p)
    idx_s = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'Sec{metric_name}'), (pd.Timestamp('2024-01-02'), f'Sec{metric_name}')], names=['Date', 'Code'])
    secondary_data = pd.DataFrame({'Value': [50, 51], 'Benchmark': [f'SecBench{metric_name}']*2}, index=idx_s)

    mock_load_data.side_effect = [
        (primary_data, 'Benchmark'),   # Result for primary load
        (secondary_data, 'Benchmark') # Result for secondary load
    ]

    # Mock metric calculation (receives primary_df, secondary_df)
    metrics_df = primary_data.copy() # Simplistic mock
    metrics_df['FundYield Change Z-Score'] = 1.0 # Add expected z-score column
    mock_calc_metrics.return_value = (metrics_df, {}) # Return tuple

    response = client.get(url_for('metric_bp.metric_page', metric_name=metric_name)) # Ensure correct blueprint name
    assert response.status_code == 200
    assert f'{metric_name} Metric Page'.encode() in response.data
    assert f'Fund{metric_name}'.encode() in response.data
    # Check if secondary data presence is indicated (depends on template)
    # assert b'Secondary Data Available' in response.data 

@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_missing_file(mock_calc_metrics, mock_load_data, client, setup_data_folder): # Use client, setup_data_folder
    metric_name = 'NonexistentMetric'
    # Don't create any files in setup_data_folder

    # os.path.exists will correctly report False due to the fixture's mock

    response = client.get(url_for('metric_bp.metric_page', metric_name=metric_name)) # Ensure correct blueprint name
    assert response.status_code == 404 # Should be 404 if primary file not found
    assert b'Error: Primary data file not found' in response.data

@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_empty_data(mock_calc_metrics, mock_load_data, client, setup_data_folder): # Use client, setup_data_folder
    metric_name = 'Yield'
    data_folder = setup_data_folder
    primary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=False)
    # Don't create secondary for this test

    # os.path.exists handled by fixture

    # Simulate load_and_process_data raising an error for the primary file
    mock_load_data.side_effect = ValueError("Failed to process primary data file")

    response = client.get(url_for('metric_bp.metric_page', metric_name=metric_name)) # Ensure correct blueprint name
    assert response.status_code == 500 # Or appropriate error code
    assert b'Error: Failed to process primary data file' in response.data

@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_secondary_missing(mock_calc_metrics, mock_load_data, client, setup_data_folder): # Use client, setup_data_folder
    metric_name = 'Yield'
    data_folder = setup_data_folder
    primary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=False)
    # DO NOT create secondary file

    # os.path.exists handled by fixture (will be True for primary, False for secondary)

    # Mock primary data loading success
    idx_p = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'Fund{metric_name}'), (pd.Timestamp('2024-01-02'), f'Fund{metric_name}')], names=['Date', 'Code'])
    primary_data = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'Bench{metric_name}']*2}, index=idx_p)
    mock_load_data.return_value = (primary_data, 'Benchmark') # Only called once for primary

    # Mock metric calculation (should only receive primary_df)
    metrics_df = primary_data.copy()
    metrics_df['FundYield Change Z-Score'] = 1.0
    mock_calc_metrics.return_value = (metrics_df, {})

    response = client.get(url_for('metric_bp.metric_page', metric_name=metric_name)) # Ensure correct blueprint name
    assert response.status_code == 200
    assert b'Yield Metric Page' in response.data
    assert b'Secondary data file (sp_ts_Yield.csv) not found or failed to load.' in response.data

@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_metric_calc_error(mock_calc_metrics, mock_load_data, client, setup_data_folder): # Use client, setup_data_folder
    metric_name = 'Yield'
    data_folder = setup_data_folder
    primary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=False)
    secondary_file = create_dummy_metric_file(data_folder, metric_name, is_secondary=True)

    # os.path.exists handled by fixture

    # Mock successful data loading for both
    idx_p = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'Fund{metric_name}'), (pd.Timestamp('2024-01-02'), f'Fund{metric_name}')], names=['Date', 'Code'])
    primary_data = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'Bench{metric_name}']*2}, index=idx_p)
    idx_s = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'Sec{metric_name}'), (pd.Timestamp('2024-01-02'), f'Sec{metric_name}')], names=['Date', 'Code'])
    secondary_data = pd.DataFrame({'Value': [50, 51], 'Benchmark': [f'SecBench{metric_name}']*2}, index=idx_s)
    mock_load_data.side_effect = [
        (primary_data, 'Benchmark'),
        (secondary_data, 'Benchmark')
    ]

    # Simulate error during metric calculation
    mock_calc_metrics.side_effect = ValueError("Metric calculation failed")

    response = client.get(url_for('metric_bp.metric_page', metric_name=metric_name)) # Ensure correct blueprint name
    assert response.status_code == 500 # Or appropriate error code
    assert b'Error processing metric page for Yield' in response.data
    assert b'Metric calculation failed' in response.data 