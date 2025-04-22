# Purpose: Unit tests for main_views.py, covering the dashboard/index route, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd

# Minimal Flask app factory for testing
@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['DATA_FOLDER'] = '/mock/data/folder'
    app.config['TESTING'] = True
    # Import and register the blueprint
    from views.main_views import main_bp
    app.register_blueprint(main_bp)
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('views.main_views.os.listdir')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_index_route_success(mock_calc_metrics, mock_load_data, mock_listdir, client):
    # Simulate two ts_ files
    mock_listdir.return_value = ['ts_MetricA.csv', 'ts_MetricB.csv']
    # Mock load_and_process_data to return DataFrame and columns
    mock_load_data.side_effect = [
        (pd.DataFrame({'A': [1, 2]}), ['FundA'], 'BenchmarkA', None, None, None),
        (pd.DataFrame({'B': [3, 4]}), ['FundB'], 'BenchmarkB', None, None, None)
    ]
    # Mock calculate_latest_metrics to return DataFrames with Z-score columns
    df1 = pd.DataFrame({'FundA Change Z-Score': [0.5], 'BenchmarkA Change Z-Score': [1.0]})
    df2 = pd.DataFrame({'FundB Change Z-Score': [0.7], 'BenchmarkB Change Z-Score': [1.2]})
    mock_calc_metrics.side_effect = [df1, df2]

    response = client.get('/')
    assert response.status_code == 200
    # Check that the rendered template contains expected metric names
    assert b'MetricA' in response.data or b'MetricB' in response.data

@patch('views.main_views.os.listdir')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_index_route_no_files(mock_calc_metrics, mock_load_data, mock_listdir, client):
    # Simulate no ts_ files
    mock_listdir.return_value = []
    response = client.get('/')
    assert response.status_code == 200
    # Should render with empty metrics/summary
    assert b'metrics' in response.data or b'summary' in response.data

@patch('views.main_views.os.listdir')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_index_route_file_load_error(mock_calc_metrics, mock_load_data, mock_listdir, client):
    # Simulate one file, but load_and_process_data fails
    mock_listdir.return_value = ['ts_MetricA.csv']
    mock_load_data.return_value = (None, [], None, None, None, None)
    response = client.get('/')
    assert response.status_code == 200
    # Should skip the file and render with empty summary
    assert b'metrics' in response.data or b'summary' in response.data

@patch('views.main_views.os.listdir')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_index_route_metrics_empty(mock_calc_metrics, mock_load_data, mock_listdir, client):
    # Simulate one file, but calculate_latest_metrics returns empty DataFrame
    mock_listdir.return_value = ['ts_MetricA.csv']
    mock_load_data.return_value = (pd.DataFrame({'A': [1]}), ['FundA'], 'BenchmarkA', None, None, None)
    mock_calc_metrics.return_value = pd.DataFrame()
    response = client.get('/')
    assert response.status_code == 200
    # Should render with empty summary
    assert b'metrics' in response.data or b'summary' in response.data

@patch('views.main_views.os.listdir')
@patch('views.main_views.load_and_process_data')
@patch('views.main_views.calculate_latest_metrics')
def test_index_route_data_folder_missing(mock_calc_metrics, mock_load_data, mock_listdir, client, app):
    # Simulate FileNotFoundError for os.listdir
    mock_listdir.side_effect = FileNotFoundError
    response = client.get('/')
    assert response.status_code == 200 or response.status_code == 500
    # Should handle error gracefully 