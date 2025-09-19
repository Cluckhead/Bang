# Purpose: Unit test for utils._is_date_like validating date header detection.

import pytest
from core.utils import _is_date_like


@pytest.mark.parametrize(
    "col,expected",
    [
        ("2025-05-01", True),
        ("01/05/2025", True),
        ("2025-05-01T12:00:00", True),
        ("Spread", False),
        ("RandomCol", False),
    ],
)
def test_is_date_like(col, expected):
    assert _is_date_like(col) == expected
