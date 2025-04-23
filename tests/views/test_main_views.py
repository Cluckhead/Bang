# Purpose: Unit tests for main_views.py, primarily testing the main dashboard/index route, ensuring correct aggregation of Z-scores from metric files, handling missing files, load errors, and calculation errors.
# Purpose: Unit tests for main_views.py, covering the dashboard/index route, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd
import os
from pathlib import Path # Import Path

# Remove the local app fixture
# @pytest.fixture
# def app():
#     template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
#     app = Flask(__name__, template_folder=template_dir)
#     app.config['DATA_FOLDER'] = '/mock/data/folder' # This will be handled differently now
#     app.config['TESTING'] = True
#     app.config['SECRET_KEY'] = 'test'  # Ensure session support
#     from views.main_views import main_bp
#     # ... (rest of blueprint registrations) ...
#     app.register_blueprint(main_bp)
#     # ... (rest of blueprint registrations) ...
#     return app

# Use tmp_path provided by pytest for file operations
def create_dummy_metric_file(data_folder_path: Path, metric_name: str) -> Path:
    """Helper to create a dummy ts_*.csv file using pathlib."""
    file_path = data_folder_path / f"ts_{metric_name}.csv"
    # Basic structure expected by load_and_process_data
    df = pd.DataFrame({
        'Date': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'Code': [f'Fund{metric_name}', f'Fund{metric_name}'], # Or use Code directly if needed
        'Value': [100, 101],
        'Benchmark': [f'Bench{metric_name}', f'Bench{metric_name}']
    })
    # Ensure parent directory exists
    data_folder_path.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False)
    return file_path

# Remove the unused mock_dashboard_data fixture
# @pytest.fixture
# def mock_dashboard_data(tmp_path):
#     pass

@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    # Use monkeypatch to set the config value for the duration of the test
    monkeypatch.setitem(client.application.config, 'DATA_FOLDER', str(data_folder))
    return data_folder


@patch('views.main_views.os.listdir')
@patch('views.main_views.os.path.exists') # Keep this mock if internal logic uses it, but prefer config
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_dashboard_success(mock_calc_metrics, mock_load_data, mock_exists, mock_listdir, client, setup_data_folder): # Use client from conftest, add setup_data_folder
    data_folder = setup_data_folder # Use the path from the fixture
    # Create dummy files needed for the test
    file_a_path = create_dummy_metric_file(data_folder, "MetricA")
    file_b_path = create_dummy_metric_file(data_folder, "MetricB")
    (data_folder / "other_file.txt").write_text("ignore me") # Non-metric file

    # Mock os.listdir to return the created files (and potentially others)
    mock_listdir.return_value = [file_a_path.name, file_b_path.name, 'other_file.txt']
    # Mock os.path.exists used within the loop (should return True for created files)
    mock_exists.return_value = True # Assume exists for now

    # Mock data loading results (ensure structure matches what load_and_process returns)
    # It usually returns (processed_dataframe, benchmark_column_name)
    idx_a = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'FundMetricA'), (pd.Timestamp('2024-01-02'), f'FundMetricA')], names=['Date', 'Code'])
    primary_df_a = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'BenchMetricA', f'BenchMetricA']}, index=idx_a)
    idx_b = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'FundMetricB'), (pd.Timestamp('2024-01-02'), f'FundMetricB')], names=['Date', 'Code'])
    primary_df_b = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'BenchMetricB', f'BenchMetricB']}, index=idx_b)
    mock_load_data.side_effect = [
        (primary_df_a, 'Benchmark'), # Note: Benchmark col name is 'Benchmark' here
        (primary_df_b, 'Benchmark')
    ]

    # Mock metric calculation results
    metrics_a = pd.DataFrame({'FundMetricA Change Z-Score': [1.0], 'Benchmark Change Z-Score': [0.5]})
    metrics_b = pd.DataFrame({'FundMetricB Change Z-Score': [-1.0], 'Benchmark Change Z-Score': [-0.5]})
    # The function calculate_latest_metrics expects the *primary_df* as input
    # Let's refine the mock based on expected calls
    def calc_metrics_side_effect(df, *args, **kwargs):
        if not df.empty and 'FundMetricA' in df.index.get_level_values('Code'):
            return (metrics_a, {}) # Return tuple (metrics_df, missing_data_info)
        elif not df.empty and 'FundMetricB' in df.index.get_level_values('Code'):
            return (metrics_b, {})
        else:
            return (pd.DataFrame(), {})
    mock_calc_metrics.side_effect = calc_metrics_side_effect

    response = client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data
    assert b'MetricA' in response.data
    assert b'MetricB' in response.data
    # Check for specific content related to metrics to ensure they were processed
    assert b'FundMetricA - MetricA' in response.data # Example, adjust if template changes
    assert b'Benchmark - MetricB' in response.data # Example, adjust if template changes
    assert b'Summary of Latest Changes' in response.data


@patch('views.main_views.os.listdir')
@patch('views.main_views.os.path.exists')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_dashboard_no_ts_files(mock_calc_metrics, mock_load_data, mock_exists, mock_listdir, client, setup_data_folder): # Use client from conftest
    data_folder = setup_data_folder # Use the path from the fixture
    (data_folder / "other_file.txt").write_text("ignore me") # Create non-metric file

    mock_listdir.return_value = ['other_file.txt'] # List only non-metric file
    mock_exists.return_value = True # Assume folder exists

    response = client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data
    assert b'No Change Z-scores could be extracted' in response.data
    mock_load_data.assert_not_called()
    mock_calc_metrics.assert_not_called()


