# Purpose: Pytest fixtures shared across view tests.

import pytest
import os
from flask import Flask


@pytest.fixture
def app(tmp_path):  # Use function-scoped tmp_path
    """Create and configure a new app instance for each test function."""
    # Use tmp_path directly for function-scoped fixture
    data_folder = tmp_path
    template_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../templates")
    )

    # Check if template folder exists
    if not os.path.isdir(template_dir):
        raise FileNotFoundError(
            f"Template folder not found at expected path: {template_dir}"
        )

    app = Flask(__name__, template_folder=template_dir)
    app.config.from_object("config")  # Load configuration from config.py
    app.config["DATA_FOLDER"] = str(data_folder)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_secret_key"  # Use a more descriptive key
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for easier testing

    # --- Register Blueprints ---
    # Important: Import *inside* the fixture to avoid premature app context issues
    try:
        from views.main_views import main_bp
        from views.metric_views import metric_bp
        from views.generic_comparison_views import generic_comparison_bp
        from views.security_views import security_bp
        from views.weight_views import weight_bp
        from views.curve_views import curve_bp
        from views.attribution_views import attribution_bp
        from views.exclusion_views import exclusion_bp
        from views.issue_views import issue_bp
        from views.api_views import api_bp
        from views.staleness_views import staleness_bp
        from views.fund_views import fund_bp

        app.register_blueprint(main_bp)
        app.register_blueprint(
            metric_bp, url_prefix="/metric"
        )  # Correct prefix based on usage
        app.register_blueprint(security_bp, url_prefix="/security")  # Correct prefix
        app.register_blueprint(weight_bp, url_prefix="/weights")  # Correct prefix
        app.register_blueprint(curve_bp)  # Assuming no prefix needed
        app.register_blueprint(
            attribution_bp, url_prefix="/attribution"
        )  # Correct prefix
        app.register_blueprint(exclusion_bp)  # Assuming no prefix needed
        app.register_blueprint(issue_bp)  # Assuming no prefix needed
        app.register_blueprint(api_bp)  # Assuming no prefix needed
        app.register_blueprint(staleness_bp)  # Assuming no prefix needed
        app.register_blueprint(
            generic_comparison_bp, url_prefix="/compare"
        )  # Correct prefix
        app.register_blueprint(fund_bp, url_prefix="/fund")  # Correct prefix
    except ImportError as e:
        print(f"Error importing or registering blueprint: {e}")
        # Optionally raise the error or handle it if running tests without all modules is expected
        raise e

    # --- Optional: Setup Test Database (if using one) ---
    # Example: If you have a test DB setup
    # with app.app_context():
    #     db.create_all()

    yield app  # Use yield for setup/teardown if needed

    # --- Optional: Teardown Test Database ---
    # Example:
    # with app.app_context():
    #     db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()
