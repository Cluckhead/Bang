# Purpose: Contains tests for the exclusion views blueprint (app/views/exclusion_views.py).
import pytest
import pandas as pd
from flask import url_for, get_flashed_messages
from unittest.mock import patch, mock_open

# Sample Data
SAMPLE_EXCLUSIONS_DF = pd.DataFrame({
    'ISIN': ['XS123', 'XS456'],
    'Reason': ['Manual', 'Sanctions'],
    'Timestamp': [pd.Timestamp('2023-01-01'), pd.Timestamp('2023-01-05')]
})

@pytest.fixture
def mock_exclusion_logic(mocker):
    """Fixture to mock exclusion data loading and file operations."""
    mock_get_path = mocker.patch('app.views.exclusion_views.get_data_folder_path', return_value='/fake/data/folder')
    mock_exists = mocker.patch('app.views.exclusion_views.os.path.exists', return_value=True)
    mock_load = mocker.patch('app.views.exclusion_views.load_exclusions', return_value=SAMPLE_EXCLUSIONS_DF.copy())
    mock_open_context = mock_open()
    mock_file_write = mocker.patch('builtins.open', mock_open_context)
    return mock_get_path, mock_exists, mock_load, mock_open_context

# --- GET /exclusions --- #

def test_exclusions_page_success(client, mock_exclusion_logic):
    """Test the exclusions_page route (GET) for successful loading."""
    mock_get_path, mock_exists, mock_load, _ = mock_exclusion_logic

    response = client.get(url_for('exclusion_views.exclusions_page'))

    assert response.status_code == 200
    assert b'Manage Exclusions' in response.data
    assert b'Current Exclusions' in response.data
    assert b'XS123' in response.data # Check data rendering
    assert b'Add New Exclusion' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with('/fake/data/folder/Exclusions.csv')
    mock_load.assert_called_once_with('/fake/data/folder/Exclusions.csv')

def test_exclusions_page_no_file(client, mock_exclusion_logic):
    """Test exclusions_page (GET) when the exclusions file does not exist."""
    mock_get_path, mock_exists, mock_load, _ = mock_exclusion_logic
    mock_exists.return_value = False # Simulate file not found
    # Ensure load_exclusions returns an empty DataFrame when file doesn't exist
    mock_load.return_value = pd.DataFrame(columns=['ISIN', 'Reason', 'Timestamp'])

    response = client.get(url_for('exclusion_views.exclusions_page'))

    assert response.status_code == 200
    assert b'Manage Exclusions' in response.data
    assert b'No exclusions found' in response.data or b'Current Exclusions' not in response.data
    assert b'Add New Exclusion' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with('/fake/data/folder/Exclusions.csv')
    mock_load.assert_called_once_with('/fake/data/folder/Exclusions.csv')

def test_exclusions_page_load_error(client, mock_exclusion_logic):
    """Test exclusions_page (GET) when load_exclusions raises an error."""
    mock_get_path, mock_exists, mock_load, _ = mock_exclusion_logic
    mock_load.side_effect = pd.errors.EmptyDataError("Mock load error")

    response = client.get(url_for('exclusion_views.exclusions_page'), follow_redirects=True)

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    assert any('Error loading exclusions file' in msg[1] for msg in messages)
    assert b'Could not load exclusions' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with('/fake/data/folder/Exclusions.csv')
    mock_load.assert_called_once_with('/fake/data/folder/Exclusions.csv')

# --- POST /exclusions/add --- #

def test_add_exclusion_success(client, mock_exclusion_logic):
    """Test the add_exclusion route (POST) for successful addition."""
    mock_get_path, mock_exists, mock_load, mock_open_context = mock_exclusion_logic
    exclusion_data = {
        'isin': 'DE789',
        'reason': 'Test Reason'
    }

    response = client.post(url_for('exclusion_views.add_exclusion'), data=exclusion_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any(f'Exclusion for {exclusion_data["isin"]} added.' in msg[1] for msg in messages)
    assert f'Exclusion for {exclusion_data["isin"]} added.'.encode() in response.data

    mock_get_path.assert_called()
    mock_exists.assert_called_once()
    mock_load.assert_called_once()
    mock_open_context.assert_called_once_with('/fake/data/folder/Exclusions.csv', 'a', newline='')
    # Check if the correct data was written (or attempted to be written)
    handle = mock_open_context()
    # Get the last call to write (assuming CSV writer writes line by line or similar)
    last_write_call = handle.write.call_args_list[-1]
    written_data = last_write_call[0][0] # Get the string that was written
    assert exclusion_data['isin'] in written_data
    assert exclusion_data['reason'] in written_data

def test_add_exclusion_missing_data(client, mock_exclusion_logic):
    """Test add_exclusion (POST) when form data is missing."""
    mock_get_path, mock_exists, mock_load, mock_open_context = mock_exclusion_logic
    exclusion_data = {
        'isin': 'DE789' # Missing reason
    }

    response = client.post(url_for('exclusion_views.add_exclusion'), data=exclusion_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any('ISIN and Reason are required.' in msg[1] for msg in messages)
    assert b'ISIN and Reason are required.' in response.data

    mock_get_path.assert_called()
    mock_exists.assert_called_once()
    mock_load.assert_called_once()
    mock_open_context.assert_not_called() # Should not attempt to write

def test_add_exclusion_write_error(client, mock_exclusion_logic):
    """Test add_exclusion (POST) when writing to the file fails."""
    mock_get_path, mock_exists, mock_load, mock_open_context = mock_exclusion_logic
    mock_open_context.side_effect = IOError("Mock write error")

    exclusion_data = {
        'isin': 'DE789',
        'reason': 'Test Reason'
    }

    response = client.post(url_for('exclusion_views.add_exclusion'), data=exclusion_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any('Error saving exclusion' in msg[1] for msg in messages)
    assert b'Error saving exclusion' in response.data

    mock_get_path.assert_called()
    mock_exists.assert_called_once()
    mock_load.assert_called_once()
    mock_open_context.assert_called_once() # Called but raised error 