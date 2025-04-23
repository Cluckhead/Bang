# Purpose: Contains tests for the attribution views blueprint (app/views/attribution_views.py).
import pytest
import pandas as pd
import numpy as np
from flask import url_for, get_flashed_messages
import json

# Sample Data
SAMPLE_METRIC_NAME = 'test_metric'
SAMPLE_DATA = pd.DataFrame({
    'Fund A': [1, 2, 3],
    'Fund B': [4, 5, 6]
}, index=pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03']))
SAMPLE_METRICS_LATEST = pd.Series({'Fund A': 3, 'Fund B': 6}, name='Latest')
SAMPLE_METRICS_SUMMARY = pd.DataFrame({
    'Mean': [2, 5],
    'Std Dev': [1, 1]
}, index=['Fund A', 'Fund B'])
SAMPLE_RESIDUAL_STATS = pd.DataFrame({
    'Mean': [0.1, -0.1],
    'Std Dev': [0.05, 0.05]
}, index=['Fund A', 'Fund B'])
SAMPLE_CHART_DATA = {'trace1': {'x': [1], 'y': [2]}}

@pytest.fixture
def mock_attribution_logic(mocker):
    """Fixture to mock attribution data loading and processing functions."""
    mocker.patch('app.views.attribution_views.get_data_folder_path')
    mock_exists = mocker.patch('app.views.attribution_views.os.path.exists', return_value=True)
    mock_load_data = mocker.patch('app.views.attribution_views.load_and_process_data', return_value=SAMPLE_DATA.copy())
    mock_calc_metrics = mocker.patch(
        'app.views.attribution_views.calculate_latest_metrics',
        return_value=(SAMPLE_METRICS_LATEST.copy(), SAMPLE_METRICS_SUMMARY.copy())
    )
    mock_calc_residual = mocker.patch('app.views.attribution_views.calc_residual', return_value=SAMPLE_RESIDUAL_STATS.copy())
    mock_norm = mocker.patch('app.views.attribution_views.norm', return_value=SAMPLE_DATA.copy() * 0.1) # Mock normalized data

    return mock_exists, mock_load_data, mock_calc_metrics, mock_calc_residual, mock_norm

def test_attribution_page_success(client, mock_attribution_logic):
    """Test the attribution_page route for successful loading."""
    mock_exists, mock_load_data, mock_calc_metrics, mock_calc_residual, mock_norm = mock_attribution_logic

    response = client.get(url_for('attribution_views.attribution_page'))

    assert response.status_code == 200
    assert b'Attribution Analysis' in response.data
    assert b'Latest Values' in response.data
    assert b'Residual Statistics' in response.data
    assert b'Fund A' in response.data
    assert b'plotly-graph-div' in response.data

    mock_exists.assert_called()
    mock_load_data.assert_called()
    mock_calc_metrics.assert_called()
    mock_calc_residual.assert_called()
    mock_norm.assert_called()

def test_attribution_page_no_data(client, mock_attribution_logic):
    """Test attribution_page when underlying data files are missing."""
    mock_exists, mock_load_data, *_ = mock_attribution_logic
    mock_exists.return_value = False # Simulate a primary file missing
    mock_load_data.side_effect = FileNotFoundError("Mock data file not found")

    response = client.get(url_for('attribution_views.attribution_page'), follow_redirects=True)

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any('Error loading attribution data' in msg[1] for msg in messages) or \
               any('file not found' in msg[1] for msg in messages)
    else:
        assert b'Error loading attribution data' in response.data or b'data file is missing' in response.data

    mock_exists.assert_called()
    mock_load_data.assert_called()
    # Other mocks should not be called if loading fails early
    assert _.mock_calc_metrics.call_count == 0
    assert _.mock_calc_residual.call_count == 0
    assert _.mock_norm.call_count == 0

def test_attribution_page_processing_error(client, mock_attribution_logic):
    """Test attribution_page when a processing function raises an error."""
    mock_exists, mock_load_data, mock_calc_metrics, mock_calc_residual, mock_norm = mock_attribution_logic
    mock_calc_residual.side_effect = ValueError("Mock processing error in residual calc")

    response = client.get(url_for('attribution_views.attribution_page'))

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any('Error calculating residuals' in msg[1] for msg in messages)
    else:
        assert b'Error calculating residuals' in response.data

    mock_exists.assert_called()
    mock_load_data.assert_called()
    mock_calc_metrics.assert_called()
    mock_calc_residual.assert_called_once() # Called but raised error
    mock_norm.assert_not_called() # Should not be called if residual calc fails 