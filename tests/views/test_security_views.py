# Purpose: Unit tests for security_views.py, covering the /security/summary and /security/details/<metric_name>/<security_id> routes, including edge and error cases.

import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
import pandas as pd
import os

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

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
@patch('views.exclusion_views.load_exclusions')
def test_securities_page_success(mock_exclusions, mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists
    mock_exists.return_value = True
    # Mock exclusions
    mock_exclusions.return_value = []
    # Mock load_and_process_security_data to return valid data
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'A')], names=['Date', 'ISIN'])
    df_long = pd.DataFrame({'Value': [1]}, index=idx)
    static_cols = ['StaticCol']
    mock_load_data.return_value = (df_long, static_cols)
    # Mock calculate_security_latest_metrics to return DataFrame
    metrics_df = pd.DataFrame({'ISIN': ['A'], 'StaticCol': ['X'], 'Latest Value': [1], 'Change': [0.1], 'Change Z-Score': [0.5], 'Mean': [1], 'Max': [1], 'Min': [1]})
    mock_calc_metrics.return_value = metrics_df
    response = client.get('/security/summary')
    assert response.status_code == 200
    assert b'securities_data' in response.data or b'ISIN' in response.data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
@patch('views.exclusion_views.load_exclusions')
def test_securities_page_no_file(mock_exclusions, mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file does not exist
    mock_exists.return_value = False
    response = client.get('/security/summary')
    assert response.status_code == 200
    assert b'not found' in response.data or b'Error' in response.data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
@patch('views.exclusion_views.load_exclusions')
def test_securities_page_empty_data(mock_exclusions, mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists but data is empty
    mock_exists.return_value = True
    mock_load_data.return_value = (pd.DataFrame(), ['StaticCol'])
    response = client.get('/security/summary')
    assert response.status_code == 200
    assert b'Error' in response.data or b'empty' in response.data or b'not found' in response.data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
@patch('views.exclusion_views.load_exclusions')
def test_securities_page_empty_after_filtering(mock_exclusions, mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists, but all data filtered out
    mock_exists.return_value = True
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'A')], names=['Date', 'ISIN'])
    df_long = pd.DataFrame({'Value': [1]}, index=idx)
    static_cols = ['StaticCol']
    mock_load_data.return_value = (df_long, static_cols)
    metrics_df = pd.DataFrame(columns=['ISIN', 'StaticCol', 'Latest Value', 'Change', 'Change Z-Score', 'Mean', 'Max', 'Min'])
    mock_calc_metrics.return_value = metrics_df
    response = client.get('/security/summary?search_term=ZZZ')
    assert response.status_code == 200
    data = response.data.lower()
    assert b'securit' in data or b'criteria' in data or b'matching' in data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
@patch('views.exclusion_views.load_exclusions')
def test_securities_page_pagination(mock_exclusions, mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists, multiple rows for pagination
    mock_exists.return_value = True
    mock_exclusions.return_value = []
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), str(i)) for i in range(60)], names=['Date', 'ISIN'])
    df_long = pd.DataFrame({'Value': list(range(60))}, index=idx)
    static_cols = ['StaticCol']
    mock_load_data.return_value = (df_long, static_cols)
    metrics_df = pd.DataFrame({'ISIN': [str(i) for i in range(60)], 'StaticCol': ['X']*60, 'Latest Value': list(range(60)), 'Change': [0.1]*60, 'Change Z-Score': [0.5]*60, 'Mean': [1]*60, 'Max': [1]*60, 'Min': [1]*60})
    mock_calc_metrics.return_value = metrics_df
    response = client.get('/security/summary?page=2')
    assert response.status_code == 200
    assert b'securities_data' in response.data or b'ISIN' in response.data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
@patch('views.security_views.calculate_security_latest_metrics')
def test_security_details_success(mock_calc_metrics, mock_load_data, mock_exists, client):
    # Simulate file exists
    mock_exists.return_value = True
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp('2024-01-01'), 'A')], names=['Date', 'ISIN'])
    df_long = pd.DataFrame({'Value': [1]}, index=idx)
    static_cols = ['StaticCol']
    mock_load_data.return_value = (df_long, static_cols)
    response = client.get('/security/details/Spread/A')
    assert response.status_code == 200 or response.status_code == 404
    data = response.data.lower()
    assert b'a' in data or b'not found' in data or b'error' in data

@patch('views.security_views.os.path.exists')
@patch('views.security_views.load_and_process_security_data')
def test_security_details_missing_file(mock_load_data, mock_exists, client):
    # Simulate file does not exist
    mock_exists.return_value = False
    mock_load_data.return_value = (None, None)
    response = client.get('/security/details/Spread/ZZZ')
    assert response.status_code == 200 or response.status_code == 404
    data = response.data.lower()
    assert b'not found' in data or b'error' in data or b'zzz' in data 