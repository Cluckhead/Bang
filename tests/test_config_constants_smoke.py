# Purpose: Smoke test: ensure key config constants exist and have expected types.

from core import config


def test_config_constants_present():
    assert isinstance(config.COLOR_PALETTE, list) and len(config.COLOR_PALETTE) > 0
    assert isinstance(config.DATE_COLUMN_PATTERNS, list) and len(config.DATE_COLUMN_PATTERNS) > 0
    assert isinstance(config.MAXMIN_THRESHOLDS, dict)

