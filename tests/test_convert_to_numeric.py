# Purpose: Test convert_to_numeric_robustly for correct numeric conversion and NaN coercion.

import numpy as np
import pandas as pd
from data_utils import convert_to_numeric_robustly, replace_zeros_with_nan


def test_convert_to_numeric_basic(caplog):
    """Converts strings 1.2, bad, None into numeric with NaN and logs coerced count."""
    series = pd.Series(["1.2", "bad", None])

    result = convert_to_numeric_robustly(series)

    # The first value should convert to 1.2
    assert result.iloc[0] == 1.2
    # Second should be NaN due to failed conversion
    assert np.isnan(result.iloc[1])
    # Third (None) should remain NaN
    assert np.isnan(result.iloc[2])
    # dtype should be float (numeric)
    assert pd.api.types.is_float_dtype(result)

    # Ensure a warning about coerced values was logged (bad string)
    coerced_msgs = [
        rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"
    ]
    assert any("could not be converted" in msg for msg in coerced_msgs)


def test_convert_to_numeric_with_zeros_replaced(caplog):
    """Test that zeros are replaced with NaN by default."""
    series = pd.Series(["1.2", "0", "3.5", "0.0"])

    result = convert_to_numeric_robustly(series)

    # The first value should convert to 1.2
    assert result.iloc[0] == 1.2
    # Second should be NaN (zero replaced)
    assert np.isnan(result.iloc[1])
    # Third should convert to 3.5
    assert result.iloc[2] == 3.5
    # Fourth should be NaN (zero replaced)
    assert np.isnan(result.iloc[3])
    # dtype should be float (numeric)
    assert pd.api.types.is_float_dtype(result)
    
    # Verify that we have the expected number of NaN values (2 zeros + 0 original NaNs = 2 NaNs)
    assert result.isna().sum() == 2


def test_convert_to_numeric_keep_zeros(caplog):
    """Test that zeros can be kept when replace_zeros=False."""
    series = pd.Series(["1.2", "0", "3.5", "0.0"])

    result = convert_to_numeric_robustly(series, replace_zeros=False)

    # The first value should convert to 1.2
    assert result.iloc[0] == 1.2
    # Second should be 0 (not replaced)
    assert result.iloc[1] == 0.0
    # Third should convert to 3.5
    assert result.iloc[2] == 3.5
    # Fourth should be 0 (not replaced)
    assert result.iloc[3] == 0.0
    # dtype should be float (numeric)
    assert pd.api.types.is_float_dtype(result)


def test_replace_zeros_with_nan():
    """Test the replace_zeros_with_nan function directly."""
    series = pd.Series([1.2, 0, 3.5, 0.0, np.nan])

    result = replace_zeros_with_nan(series)

    # First value unchanged
    assert result.iloc[0] == 1.2
    # Second value (0) should be NaN
    assert np.isnan(result.iloc[1])
    # Third value unchanged
    assert result.iloc[2] == 3.5
    # Fourth value (0.0) should be NaN
    assert np.isnan(result.iloc[3])
    # Fifth value (already NaN) should remain NaN
    assert np.isnan(result.iloc[4])


def test_replace_zeros_with_nan_non_numeric():
    """Test that replace_zeros_with_nan handles non-numeric series gracefully."""
    series = pd.Series(["a", "b", "c"])

    result = replace_zeros_with_nan(series)

    # Should return unchanged for non-numeric series
    assert result.equals(series)
