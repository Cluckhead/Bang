# Purpose: Test convert_to_numeric_robustly for correct numeric conversion and NaN coercion.

import numpy as np
import pandas as pd
from data_utils import convert_to_numeric_robustly


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
    coerced_msgs = [rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("could not be converted" in msg for msg in coerced_msgs) 