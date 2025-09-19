# Purpose: Smoke test to import weight blueprint and name.

from views.weight_views import weight_bp


def test_weight_blueprint_name():
    assert weight_bp.name == "weight"

