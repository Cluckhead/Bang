# Purpose: Unit tests for curve_views.py, testing the /curve route for displaying yield curve analysis, including handling missing files and processing errors.

import pytest
import pandas as pd
import json
from flask import url_for, get_flashed_messages
from unittest.mock import patch
from pathlib import Path # Import Path
import os

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
CURVE_FILENAME = 'curves.csv' # Define expected filename

# Add fixture to manage data folder per test using tmp_path
@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    monkeypatch.setitem(client.application.config, 'DATA_FOLDER', str(data_folder))
    curve_file_path = data_folder / CURVE_FILENAME

    # Patch os.path.exists to check actual existence within tmp_path
    original_exists = os.path.exists
    def mock_exists(path):
        try:
            path_obj = Path(path).resolve()
            if path_obj == curve_file_path.resolve() or path_obj.is_relative_to(data_folder.resolve()):
                return path_obj.exists()
        except (TypeError, ValueError, Exception):
            pass
        return original_exists(path)

    # Patch where os.path.exists might be called
    with patch('views.curve_views.os.path.exists', side_effect=mock_exists), \
         patch('curve_processing.os.path.exists', side_effect=mock_exists): # Patch in processing module too
        yield data_folder, curve_file_path # Provide paths

# Updated mock fixture
@pytest.fixture
def mock_curve_logic(mocker, setup_data_folder):
    """Fixture to mock curve data loading and processing functions."""
    data_folder, curve_file_path = setup_data_folder
    # Mock processing functions - assume they are called with the data folder path or use config
    mock_load_curve = mocker.patch('curve_processing.load_curve_data', return_value=SAMPLE_CURVE_DATA.copy())
    mock_get_latest = mocker.patch('curve_processing.get_latest_curve_date', return_value=LATEST_CURVE_DATE)
    mock_check_incons = mocker.patch('curve_processing.check_curve_inconsistencies', return_value=SAMPLE_INCONSISTENCIES.copy())

    # Create the dummy curve file so existence checks pass
    curve_file_path.touch()

    return mock_load_curve, mock_get_latest, mock_check_incons, data_folder

# --- Tests for /curve route --- #

def test_curve_page_success(client, mock_curve_logic):
    """Test the curve_page route for successful loading."""
    mock_load_curve, mock_get_latest, mock_check_incons, data_folder = mock_curve_logic

    response = client.get(url_for('curve_bp.curve_page')) # Use blueprint name

    assert response.status_code == 200
    assert b'Yield Curve Analysis' in response.data
    assert b'Latest Curve Date: 2023-01-02' in response.data
    assert b'Curve Inconsistencies' in response.data
    assert b'Not Monotonic' in response.data # Check inconsistency table
    assert b'plotly-graph-div' in response.data # Check if plot div exists

    mock_load_curve.assert_called_once_with(str(data_folder))
    mock_get_latest.assert_called_once_with(SAMPLE_CURVE_DATA)
    mock_check_incons.assert_called_once_with(SAMPLE_CURVE_DATA)

def test_curve_page_no_data_file(client, mock_curve_logic, setup_data_folder):
    """Test curve_page when the curve data file does not exist."""
    mock_load_curve, mock_get_latest, mock_check_incons, data_folder = mock_curve_logic
    _, curve_file_path = setup_data_folder # Get the expected path

    # Ensure the file does NOT exist
    if curve_file_path.exists():
        curve_file_path.unlink()

    # Make load_curve_data return empty when file missing
    mock_load_curve.return_value = pd.DataFrame()

    response = client.get(url_for('curve_bp.curve_page'), follow_redirects=True) # Use blueprint name

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    assert any('Curve data file not found' in msg[1] for msg in messages)
    assert b'No curve data available' in response.data

    mock_load_curve.assert_called_once_with(str(data_folder))
    mock_get_latest.assert_not_called()
    mock_check_incons.assert_not_called()

def test_curve_page_load_error(client, mock_curve_logic):
    """Test curve_page when load_curve_data raises an error."""
    mock_load_curve, mock_get_latest, mock_check_incons, data_folder = mock_curve_logic
    # File exists (created in fixture), but load raises error
    mock_load_curve.side_effect = Exception("Mock error loading curve data")

    response = client.get(url_for('curve_bp.curve_page'), follow_redirects=True) # Use blueprint name

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    assert any('Error loading curve data' in msg[1] for msg in messages)
    assert b'Could not load curve data' in response.data

    mock_load_curve.assert_called_once_with(str(data_folder))
    mock_get_latest.assert_not_called()
    mock_check_incons.assert_not_called()

def test_curve_page_processing_error(client, mock_curve_logic):
    """Test curve_page when check_curve_inconsistencies raises an error."""
    mock_load_curve, mock_get_latest, mock_check_incons, data_folder = mock_curve_logic
    # Load succeeds, but inconsistency check fails
    mock_check_incons.side_effect = ValueError("Mock error checking inconsistencies")

    response = client.get(url_for('curve_bp.curve_page')) # Use blueprint name

    # The view should still render the chart even if inconsistency check fails
    assert response.status_code == 200
    assert b'Yield Curve Analysis' in response.data
    assert b'plotly-graph-div' in response.data
    # Check for an error message about inconsistencies
    messages = get_flashed_messages(with_categories=True)
    assert any('Error checking curve inconsistencies' in msg[1] for msg in messages)
    assert b'Could not check inconsistencies' in response.data

    mock_load_curve.assert_called_once_with(str(data_folder))
    mock_get_latest.assert_called_once_with(SAMPLE_CURVE_DATA)
    mock_check_incons.assert_called_once_with(SAMPLE_CURVE_DATA) # Called but raised error 