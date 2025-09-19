# Purpose: Smoke test to ensure NAV_MENU structure is importable and non-empty.

from core.navigation_config import NAV_MENU


def test_nav_menu_non_empty():
    assert isinstance(NAV_MENU, list) and len(NAV_MENU) > 0

