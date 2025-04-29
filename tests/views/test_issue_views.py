# Purpose: Unit tests for issue_views.py, covering GET /issues, POST /issues (add), and POST /issues/close routes. Tests include loading, adding, closing issues, and handling errors.

import pytest
import pandas as pd
from flask import url_for, get_flashed_messages
from unittest.mock import patch
from pathlib import Path  # Import Path
import os

# Define the issues file name directly - This might be better in config
ISSUES_FILENAME = "data_issues.csv"

# Sample Data
SAMPLE_ISSUES_DF = pd.DataFrame(
    {
        "IssueID": ["issue_1", "issue_2"],
        "DateRaised": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-05")],
        "RaisedBy": ["User1", "User2"],
        "FundImpacted": ["FUND1", "FUND2"],
        "DataSource": ["Source1", "Source2"],
        "IssueDate": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-05")],
        "Description": ["Desc A", "Desc B"],
        "JiraLink": ["", ""],
        "Status": ["Open", "Open"],
        "DateClosed": [pd.NaT, pd.NaT],
        "ClosedBy": [None, None],
        "ResolutionComment": [None, None],
    }
)


# Add fixture to manage data folder per test using tmp_path
@pytest.fixture(autouse=True)
def setup_data_folder(client, tmp_path, monkeypatch):
    """Set the DATA_FOLDER config to tmp_path for each test."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    monkeypatch.setitem(client.application.config, "DATA_FOLDER", str(data_folder))
    # Assuming issues file is relative to data_folder
    issues_file_path = data_folder / ISSUES_FILENAME
    # Patch os.path.exists (might be used internally by processing functions)
    original_exists = os.path.exists

    def mock_exists(path):
        try:
            path_obj = Path(path).resolve()
            if path_obj == issues_file_path.resolve() or path_obj.is_relative_to(
                data_folder.resolve()
            ):
                return path_obj.exists()
        except (TypeError, ValueError, Exception):
            pass
        return original_exists(path)

    # Patch where os.path.exists might be called
    with patch("views.issue_views.os.path.exists", side_effect=mock_exists), patch(
        "issue_processing.os.path.exists", side_effect=mock_exists
    ):  # Patch in processing module too
        yield data_folder  # Provide path to tests/fixtures


# Updated mock fixture
@pytest.fixture
def mock_issue_logic(mocker, setup_data_folder):
    """Fixture to mock issue loading and modification functions using temp path."""
    data_folder_path = setup_data_folder  # Get the temp path

    # Mock the functions from issue_processing
    # Ensure they are called with the correct temp data_folder_path
    mock_load_issues = mocker.patch(
        "issue_processing.load_issues", return_value=SAMPLE_ISSUES_DF.copy()
    )
    mock_add_issue = mocker.patch(
        "issue_processing.add_issue", return_value="new_issue_id"
    )
    mock_close_issue = mocker.patch("issue_processing.close_issue", return_value=True)
    mock_load_fund_list = mocker.patch(
        "issue_processing.load_fund_list", return_value=["FUND1", "FUND2"]
    )

    # Mock other functions called by the view
    mock_load_users = mocker.patch(
        "views.issue_views.load_users", return_value=["User1", "User2"]
    )

    return (
        mock_load_issues,
        mock_add_issue,
        mock_close_issue,
        mock_load_fund_list,
        mock_load_users,
        data_folder_path,
    )


# --- GET /issues --- #


def test_issues_page_success(client, mock_issue_logic):
    """Test the issues_page route (GET) for successful loading."""
    mock_load_issues, _, _, mock_load_fund_list, _, data_folder_path = mock_issue_logic

    response = client.get(url_for("issue_bp.issues_page"))  # Use url_for

    assert response.status_code == 200
    assert b"Manage Data Issues" in response.data
    assert b"issue_1" in response.data  # Check sample data rendering

    mock_load_issues.assert_called_once_with(str(data_folder_path))
    mock_load_fund_list.assert_called_once_with(str(data_folder_path))


def test_issues_page_no_file(client, mock_issue_logic):
    """Test issues_page (GET) when the issues file does not exist (load returns empty)."""
    mock_load_issues, _, _, mock_load_fund_list, _, data_folder_path = mock_issue_logic
    mock_load_issues.return_value = pd.DataFrame(columns=SAMPLE_ISSUES_DF.columns)

    response = client.get(url_for("issue_bp.issues_page"))  # Use url_for

    assert response.status_code == 200
    assert b"No open issues found" in response.data

    mock_load_issues.assert_called_once_with(str(data_folder_path))
    mock_load_fund_list.assert_called_once_with(str(data_folder_path))


def test_issues_page_load_error(client, mock_issue_logic, mocker):
    """Test issues_page (GET) when load_issues raises an error."""
    mock_load_issues, _, _, mock_load_fund_list, _, data_folder_path = mock_issue_logic
    mock_load_issues.side_effect = pd.errors.ParserError("Mock load error")
    mock_flash = mocker.patch("views.issue_views.flash")  # Mock flash to check messages

    response = client.get(url_for("issue_bp.issues_page"))  # Use url_for

    # Expect graceful handling (page loads, error flashed)
    assert response.status_code == 200
    mock_flash.assert_called_once()
    assert "Error loading issues file" in mock_flash.call_args[0][0]
    assert b"Could not load issues" in response.data

    mock_load_issues.assert_called_once_with(str(data_folder_path))
    # load_fund_list might still be called depending on view logic
    # mock_load_fund_list.assert_called_once_with(str(data_folder_path))


# --- POST /issues/add --- #


def test_add_new_issue_success(client, mock_issue_logic, mocker):
    """Test adding a new issue through POST."""
    _, mock_add_issue, _, _, _, data_folder_path = mock_issue_logic

    # Mock the DATA_SOURCES constant if needed
    # mocker.patch('views.issue_views.DATA_SOURCES', ['Source1', 'Source2'])

    issue_data = {
        "raised_by": "User1",
        "fund_impacted": "FUND1",
        "data_source": "Source1",
        "issue_date": "2023-01-10",
        "description": "New Description",
        "jira_link": "",
    }

    response = client.post(
        url_for("issue_bp.add_issue"), data=issue_data, follow_redirects=True
    )  # Use url_for

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any("Issue new_issue_id added successfully" in msg[1] for msg in messages)

    # Verify the mock was called with the correct temp path
    mock_add_issue.assert_called_once()
    call_kwargs = mock_add_issue.call_args.kwargs
    assert call_kwargs["raised_by"] == "User1"
    assert call_kwargs["fund_impacted"] == "FUND1"
    assert call_kwargs["data_source"] == "Source1"
    assert call_kwargs["data_folder_path"] == str(data_folder_path)


def test_add_new_issue_missing_data(client, mock_issue_logic):
    """Test add_new_issue (POST) when form data is missing."""
    _, mock_add_issue, _, _, _, _ = mock_issue_logic
    issue_data = {"raised_by": "User1"}  # Missing required fields

    response = client.post(
        url_for("issue_bp.add_issue"), data=issue_data, follow_redirects=True
    )  # Use url_for

    assert response.status_code == 200  # Redisplays form
    messages = get_flashed_messages(with_categories=True)
    assert any(
        "Missing required fields" in msg[1] for msg in messages
    )  # Check for specific error flash

    mock_add_issue.assert_not_called()


def test_add_new_issue_save_error(client, mock_issue_logic):
    """Test add_new_issue (POST) when add_issue returns False/empty."""
    _, mock_add_issue, _, _, _, data_folder_path = mock_issue_logic
    mock_add_issue.return_value = ""  # Simulate save failure

    issue_data = {
        "raised_by": "User1",
        "fund_impacted": "FUND1",
        "data_source": "Source1",
        "issue_date": "2023-01-10",
        "description": "New Description",
        "jira_link": "",
    }

    response = client.post(
        url_for("issue_bp.add_issue"), data=issue_data, follow_redirects=True
    )  # Use url_for

    assert response.status_code == 200  # Redisplays form
    messages = get_flashed_messages(with_categories=True)
    assert any("Error adding issue" in msg[1] for msg in messages)

    mock_add_issue.assert_called_once()  # Still called, but failed


# --- POST /issues/close/<issue_id> --- #


def test_close_existing_issue_success(client, mock_issue_logic):
    """Test closing an existing issue via POST /issues/close/<id>."""
    _, _, mock_close_issue, _, _, data_folder_path = mock_issue_logic
    issue_id_to_close = "issue_1"

    close_data = {
        # Data might be passed via form in request context, check view
        "closed_by": "TestUser",  # Assuming these are needed
        "resolution_comment": "Resolved.",
    }

    response = client.post(
        url_for("issue_bp.close_issue", issue_id=issue_id_to_close),
        data=close_data,
        follow_redirects=True,
    )  # Use url_for

    assert response.status_code == 200
    messages = get_flashed_messages(with_categories=True)
    assert any(
        f"Issue {issue_id_to_close} closed successfully" in msg[1] for msg in messages
    )

    # Verify close_issue mock call with correct path
    mock_close_issue.assert_called_once_with(
        issue_id=issue_id_to_close,
        closed_by="TestUser",
        resolution_comment="Resolved.",
        data_folder_path=str(data_folder_path),
    )


def test_close_existing_issue_failure(client, mock_issue_logic):
    """Test closing an issue when close_issue returns False."""
    _, _, mock_close_issue, _, _, data_folder_path = mock_issue_logic
    mock_close_issue.return_value = False  # Simulate failure
    issue_id_to_close = "issue_not_found"

    close_data = {
        "closed_by": "TestUser",
        "resolution_comment": "Attempted resolution.",
    }

    response = client.post(
        url_for("issue_bp.close_issue", issue_id=issue_id_to_close),
        data=close_data,
        follow_redirects=True,
    )  # Use url_for

    assert response.status_code == 200  # Redirects back
    messages = get_flashed_messages(with_categories=True)
    assert any("Error closing issue" in msg[1] for msg in messages)

    mock_close_issue.assert_called_once_with(
        issue_id=issue_id_to_close,
        closed_by="TestUser",
        resolution_comment="Attempted resolution.",
        data_folder_path=str(data_folder_path),
    )
