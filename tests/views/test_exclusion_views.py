# Purpose: Unit tests for exclusion_views.py, covering GET /exclusions and POST /exclusions/add routes, including testing file loading, adding exclusions, handling missing files, and errors.

import pytest
import pandas as pd
from flask import url_for, get_flashed_messages
from unittest.mock import patch, mock_open
from pathlib import Path # Import Path
import os

# Sample Data
SAMPLE_EXCLUSIONS_DF = pd.DataFrame({
    'ISIN': ['XS123', 'XS456'],
    'Reason': ['Manual', 'Sanctions'],
    'Timestamp': [pd.Timestamp('2023-01-01'), pd.Timestamp('2023-01-05')]
})

# Add fixture to manage data folder per test using tmp_path
@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER and EXCLUSIONS_FILE config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    exclusions_file_path = data_folder / 'Exclusions.csv'
    # Set both DATA_FOLDER (if used by view) and EXCLUSIONS_FILE config vars
    monkeypatch.setitem(client.application.config, 'DATA_FOLDER', str(data_folder))
    monkeypatch.setitem(client.application.config, 'EXCLUSIONS_FILE', str(exclusions_file_path))

    # Patch os.path.exists to check actual existence within tmp_path
    original_exists = os.path.exists
    def mock_exists(path):
        try:
            path_obj = Path(path).resolve()
            # Check against the specific exclusions file path or the data folder
            exclusions_file_resolved = exclusions_file_path.resolve()
            data_folder_resolved = data_folder.resolve()
            if path_obj == exclusions_file_resolved or path_obj.is_relative_to(data_folder_resolved):
                return path_obj.exists()
        except (TypeError, ValueError, Exception):
            pass
        return original_exists(path)

    # Patch os path exists where it might be used
    with patch('views.exclusion_views.os.path.exists', side_effect=mock_exists):
        yield data_folder, exclusions_file_path # Provide paths to tests/fixtures

# Updated mock fixture
@pytest.fixture
def mock_exclusion_logic(mocker, setup_data_folder):
    """Fixture to mock exclusion data loading and file operations using temp paths."""
    data_folder, exclusions_file_path = setup_data_folder

    # Mock load_exclusions - assumes it takes the file path as argument
    # If it reads from config, this mock might need adjustment or removal
    mock_load = mocker.patch('views.exclusion_views.load_exclusions', return_value=SAMPLE_EXCLUSIONS_DF.copy())

    # Mock builtins.open for the specific exclusions file path
    mock_open_context = mock_open()
    mocker.patch('builtins.open', mock_open_context)

    # Return the mocks needed by tests
    return mock_load, mock_open_context, exclusions_file_path

# --- GET /exclusions --- #

def test_exclusions_page_success(client, mock_exclusion_logic, setup_data_folder):
    """Test the exclusions_page route (GET) for successful loading."""
    mock_load, _, exclusions_file_path = mock_exclusion_logic
    # Create the dummy file so os.path.exists (patched by setup_data_folder) returns True
    exclusions_file_path.touch()

    response = client.get(url_for('exclusion_bp.exclusions_page')) # Use blueprint name

    assert response.status_code == 200
    assert b'Manage Exclusions' in response.data
    assert b'Current Exclusions' in response.data
    assert b'XS123' in response.data # Check data rendering
    assert b'Add New Exclusion' in response.data

    # Verify load_exclusions was called, potentially with the path from config
    # The exact call depends on how load_exclusions gets the path (config vs argument)
    # Assuming it reads from config['EXCLUSIONS_FILE'] set by setup_data_folder:
    mock_load.assert_called_once()
    # If it takes path as argument:
    # mock_load.assert_called_once_with(str(exclusions_file_path))

