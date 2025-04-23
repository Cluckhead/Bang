# Purpose: Contains tests for the curve views blueprint (app/views/curve_views.py).
import pytest
import pandas as pd
import json
from flask import url_for, get_flashed_messages

# Sample Data
SAMPLE_CURVE_DATA = pd.DataFrame({
    '1m': [0.01, 0.011],
    '3m': [0.015, 0.016],
    '1y': [0.02, 0.021]
}, index=pd.to_datetime(['2023-01-01', '2023-01-02']))
LATEST_CURVE_DATE = pd.to_datetime('2023-01-02')
SAMPLE_INCONSISTENCIES = pd.DataFrame({
    'Date': [pd.to_datetime('2023-01-01')],
    'Term': ['3m'],
    'Reason': ['Not Monotonic']
})

@pytest.fixture
def mock_curve_logic(mocker):
    """Fixture to mock curve data loading and processing functions."""
    mocker.patch('app.views.curve_views.get_data_folder_path')
    mock_exists = mocker.patch('app.views.curve_views.os.path.exists', return_value=True)
    mock_load_curve = mocker.patch('app.views.curve_views.load_curve_data', return_value=SAMPLE_CURVE_DATA.copy())
    mock_get_latest = mocker.patch('app.views.curve_views.get_latest_curve_date', return_value=LATEST_CURVE_DATE)
    mock_check_incons = mocker.patch('app.views.curve_views.check_curve_inconsistencies', return_value=SAMPLE_INCONSISTENCIES.copy())
    return mock_exists, mock_load_curve, mock_get_latest, mock_check_incons

def test_curve_page_success(client, mock_curve_logic):
    """Test the curve_page route for successful loading."""
    mock_exists, mock_load_curve, mock_get_latest, mock_check_incons = mock_curve_logic

    response = client.get(url_for('curve_views.curve_page'))

    assert response.status_code == 200
    assert b'Yield Curve Analysis' in response.data
    assert b'Latest Curve Date: 2023-01-02' in response.data
    assert b'Curve Inconsistencies' in response.data
    assert b'Not Monotonic' in response.data # Check inconsistency table
    assert b'plotly-graph-div' in response.data # Check if plot div exists

    mock_exists.assert_called_once()
    mock_load_curve.assert_called_once()
    mock_get_latest.assert_called_once_with(SAMPLE_CURVE_DATA)
    mock_check_incons.assert_called_once_with(SAMPLE_CURVE_DATA)

def test_curve_page_no_data_file(client, mock_curve_logic):
    """Test curve_page when the curve data file does not exist."""
    mock_exists, mock_load_curve, mock_get_latest, mock_check_incons = mock_curve_logic
    mock_exists.return_value = False # Simulate file not found

    response = client.get(url_for('curve_views.curve_page'), follow_redirects=True)

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any('Curve data file not found' in msg[1] for msg in messages)
    else:
        assert b'Curve data file not found' in response.data or b'No curve data available' in response.data

    mock_exists.assert_called_once()
    mock_load_curve.assert_not_called()
    mock_get_latest.assert_not_called()
    mock_check_incons.assert_not_called()

def test_curve_page_load_error(client, mock_curve_logic):
    """Test curve_page when load_curve_data raises an error."""
    mock_exists, mock_load_curve, mock_get_latest, mock_check_incons = mock_curve_logic
    mock_load_curve.side_effect = FileNotFoundError("Mock error loading curve data")

    response = client.get(url_for('curve_views.curve_page'), follow_redirects=True)

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any('Error loading curve data' in msg[1] for msg in messages)
    else:
        assert b'Error loading curve data' in response.data

    mock_exists.assert_called_once()
    mock_load_curve.assert_called_once() # Called but raised error
    mock_get_latest.assert_not_called()
    mock_check_incons.assert_not_called()

def test_curve_page_processing_error(client, mock_curve_logic):
    """Test curve_page when check_curve_inconsistencies raises an error."""
    mock_exists, mock_load_curve, mock_get_latest, mock_check_incons = mock_curve_logic
    mock_check_incons.side_effect = ValueError("Mock error checking inconsistencies")

    response = client.get(url_for('curve_views.curve_page'))

    # The view should still render the chart even if inconsistency check fails
    assert response.status_code == 200
    assert b'Yield Curve Analysis' in response.data
    assert b'plotly-graph-div' in response.data
    # Check for an error message about inconsistencies
    assert b'Error checking curve inconsistencies' in response.data

    mock_exists.assert_called_once()
    mock_load_curve.assert_called_once()
    mock_get_latest.assert_called_once_with(SAMPLE_CURVE_DATA)
    mock_check_incons.assert_called_once_with(SAMPLE_CURVE_DATA) # Called but raised error

    mock_get_latest.assert_called_once_with(SAMPLE_CURVE_DATA)
    mock_check_incons.assert_called_once_with(SAMPLE_CURVE_DATA) # Called but raised error 