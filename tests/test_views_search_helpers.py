# Purpose: Minimal test for search endpoints helpers import and blueprint existence.

from views.search_views import search_bp


def test_search_blueprint_name():
    assert search_bp.name == "search"

