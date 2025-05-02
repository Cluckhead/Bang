# Purpose: Pytest fixtures shared across view tests.

import pytest
import os
from flask import Flask
import tempfile
import shutil
import pandas as pd
from datetime import datetime
import sys

# Add project root to sys.path if necessary, depending on test runner setup
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import all necessary blueprints
from views.main_views import main_bp
from views.metric_views import metric_bp
from views.fund_views import fund_bp
from views.watchlist_views import watchlist_bp
from views.maxmin_views import maxmin_bp
from views.security_views import security_bp
from views.api_views import api_bp
from views.staleness_views import staleness_bp
from views.issue_views import issue_bp
from views.exclusion_views import exclusion_bp
from views.weight_views import weight_bp
from views.curve_views import curve_bp
from views.generic_comparison_views import generic_comparison_bp
from views.attribution_views import attribution_bp

# --- Fixtures ---

@pytest.fixture(scope="function")
def app():
    """Creates and configures a new app instance for each test function."""
    app = Flask(__name__, instance_relative_config=True)

    # --- Configuration ---
    # Use temporary directory for data to isolate tests
    temp_data_dir = tempfile.mkdtemp()
    # Ensure the 'instance' directory exists for logging if Flask expects it
    instance_path = os.path.join(temp_data_dir, 'instance')
    os.makedirs(instance_path, exist_ok=True)

    # Set essential config values for testing
    app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test_secret_key", # Needed for session/flash
        "WTF_CSRF_ENABLED": False,
        "DATA_FOLDER": temp_data_dir, # Point to temp data folder
        "INSTANCE_PATH": instance_path, # Point to temp instance folder
        "PROPAGATE_EXCEPTIONS": True, # Show exceptions during tests
        "SERVER_NAME": "localhost.test" # Helps url_for outside request context if needed
    })

    # Create dummy files within the temp data directory if needed by views
    # Example: Create an empty users file if load_users requires it
    users_file = os.path.join(temp_data_dir, "users.csv")
    pd.DataFrame(columns=['Username']).to_csv(users_file, index=False)
    # Example: Create an empty watchlist file
    watchlist_file = os.path.join(temp_data_dir, "watchlist.csv")
    pd.DataFrame(columns=[
        "ISIN", "Security Name", "Reason", "DateAdded", "AddedBy",
        "LastChecked", "Status", "ClearedBy", "ClearedDate", "ClearReason"
    ]).to_csv(watchlist_file, index=False)
    # Example: Create an empty securities file
    securities_file = os.path.join(temp_data_dir, "securities.csv")
    pd.DataFrame(columns=["ISIN", "Security Name", "Ticker", "Security Sub Type"]).to_csv(securities_file, index=False)

    # --- Register Blueprints ---
    # Register ALL blueprints used in base.html sidebar or templates extended by views
    app.register_blueprint(main_bp)
    app.register_blueprint(metric_bp, url_prefix="/metric")
    app.register_blueprint(security_bp, url_prefix="/security")
    app.register_blueprint(fund_bp, url_prefix="/fund")
    app.register_blueprint(weight_bp, url_prefix="/weights")
    app.register_blueprint(curve_bp)
    app.register_blueprint(attribution_bp, url_prefix="/attribution")
    app.register_blueprint(generic_comparison_bp, url_prefix="/compare")
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(maxmin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(staleness_bp)
    app.register_blueprint(issue_bp)
    app.register_blueprint(exclusion_bp)

    # --- App Context ---
    # Yield the app within its context
    with app.app_context():
        yield app

    # --- Cleanup ---
    # Remove the temporary directory after the test runs
    shutil.rmtree(temp_data_dir)

@pytest.fixture(scope="function")
def client(app):
    """Provides a Flask test client derived from the app fixture."""
    return app.test_client()

@pytest.fixture(scope="function")
def mock_data_folder(app):
    """Provides the path to the temporary data folder used by the app fixture."""
    return app.config['DATA_FOLDER']

# Define mock data for reuse in tests
MOCK_USERS = ['UserA', 'UserB', 'TestUser']
MOCK_SECURITIES = [
    {'ISIN': 'US123', 'Security Name': 'Test Sec A', 'Ticker': 'TSA', 'Security Sub Type': 'Corp'},
    {'ISIN': 'DE000TEST001', 'Security Name': 'Test Sec B', 'Ticker': 'TSB', 'Security Sub Type': 'Govt'},
    {'ISIN': 'GB123', 'Security Name': 'Test Sec C', 'Ticker': None, 'Security Sub Type': 'Agency'}
]

# You can add more shared fixtures or helper functions here if needed
# Example: Fixture to create a pre-populated watchlist file in the temp dir
@pytest.fixture
def populated_watchlist(mock_data_folder):
    watchlist_path = os.path.join(mock_data_folder, 'watchlist.csv')
    data = [
        {'ISIN': 'US123', 'Security Name': 'Test Sec A', 'Reason': 'Initial', 'DateAdded': datetime(2023, 1, 1).strftime('%Y-%m-%d %H:%M:%S'), 'AddedBy': 'UserA', 'LastChecked': None, 'Status': 'Active', 'ClearedBy': None, 'ClearedDate': None, 'ClearReason': None},
        {'ISIN': 'DE000TEST001', 'Security Name': 'Test Sec B', 'Reason': 'Cleared Example', 'DateAdded': datetime(2023, 1, 2).strftime('%Y-%m-%d %H:%M:%S'), 'AddedBy': 'UserB', 'LastChecked': datetime(2023, 1, 10).strftime('%Y-%m-%d %H:%M:%S'), 'Status': 'Cleared', 'ClearedBy': 'UserA', 'ClearedDate': datetime(2023, 1, 15).strftime('%Y-%m-%d %H:%M:%S'), 'ClearReason': 'Resolved'},
    ]
    df = pd.DataFrame(data)
    df.to_csv(watchlist_path, index=False)
    return watchlist_path
