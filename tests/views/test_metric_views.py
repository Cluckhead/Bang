# Purpose: Unit tests for metric_views.py, covering the /metric/<metric_name> route, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['DATA_FOLDER'] = '/mock/data/folder'
    app.config['TESTING'] = True
    from views.metric_views import metric_bp
    app.register_blueprint(metric_bp)
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('views.metric_views.os.path.exists')
@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_success(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists
    mock_exists.return_value = True
    # Mock load_and_process_data to return valid data
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'FundA')], names=['Date', 'Fund'])
    primary_df = pd.DataFrame({'Value': [1]}, index=idx)
    mock_load_data.return_value = (primary_df, ['FundA'], 'BenchmarkA', None, None, None)
    # Mock calculate_latest_metrics to return DataFrame
    metrics_df = pd.DataFrame({'FundA Change Z-Score': [0.5]}, index=['FundA'])
    mock_calc_metrics.return_value = metrics_df
    response = client.get('/metric/Yield')
    assert response.status_code == 200
    assert b'Yield' in response.data
    assert b'charts_data_json' in response.data or b'charts' in response.data

@patch('views.metric_views.os.path.exists')
@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_missing_file(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file does not exist
    mock_exists.return_value = False
    mock_load_data.return_value = (None, None, None, None, None, None)
    response = client.get('/metric/NonexistentMetric')
    assert response.status_code == 404
    assert b'not found' in response.data or b'Error' in response.data

@patch('views.metric_views.os.path.exists')
@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_empty_data(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists but data is empty
    mock_exists.return_value = True
    mock_load_data.return_value = (pd.DataFrame(), ['FundA'], 'BenchmarkA', None, None, None)
    response = client.get('/metric/Yield')
    assert response.status_code == 500 or b'no fund data' in response.data or b'Error' in response.data

@patch('views.metric_views.os.path.exists')
@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_secondary_missing(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate secondary data missing
    mock_exists.return_value = True
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'FundA')], names=['Date', 'Fund'])
    primary_df = pd.DataFrame({'Value': [1]}, index=idx)
    mock_load_data.return_value = (primary_df, ['FundA'], 'BenchmarkA', None, None, None)
    metrics_df = pd.DataFrame({'FundA Change Z-Score': [0.5]}, index=['FundA'])
    mock_calc_metrics.return_value = metrics_df
    response = client.get('/metric/Yield')
    assert response.status_code == 200
    assert b'Yield' in response.data

@patch('views.metric_views.os.path.exists')
@patch('views.metric_views.load_and_process_data')
@patch('views.metric_views.calculate_latest_metrics')
def test_metric_page_metric_calc_error(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate error in metric calculation
    mock_exists.return_value = True
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'FundA')], names=['Date', 'Fund'])
    primary_df = pd.DataFrame({'Value': [1]}, index=idx)
    mock_load_data.return_value = (primary_df, ['FundA'], 'BenchmarkA', None, None, None)
    mock_calc_metrics.side_effect = Exception('Metric calculation failed')
    response = client.get('/metric/Yield')
    assert response.status_code == 500 or b'Error' in response.data 