# Purpose: Provides pytest fixtures for the Flask app and test client for use in tests.

import pytest
import os
from app import create_app

@pytest.fixture(scope='module')
def app():
    """Fixture to create a Flask app instance for testing."""
    # Ensure the template folder is set correctly relative to the test directory
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    # Create the app instance first
    app_instance = create_app()
    # Update config for testing
    app_instance.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test',
        'TEMPLATES_AUTO_RELOAD': True,
        'TEMPLATE_FOLDER': template_dir, # Override template folder if needed
        # Ensure DATA_FOLDER points to a test-specific location if necessary
        # 'DATA_FOLDER': '/path/to/test/data' 
    })

    yield app_instance

@pytest.fixture(scope='module')
def client(app):
    """Fixture to provide a test client for the Flask app."""
    return app.test_client() 