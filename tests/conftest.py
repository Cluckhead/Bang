# Purpose: Provides pytest fixtures for the Flask app and test client for use in tests.

import pytest
import os
from app import create_app  # Import the application factory


@pytest.fixture(scope="module")
def test_app():
    """Provides a Flask application context for the test session."""
    app = create_app()  # Use the factory to create a new app instance
    # Ensure the template folder path is correct relative to the app root
    template_dir = os.path.abspath(os.path.join(app.root_path, "templates"))
    app.template_folder = template_dir
    # Update other necessary testing configurations
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,  # Often disabled for testing forms
            "SECRET_KEY": "test",  # Needed for session, flash messages
            "SERVER_NAME": "localhost.test",  # Helps url_for work correctly outside request context
        }
    )

    with app.app_context():
        yield app


@pytest.fixture(scope="function")  # Changed scope to function for isolation
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
