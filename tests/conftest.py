# Purpose: Provides pytest fixtures for the Flask app and test client for use in tests.

import pytest
import os
from app import create_app

@pytest.fixture(scope='module')
def app():
    """Fixture to create a Flask app instance for testing."""
    # Ensure the template folder is set correctly relative to the test directory
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test',
        'TEMPLATES_AUTO_RELOAD': True,
        'TEMPLATE_FOLDER': template_dir,
    })
    yield app

@pytest.fixture(scope='module')
def client(app):
    """Fixture to provide a test client for the Flask app."""
    return app.test_client() 