def test_exclusions_page_no_file(client, mock_exclusion_logic):
    """Test exclusions_page (GET) when the exclusions file does not exist."""
    mock_load, _, exclusions_file_path = mock_exclusion_logic
    # Do NOT create the file, so os.path.exists returns False

    # Ensure load_exclusions returns an empty DataFrame when file doesn't exist
    # This might happen internally in load_exclusions or needs explicit mocking
    mock_load.return_value = pd.DataFrame(columns=['ISIN', 'Reason', 'Timestamp'])

    response = client.get(url_for('exclusion_bp.exclusions_page')) # Use blueprint name

    assert response.status_code == 200
    assert b'Manage Exclusions' in response.data
    assert b'No exclusions found' in response.data
    assert b'Add New Exclusion' in response.data

    # load_exclusions might still be called, but should handle the non-existent file
    mock_load.assert_called_once()

def test_exclusions_page_load_error(client, mock_exclusion_logic, setup_data_folder):
    """Test exclusions_page (GET) when load_exclusions raises an error."""
    mock_load, _, exclusions_file_path = mock_exclusion_logic
    exclusions_file_path.touch() # File needs to exist for load to be attempted
    mock_load.side_effect = pd.errors.EmptyDataError("Mock load error")

    response = client.get(url_for('exclusion_bp.exclusions_page'), follow_redirects=True) # Use blueprint name

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    assert any('Error loading exclusions file' in msg[1] for msg in messages)
    assert b'Could not load exclusions' in response.data

    mock_load.assert_called_once()

# --- POST /exclusions/add --- #

def test_add_exclusion_success(client, mock_exclusion_logic):
    """Test the add_exclusion route (POST) for successful addition."""
    mock_load, mock_open_context, exclusions_file_path = mock_exclusion_logic
    # Assume the file exists or will be created by the append operation

    exclusion_data = {
        'isin': 'DE789',
        'reason': 'Test Reason'
    }

    response = client.post(url_for('exclusion_bp.add_exclusion'), data=exclusion_data, follow_redirects=True) # Use blueprint name

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any(f'Exclusion for {exclusion_data["isin"]} added.' in msg[1] for msg in messages)
    # assert f'Exclusion for {exclusion_data["isin"]} added.'.encode() in response.data # Check rendered page if needed

    # Check that open was called correctly with the temp path
    mock_open_context.assert_called_once_with(str(exclusions_file_path), 'a', newline='')
    handle = mock_open_context()
    written_data = "".join(call[0][0] for call in handle.write.call_args_list)
    assert exclusion_data['isin'] in written_data
    assert exclusion_data['reason'] in written_data

def test_add_exclusion_missing_data(client, mock_exclusion_logic):
    """Test add_exclusion (POST) when form data is missing."""
    mock_load, mock_open_context, _ = mock_exclusion_logic
    exclusion_data = {
        'isin': 'DE789' # Missing reason
    }

    response = client.post(url_for('exclusion_bp.add_exclusion'), data=exclusion_data, follow_redirects=True) # Use blueprint name

    assert response.status_code == 200 # Should redisplay form with error
    messages = get_flashed_messages(with_categories=True)
    assert any('ISIN and Reason are required.' in msg[1] for msg in messages)
    # assert b'ISIN and Reason are required.' in response.data # Check rendered page

    mock_open_context.assert_not_called() # Should not attempt to write

def test_add_exclusion_write_error(client, mock_exclusion_logic):
    """Test add_exclusion (POST) when writing to the file fails."""
    mock_load, mock_open_context, exclusions_file_path = mock_exclusion_logic
    # Simulate IOError when open is called
    mock_open_context.side_effect = IOError("Mock write error")

    exclusion_data = {
        'isin': 'DE789',
        'reason': 'Test Reason'
    }

    response = client.post(url_for('exclusion_bp.add_exclusion'), data=exclusion_data, follow_redirects=True) # Use blueprint name

    assert response.status_code == 200 # Redisplays form
    messages = get_flashed_messages(with_categories=True)
    assert any('Error saving exclusion' in msg[1] for msg in messages)
    # assert b'Error saving exclusion' in response.data # Check rendered page

    # Check open was called (and raised error)
    mock_open_context.assert_called_once_with(str(exclusions_file_path), 'a', newline='') 