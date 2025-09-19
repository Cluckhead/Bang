# Purpose: Smoke-tests for Flask app factory and core blueprint registration.

from flask import Flask
from app import create_app


def test_create_app_blueprints_expanded():
    app = create_app()
    assert isinstance(app, Flask)
    # Check a representative subset of core blueprints
    expected_bps = {
        "main",
        "metric",
        "security",
        "fund",
        "api_bp",
        "generic_comparison_bp",
        "staleness_bp",
        "maxmin_bp",
        "ticket_bp",
        "settings_bp",
        "bond_calc_bp",
    }
    app_bps = set(app.blueprints.keys())
    missing = expected_bps - app_bps
    assert not missing, f"Missing expected blueprints: {missing}"


def test_create_app_hello_route():
    app = create_app()
    client = app.test_client()
    resp = client.get("/hello")
    assert resp.status_code == 200
    assert b"Hello, World!" in resp.data