@patch('views.main_views.os.listdir')
@patch('views.main_views.os.path.exists')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_dashboard_load_error(mock_calc_metrics, mock_load_data, mock_exists, mock_listdir, client, setup_data_folder): # Use client from conftest
    data_folder = setup_data_folder # Use the path from the fixture
    file_a_path = create_dummy_metric_file(data_folder, "MetricA") # Create file first

    mock_listdir.return_value = [file_a_path.name]
    mock_exists.return_value = True
    mock_load_data.side_effect = ValueError("Failed to load") # Simulate error during load

    response = client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data
    assert b'Warning: Failed to load data for ts_MetricA.csv' in response.data
    assert b'No Change Z-scores could be extracted' in response.data # Should be empty
    mock_calc_metrics.assert_not_called() # Calculation shouldn't happen if load fails


@patch('views.main_views.os.listdir')
@patch('views.main_views.os.path.exists')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_dashboard_calc_error(mock_calc_metrics, mock_load_data, mock_exists, mock_listdir, client, setup_data_folder): # Use client from conftest
    data_folder = setup_data_folder # Use the path from the fixture
    file_a_path = create_dummy_metric_file(data_folder, "MetricA") # Create file

    mock_listdir.return_value = [file_a_path.name]
    mock_exists.return_value = True

    # Mock successful load
    idx_a = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), f'FundMetricA'), (pd.Timestamp('2024-01-02'), f'FundMetricA')], names=['Date', 'Code'])
    primary_df_a = pd.DataFrame({'Value': [100, 101], 'Benchmark': [f'BenchMetricA', f'BenchMetricA']}, index=idx_a)
    mock_load_data.return_value = (primary_df_a, 'Benchmark')

    mock_calc_metrics.side_effect = ValueError("Calculation failed") # Simulate error during calculation

    response = client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data
    assert b'Warning: Could not calculate latest_metrics for ts_MetricA.csv' in response.data
    assert b'No Change Z-scores could be extracted' in response.data # Should be empty


# Remove os.path.exists mock, rely on setup_data_folder failure if path doesn't exist
# Or mock the specific check within the route if necessary
def test_dashboard_data_folder_missing(client, monkeypatch): # Use client from conftest
    # Simulate DATA_FOLDER does not exist by setting a non-existent path
    # We rely on the route's internal check `os.path.exists(app.config['DATA_FOLDER'])`
    non_existent_path = "/non/existent/path/that/fails"
    monkeypatch.setitem(client.application.config, 'DATA_FOLDER', non_existent_path)
    
    # Mock os.path.exists ONLY for the specific check in the route
    with patch('views.main_views.os.path.exists') as mock_exists:
        mock_exists.return_value = False # Simulate the folder check failing
        response = client.get('/')

    # Check if the route returns a 500 or handles it gracefully
    # Based on the original test, it seems it expects a 500 and a specific message
    # Let's keep that assertion for now, but ideally the route might render a user-friendly error page (200 OK)
    assert response.status_code == 500 # Or assert 200 if it handles gracefully
    assert b'Configured DATA_FOLDER does not exist' in response.data


# --- Remove redundant tests below as they are covered by the test_dashboard_* tests above ---
# @patch('views.main_views.os.listdir')
# @patch('views.main_views.load_and_process_data')
# @patch('views.main_views.calculate_latest_metrics')
# def test_index_route_success(mock_calc_metrics, mock_load_data, mock_listdir, client):
#     # ... (already covered by test_dashboard_success) ...

# @patch('views.main_views.os.listdir')
# @patch('views.main_views.load_and_process_data')
# @patch('views.main_views.calculate_latest_metrics')
# def test_index_route_no_files(mock_calc_metrics, mock_load_data, mock_listdir, client):
#     # ... (already covered by test_dashboard_no_ts_files) ...

# @patch('views.main_views.os.listdir')
# @patch('views.main_views.load_and_process_data')
# @patch('views.main_views.calculate_latest_metrics')
# def test_index_route_file_load_error(mock_calc_metrics, mock_load_data, mock_listdir, client):
#     # ... (already covered by test_dashboard_load_error) ...

# @patch('views.main_views.os.listdir')
# @patch('views.main_views.load_and_process_data')
# @patch('views.main_views.calculate_latest_metrics')
# def test_index_route_metrics_empty(mock_calc_metrics, mock_load_data, mock_listdir, client):
#     # Similar to calc_error, assuming empty result is handled within the template/logic
#     # Let's keep test_dashboard_calc_error which covers error handling
#     pass # Remove this redundant test

# @patch('views.main_views.os.listdir')
# @patch('views.main_views.load_and_process_data')
# @patch('views.main_views.calculate_latest_metrics')
# def test_index_route_data_folder_missing(mock_calc_metrics, mock_load_data, mock_listdir, client, app): # This test was malformed before
#     # ... (already covered by test_dashboard_data_folder_missing) ...
#     pass # Remove this redundant test 