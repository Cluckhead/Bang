# Purpose: Test the _term_to_days helper in curve_processing for correct conversions and edge-case handling.

import pytest
from curve_processing import _term_to_days


@pytest.mark.parametrize(
    "input_term, expected_days",
    [
        ("7D", 7),  # days
        ("1M", 30),  # months (approx)
        ("2Y", 730),  # years (approx)
        ("0D", None),  # zero interpreted as None
        ("bad", None),  # invalid string returns None
        (123, None),  # non-string input returns None
    ],
)
def test_term_to_days_conversions(input_term, expected_days):
    """Validate that _term_to_days converts term strings to approximate day counts or None."""
    assert _term_to_days(input_term) == expected_days 