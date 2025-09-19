# Purpose: Test the parse_dates_robustly function for handling mixed date formats and invalid inputs.

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from core.data_utils import parse_dates_robustly


def test_parse_dates_robustly_mixed_formats():
    """Ensure parse_dates_robustly correctly parses multiple date formats and flags invalid ones."""
    # Prepare a Series with 3 valid date strings in different formats and 1 invalid string
    date_strings = pd.Series(
        [
            "2024-06-01",  # YYYY-MM-DD
            "01/07/2024",  # DD/MM/YYYY
            "2024-08-01T12:34:56",  # ISO 8601
            "not a date",  # Invalid
        ]
    )

    parsed = parse_dates_robustly(date_strings)

    # Assertions
    assert parsed.notna().sum() == 3, "Expected three successfully parsed dates."
    assert parsed.isna().sum() == 1, "Expected one NaT for the invalid date string."
    assert is_datetime64_any_dtype(
        parsed
    ), "Parsed Series should have datetime64 dtype."
