# Purpose: Smoke-test for app.create_app blueprint registration.

from flask import Flask
from app import create_app


def test_create_app_blueprints():
    app = create_app()
    assert isinstance(app, Flask)
    # Expected blueprint names
    expected_bps = {"metric", "staleness_bp"}
    assert expected_bps.issubset(set(app.blueprints.keys()))
