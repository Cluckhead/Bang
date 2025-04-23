# Purpose: Contains tests for the issue views blueprint (app/views/issue_views.py).
import pytest
import pandas as pd
from flask import url_for, get_flashed_messages
from app.processing.issue_processing import ISSUES_FILE

# Sample Data
SAMPLE_ISSUES_DF = pd.DataFrame({
    'ID': ['issue_1', 'issue_2'],
    'Timestamp': [pd.Timestamp('2023-01-01'), pd.Timestamp('2023-01-05')],
    'Metric': ['MetricA', 'MetricB'],
    'Security': ['ISIN123', 'ISIN456'],
    'Description': ['Desc A', 'Desc B'],
    'Status': ['Open', 'Open']
})

@pytest.fixture
def mock_issue_logic(mocker):
    """Fixture to mock issue loading and modification functions."""
    mock_get_path = mocker.patch('app.views.issue_views.get_data_folder_path', return_value='/fake/data')
    mock_exists = mocker.patch('app.views.issue_views.os.path.exists', return_value=True)
    mock_load = mocker.patch('app.views.issue_views.load_issues', return_value=SAMPLE_ISSUES_DF.copy())
    mock_add = mocker.patch('app.views.issue_views.add_issue', return_value=True)
    mock_close = mocker.patch('app.views.issue_views.close_issue', return_value=True)
    return mock_get_path, mock_exists, mock_load, mock_add, mock_close

# --- GET /issues --- #

def test_issues_page_success(client, mock_issue_logic):
    """Test the issues_page route (GET) for successful loading."""
    mock_get_path, mock_exists, mock_load, _, _ = mock_issue_logic
    issues_path = f'/fake/data/{ISSUES_FILE}'

    response = client.get(url_for('issue_views.issues_page'))

    assert response.status_code == 200
    assert b'Issue Tracker' in response.data
    assert b'Open Issues' in response.data
    assert b'issue_1' in response.data # Check data rendering
    assert b'Add New Issue' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with(issues_path)
    mock_load.assert_called_once_with(issues_path)

def test_issues_page_no_file(client, mock_issue_logic):
    """Test issues_page (GET) when the issues file does not exist."""
    mock_get_path, mock_exists, mock_load, _, _ = mock_issue_logic
    issues_path = f'/fake/data/{ISSUES_FILE}'
    mock_exists.return_value = False # Simulate file not found
    mock_load.return_value = pd.DataFrame(columns=['ID', 'Timestamp', 'Metric', 'Security', 'Description', 'Status'])

    response = client.get(url_for('issue_views.issues_page'))

    assert response.status_code == 200
    assert b'Issue Tracker' in response.data
    assert b'No open issues found' in response.data or b'Open Issues' not in response.data
    assert b'Add New Issue' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with(issues_path)
    mock_load.assert_called_once_with(issues_path)

def test_issues_page_load_error(client, mock_issue_logic):
    """Test issues_page (GET) when load_issues raises an error."""
    mock_get_path, mock_exists, mock_load, _, _ = mock_issue_logic
    issues_path = f'/fake/data/{ISSUES_FILE}'
    mock_load.side_effect = pd.errors.ParserError("Mock load error")

    response = client.get(url_for('issue_views.issues_page'), follow_redirects=True)

    assert response.status_code == 200 # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    assert any('Error loading issues file' in msg[1] for msg in messages)
    assert b'Could not load issues' in response.data

    mock_get_path.assert_called_once()
    mock_exists.assert_called_once_with(issues_path)
    mock_load.assert_called_once_with(issues_path)

# --- POST /issues/add --- #

def test_add_new_issue_success(client, mock_issue_logic):
    """Test the add_new_issue route (POST) for successful addition."""
    mock_get_path, mock_exists, mock_load, mock_add, mock_close = mock_issue_logic
    issue_data = {
        'metric': 'NewMetric',
        'security': 'NewISIN',
        'description': 'New Description'
    }
    issues_path = f'/fake/data/{ISSUES_FILE}'

    response = client.post(url_for('issue_views.add_new_issue'), data=issue_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any('New issue added successfully.' in msg[1] for msg in messages)
    assert b'New issue added successfully.' in response.data

    mock_get_path.assert_called_once()
    mock_add.assert_called_once_with(
        issues_path,
        issue_data['metric'],
        issue_data['security'],
        issue_data['description']
    )
    mock_close.assert_not_called() # Ensure close wasn't called

def test_add_new_issue_missing_data(client, mock_issue_logic):
    """Test add_new_issue (POST) when form data is missing."""
    mock_get_path, _, _, mock_add, _ = mock_issue_logic
    issue_data = {
        'metric': 'NewMetric', # Missing security and description
    }

    response = client.post(url_for('issue_views.add_new_issue'), data=issue_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any('All fields are required.' in msg[1] for msg in messages)
    assert b'All fields are required.' in response.data

    mock_get_path.assert_called_once()
    mock_add.assert_not_called()

def test_add_new_issue_save_error(client, mock_issue_logic):
    """Test add_new_issue (POST) when add_issue returns False or raises error."""
    mock_get_path, _, _, mock_add, _ = mock_issue_logic
    mock_add.return_value = False # Simulate save failure
    issues_path = f'/fake/data/{ISSUES_FILE}'
    issue_data = {
        'metric': 'NewMetric',
        'security': 'NewISIN',
        'description': 'New Description'
    }

    response = client.post(url_for('issue_views.add_new_issue'), data=issue_data, follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any('Failed to add issue.' in msg[1] for msg in messages)
    assert b'Failed to add issue.' in response.data

    mock_get_path.assert_called_once()
    mock_add.assert_called_once_with(
        issues_path,
        issue_data['metric'],
        issue_data['security'],
        issue_data['description']
    )

# --- POST /issues/close/<issue_id> --- #

def test_close_existing_issue_success(client, mock_issue_logic):
    """Test the close_existing_issue route (POST) for successful closure."""
    mock_get_path, _, _, mock_add, mock_close = mock_issue_logic
    issue_id_to_close = 'issue_1'
    issues_path = f'/fake/data/{ISSUES_FILE}'

    response = client.post(url_for('issue_views.close_existing_issue', issue_id=issue_id_to_close), follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any(f'Issue {issue_id_to_close} closed successfully.' in msg[1] for msg in messages)
    assert f'Issue {issue_id_to_close} closed successfully.'.encode() in response.data

    mock_get_path.assert_called_once()
    mock_close.assert_called_once_with(issues_path, issue_id_to_close)
    mock_add.assert_not_called()

def test_close_existing_issue_failure(client, mock_issue_logic):
    """Test close_existing_issue (POST) when close_issue returns False."""
    mock_get_path, _, _, mock_add, mock_close = mock_issue_logic
    mock_close.return_value = False # Simulate failure (e.g., issue not found)
    issue_id_to_close = 'issue_nonexistent'
    issues_path = f'/fake/data/{ISSUES_FILE}'

    response = client.post(url_for('issue_views.close_existing_issue', issue_id=issue_id_to_close), follow_redirects=True)

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any(f'Failed to close issue {issue_id_to_close}.' in msg[1] for msg in messages)
    assert f'Failed to close issue {issue_id_to_close}.'.encode() in response.data

    mock_get_path.assert_called_once()
    mock_close.assert_called_once_with(issues_path, issue_id_to_close)
    mock_add.assert_not_called() 