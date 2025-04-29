# Purpose: Contains tests for the staleness views blueprint (app/views/staleness_views.py).
import pytest
import pandas as pd
from flask import url_for, get_flashed_messages
import plotly.graph_objects as go

# Sample Data
SAMPLE_SUMMARY = pd.DataFrame(
    {
        "Data Type": ["primary", "secondary"],
        "Latest Date": [pd.to_datetime("2023-01-10"), pd.to_datetime("2023-01-05")],
        "Staleness (Days)": [2, 7],
    }
)
SAMPLE_DETAILS = pd.DataFrame(
    {
        "ISIN": ["US1", "FR1"],
        "Security Name": ["Sec One", "Sec Two"],
        "Metric": ["Price", "Yield"],
        "Last Update": [pd.to_datetime("2023-01-08"), pd.to_datetime("2023-01-01")],
        "Staleness (Days)": [4, 11],
    }
)
SAMPLE_PLOT = go.Figure(go.Bar(x=["A"], y=[1]))


@pytest.fixture
def mock_staleness_logic(mocker):
    """Fixture to mock staleness data loading and processing functions."""
    mocker.patch("app.views.staleness_views.get_data_folder_path")
    mock_exists = mocker.patch(
        "app.views.staleness_views.os.path.exists", return_value=True
    )
    mock_load_data = mocker.patch(
        "app.views.staleness_views.load_and_process_data"
    )  # Assuming this is used indirectly
    mock_get_summary = mocker.patch(
        "app.views.staleness_views.get_staleness_summary",
        return_value=SAMPLE_SUMMARY.copy(),
    )
    mock_get_details = mocker.patch(
        "app.views.staleness_views.get_stale_securities_details",
        return_value=SAMPLE_DETAILS.copy(),
    )
    mock_plot = mocker.patch(
        "app.views.staleness_views.create_staleness_plot", return_value=SAMPLE_PLOT
    )
    return mock_exists, mock_get_summary, mock_get_details, mock_plot


def test_staleness_page_success(client, mock_staleness_logic):
    """Test the staleness_page route for successful loading."""
    mock_exists, mock_get_summary, mock_get_details, mock_plot = mock_staleness_logic

    response = client.get(url_for("staleness_views.staleness_page"))

    assert response.status_code == 200
    assert b"Data Staleness Overview" in response.data
    assert b"Staleness Summary" in response.data
    assert b"Stale Securities Details" in response.data
    assert b"primary" in response.data  # From summary table
    assert b"US1" in response.data  # From details table
    assert b"plotly-graph-div" in response.data  # Check if plot div exists

    mock_exists.assert_called()
    mock_get_summary.assert_called_once()
    mock_get_details.assert_called_once()
    mock_plot.assert_called_once()


def test_staleness_page_no_data(client, mock_staleness_logic):
    """Test staleness_page when underlying data files are missing."""
    mock_exists, mock_get_summary, mock_get_details, mock_plot = mock_staleness_logic
    # Simulate file not found for a crucial dependency (e.g., inside get_staleness_summary)
    mock_get_summary.side_effect = FileNotFoundError(
        "Mock file not found for staleness"
    )

    response = client.get(
        url_for("staleness_views.staleness_page"), follow_redirects=True
    )

    assert response.status_code == 200  # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any("Error loading staleness data" in msg[1] for msg in messages) or any(
            "missing" in msg[1] for msg in messages
        )
    else:
        assert (
            b"Error loading staleness data" in response.data
            or b"data file is missing" in response.data
        )

    mock_exists.assert_called()
    mock_get_summary.assert_called_once()  # Called but raised error
    mock_get_details.assert_not_called()  # Should bail out before details
    mock_plot.assert_not_called()  # Should bail out before plot


def test_staleness_page_processing_error(client, mock_staleness_logic):
    """Test staleness_page when a processing function raises an error."""
    mock_exists, mock_get_summary, mock_get_details, mock_plot = mock_staleness_logic
    mock_get_details.side_effect = ValueError("Mock processing error")

    response = client.get(
        url_for("staleness_views.staleness_page"), follow_redirects=True
    )

    assert response.status_code == 200  # Handles gracefully
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any("Error processing staleness details" in msg[1] for msg in messages)
    else:
        assert b"Error processing staleness details" in response.data

    mock_exists.assert_called()
    mock_get_summary.assert_called_once()
    mock_get_details.assert_called_once()  # Called but raised error
    mock_plot.assert_not_called()  # Should bail out before plot
