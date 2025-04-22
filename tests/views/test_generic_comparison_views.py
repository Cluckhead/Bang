# Purpose: Unit tests for generic_comparison_views.py, covering the /compare/<comparison_type>/summary and /compare/<comparison_type>/details/<security_id> routes, including edge and error cases.

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
    from views.generic_comparison_views import generic_comparison_bp
    from views.security_views import security_bp
    from views.weight_views import weight_bp
    from views.curve_views import curve_bp
    from views.attribution_views import attribution_bp
    from views.exclusion_views import exclusion_bp
    from views.issue_views import issue_bp
    from views.api_views import api_bp
    from views.staleness_views import staleness_bp
    app.register_blueprint(main_bp)  # Register main_bp for main.index endpoint
    app.register_blueprint(security_bp)  # Register security_bp for security.securities_page endpoint
    app.register_blueprint(weight_bp)
    app.register_blueprint(curve_bp)
    app.register_blueprint(attribution_bp)
    app.register_blueprint(exclusion_bp)
    app.register_blueprint(issue_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(staleness_bp)
    app.register_blueprint(generic_comparison_bp, url_prefix='/compare')
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('views.generic_comparison_views.load_generic_comparison_data')
@patch('views.generic_comparison_views.calculate_generic_comparison_stats')
@patch('views.generic_comparison_views.load_weights_and_held_status')
@patch('views.generic_comparison_views.load_fund_codes_from_csv')
def test_comparison_summary_success(mock_fund_codes, mock_held_status, mock_calc_stats, mock_load_data, client):
    # Mock config for a valid comparison type
    from views.generic_comparison_views import COMPARISON_CONFIG
    COMPARISON_CONFIG['spread'] = {'display_name': 'Spread', 'file1': 'f1.csv', 'file2': 'f2.csv'}
    # Mock data loading
    merged_data = pd.DataFrame({'ISIN': ['A'], 'Value_Orig': [1], 'Value_New': [2], 'Date': [pd.Timestamp('2024-01-01')]})
    static_data = pd.DataFrame({'ISIN': ['A'], 'StaticCol': ['X']})
    static_cols = ['StaticCol']
    mock_load_data.return_value = (merged_data, static_data, static_cols, 'ISIN')
    # Mock stats
    stats_df = pd.DataFrame({'ISIN': ['A'], 'Level_Correlation': [0.9], 'is_held': [True], 'StaticCol': ['X']})
    mock_calc_stats.return_value = stats_df
    # Mock held status
    held_status = pd.Series([True], index=['A'])
    mock_held_status.return_value = held_status
    # Mock fund codes
    mock_fund_codes.return_value = ['FUND1', 'FUND2']
    response = client.get('/compare/spread/summary')
    assert response.status_code == 200
    assert b'Spread' in response.data or b'ISIN' in response.data

@patch('views.generic_comparison_views.load_generic_comparison_data')
def test_comparison_summary_invalid_type(mock_load_data, client):
    response = client.get('/compare/invalidtype/summary')
    assert response.status_code == 404

@patch('views.generic_comparison_views.load_generic_comparison_data')
@patch('views.generic_comparison_views.calculate_generic_comparison_stats')
def test_comparison_summary_empty_data(mock_calc_stats, mock_load_data, client):
    from views.generic_comparison_views import COMPARISON_CONFIG
    COMPARISON_CONFIG['spread'] = {'display_name': 'Spread', 'file1': 'f1.csv', 'file2': 'f2.csv'}
    mock_load_data.return_value = (pd.DataFrame(), pd.DataFrame(), [], 'ISIN')
    mock_calc_stats.return_value = pd.DataFrame()
    response = client.get('/compare/spread/summary')
    assert response.status_code == 200
    assert b'No Spread comparison statistics available' in response.data or b'empty' in response.data

@patch('views.generic_comparison_views.load_generic_comparison_data')
@patch('views.generic_comparison_views.calculate_generic_comparison_stats')
@patch('views.generic_comparison_views.load_weights_and_held_status')
def test_comparison_summary_show_sold(mock_held_status, mock_calc_stats, mock_load_data, client):
    from views.generic_comparison_views import COMPARISON_CONFIG
    COMPARISON_CONFIG['spread'] = {'display_name': 'Spread', 'file1': 'f1.csv', 'file2': 'f2.csv'}
    merged_data = pd.DataFrame({'ISIN': ['A', 'B'], 'Value_Orig': [1, 2], 'Value_New': [2, 3], 'Date': [pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-01')]})
    static_data = pd.DataFrame({'ISIN': ['A', 'B'], 'StaticCol': ['X', 'Y']})
    static_cols = ['StaticCol']
    mock_load_data.return_value = (merged_data, static_data, static_cols, 'ISIN')
    stats_df = pd.DataFrame({'ISIN': ['A', 'B'], 'Level_Correlation': [0.9, 0.8], 'is_held': [True, False], 'StaticCol': ['X', 'Y']})
    mock_calc_stats.return_value = stats_df
    held_status = pd.Series([True, False], index=['A', 'B'])
    mock_held_status.return_value = held_status
    response = client.get('/compare/spread/summary?show_sold=true')
    assert response.status_code == 200
    assert b'Spread' in response.data or b'ISIN' in response.data

@patch('views.generic_comparison_views.load_generic_comparison_data')
@patch('views.generic_comparison_views.calculate_generic_comparison_stats')
@patch('views.generic_comparison_views.get_holdings_for_security')
def test_comparison_details_success(mock_holdings, mock_calc_stats, mock_load_data, client):
    from views.generic_comparison_views import COMPARISON_CONFIG
    COMPARISON_CONFIG['spread'] = {'display_name': 'Spread', 'file1': 'f1.csv', 'file2': 'f2.csv', 'value_label': 'Spread'}
    merged_data = pd.DataFrame({'ISIN': ['A'], 'Value_Orig': [1], 'Value_New': [2], 'Date': [pd.Timestamp('2024-01-01')]})
    static_data = pd.DataFrame({'ISIN': ['A'], 'StaticCol': ['X']})
    mock_load_data.return_value = (merged_data, static_data, [], 'ISIN')
    stats_df = pd.DataFrame({'ISIN': ['A'], 'Level_Correlation': [0.9], 'StaticCol': ['X']})
    mock_calc_stats.return_value = stats_df
    mock_holdings.return_value = ({'FUND1': [True]}, ['2024-01-01'], None)
    response = client.get('/compare/spread/details/A')
    assert response.status_code == 200
    assert b'A' in response.data or b'chart_data' in response.data

@patch('views.generic_comparison_views.load_generic_comparison_data')
def test_comparison_details_invalid_type(mock_load_data, client):
    response = client.get('/compare/invalidtype/details/A')
    assert response.status_code == 404

@patch('views.generic_comparison_views.load_generic_comparison_data')
def test_comparison_details_no_data(mock_load_data, client):
    from views.generic_comparison_views import COMPARISON_CONFIG
    COMPARISON_CONFIG['spread'] = {'display_name': 'Spread', 'file1': 'f1.csv', 'file2': 'f2.csv'}
    mock_load_data.return_value = (pd.DataFrame(), pd.DataFrame(), [], 'ISIN')
    response = client.get('/compare/spread/details/A')
    assert response.status_code == 200
    assert b'not found' in response.data or b'Error' in response.data 