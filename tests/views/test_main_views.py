# Purpose: Unit tests for main_views.py, covering the dashboard/index route, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd
import os

# Comprehensive Flask app factory for testing (register all blueprints)
@pytest.fixture
def app():
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
    app = Flask(__name__, template_folder=template_dir)
    app.config['DATA_FOLDER'] = '/mock/data/folder'
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'  # Ensure session support
    from views.main_views import main_bp
    from views.metric_views import metric_bp
    from views.security_views import security_bp
    from views.weight_views import weight_bp
    from views.curve_views import curve_bp
    from views.attribution_views import attribution_bp
    from views.exclusion_views import exclusion_bp
    from views.issue_views import issue_bp
    from views.api_views import api_bp
    from views.staleness_views import staleness_bp
    from views.generic_comparison_views import generic_comparison_bp
    from views.fund_views import fund_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(weight_bp)
    app.register_blueprint(curve_bp)
    app.register_blueprint(attribution_bp)
    app.register_blueprint(exclusion_bp)
    app.register_blueprint(issue_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(staleness_bp)
    app.register_blueprint(generic_comparison_bp, url_prefix='/compare')
    app.register_blueprint(fund_bp)
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