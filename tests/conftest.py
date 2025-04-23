# Purpose: Provides pytest fixtures for the Flask app and test client for use in tests.

import pytest
import os
from app import app as flask_app  # Assuming your Flask app instance is named 'app' in 'app.py'

@pytest.fixture(scope="module")
def test_app():
    """Provides a Flask application context for the test session."""
    # Configure the app for testing here if needed
    # Example: flask_app.config.update({'TESTING': True, 'SECRET_KEY': 'test'})
    # Ensure the template folder path is correct relative to the app root
    template_dir = os.path.abspath(os.path.join(flask_app.root_path, 'templates'))
    flask_app.template_folder = template_dir
    # Update other necessary testing configurations
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False, # Often disabled for testing forms
        'SECRET_KEY': 'test', # Needed for session, flash messages
        'SERVER_NAME': 'localhost.test' # Helps url_for work correctly outside request context
    })

    with flask_app.app_context():
        yield flask_app

@pytest.fixture(scope="function") # Changed scope to function for isolation
def client(test_app):
    """Provides a Flask test client for each test function."""
    return test_app.test_client()

# Removed duplicate app and client fixtures below
# @pytest.fixture(scope='module')
# def app():
#     """Fixture to create a Flask app instance for testing."""
#     # ... (removed duplicate logic) ...
#     yield app_instance
#
# @pytest.fixture(scope='module')
# def client(app):
#     """Fixture to provide a test client for the Flask app."""
#     return app.test_client() 