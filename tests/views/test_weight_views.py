# Purpose: Contains tests for the weight views blueprint (app/views/weight_views.py).
import pytest
import pandas as pd
from flask import url_for, get_flashed_messages

# Sample Data
SAMPLE_WEIGHTS_DF = pd.DataFrame(
    {
        "ISIN": ["US1", "FR1", "GB1"],
        "Security Name": ["Sec One", "Sec Two", "Sec Three"],
        "Weight": [0.5, 0.3, 0.2],
        "Held": [True, True, False],  # Example 'Held' status
    }
)
LATEST_WEIGHT_DATE = pd.to_datetime("2023-01-01")


@pytest.fixture
def mock_weight_logic(mocker):
    """Fixture to mock weight data loading and processing functions."""
    mocker.patch("app.views.weight_views.get_data_folder_path")
    mock_exists = mocker.patch(
        "app.views.weight_views.os.path.exists", return_value=True
    )
    mock_load_weights = mocker.patch(
        "app.views.weight_views.load_weights_and_held_status",
        return_value=(SAMPLE_WEIGHTS_DF.copy(), LATEST_WEIGHT_DATE),
    )
    return mock_exists, mock_load_weights


def test_weights_page_success(client, mock_weight_logic):
    """Test the weights_page route for successful loading."""
    mock_exists, mock_load_weights = mock_weight_logic

    response = client.get(url_for("weight_views.weights_page"))

    assert response.status_code == 200
    assert b"Portfolio Weights" in response.data
    assert b"Latest Weight Date: 2023-01-01" in response.data
    assert b"US1" in response.data  # Check data rendering
    assert b"Sec One" in response.data
    assert b"Held" in response.data  # Check column rendering

    mock_exists.assert_called_once()
    mock_load_weights.assert_called_once()


def test_weights_page_no_data_file(client, mock_weight_logic):
    """Test weights_page when the weight file does not exist."""
    mock_exists, mock_load_weights = mock_weight_logic
    mock_exists.return_value = False  # Simulate file not found

    response = client.get(url_for("weight_views.weights_page"), follow_redirects=True)

    assert response.status_code == 200  # Handles gracefully
    # Check for flash message or error message in template
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any("Weight file not found" in msg[1] for msg in messages)
    else:
        assert (
            b"Weight file not found" in response.data
            or b"No weight data available" in response.data
        )

    mock_exists.assert_called_once()
    mock_load_weights.assert_not_called()  # Should not attempt load if file missing


def test_weights_page_load_error(client, mock_weight_logic):
    """Test weights_page when load_weights_and_held_status raises an error."""
    mock_exists, mock_load_weights = mock_weight_logic
    mock_load_weights.side_effect = FileNotFoundError("Mock error loading weights")

    response = client.get(url_for("weight_views.weights_page"), follow_redirects=True)

    assert response.status_code == 200  # Handles gracefully
    # Check for flash message or error message in template
    messages = get_flashed_messages(with_categories=True)
    if messages:
        assert any("Error loading weights data" in msg[1] for msg in messages)
    else:
        assert b"Error loading weights data" in response.data

    mock_exists.assert_called_once()
    mock_load_weights.assert_called_once()  # Called, but raised error
