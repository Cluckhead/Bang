"""
Placeholder module for validating data retrieved from the API.

This module will contain functions to check the structure, data types,
and potentially the content consistency of the DataFrames returned by the
Rex API before they are saved as CSV files.
"""

import pandas as pd
from typing import Tuple, List


def validate_data(df: pd.DataFrame, filename: str) -> Tuple[bool, List[str]]:
    """
    Validates the structure and types of the DataFrame based on filename conventions.

    This is a placeholder function. Implement specific checks based on the
    expected format for different file types (e.g., 'ts_*.csv', 'sec_*.csv').

    Args:
        df (pd.DataFrame): The DataFrame returned by the API call.
        filename (str): The intended filename for the data (e.g., 'ts_Duration.csv').

    Returns:
        tuple[bool, list[str]]: A tuple containing:
            - bool: True if the data is valid, False otherwise.
            - list[str]: A list of validation error messages, empty if valid.
    """
    errors = []

    if df is None or not isinstance(df, pd.DataFrame):
        errors.append("Invalid input: DataFrame is None or not a pandas DataFrame.")
        return False, errors

    if df.empty:
        # It might be valid for some queries to return no data, but flag it for review.
        errors.append("Warning: DataFrame is empty.")
        # Decide if empty is truly invalid or just a warning.
        # For now, let's consider it potentially valid but issue a warning.
        # return False, errors # Uncomment if empty df is strictly invalid

    # Example checks based on filename conventions:
    if filename.startswith("ts_"):
        # Checks for time-series files
        required_cols = [
            "Date",
            "Code",
        ]  # Assuming these are standard post-processing names
        if not all(col in df.columns for col in required_cols):
            errors.append(
                f"Missing required columns for time-series data: Expected {required_cols}, got {list(df.columns)}"
            )
        # Check if 'Date' column is datetime type (or can be coerced)
        if "Date" in df.columns:
            try:
                pd.to_datetime(df["Date"])
            except Exception as e:
                errors.append(f"'Date' column cannot be parsed as datetime: {e}")
        # Check if value columns (excluding Date, Code, Benchmark if exists) are numeric
        value_cols = [
            col for col in df.columns if col not in ["Date", "Code", "Benchmark"]
        ]
        for col in value_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append(f"Column '{col}' in time-series data is not numeric.")

    elif filename.startswith("sec_"):
        # Checks for security-level files
        # Check for an ID column (e.g., 'ISIN')
        id_cols = [col for col in df.columns if col.upper() in ["ISIN", "SECURITY ID"]]
        if not id_cols:
            errors.append("No ID column found (expected 'ISIN' or 'Security ID').")
        # Check if columns intended as dates are parseable
        date_like_cols = [col for col in df.columns if _is_date_like(col)]
        if not date_like_cols:
            errors.append("No date-like columns found in security-level file.")
        else:
            for col in date_like_cols:
                try:
                    pd.to_datetime(df[col])
                except Exception as e:
                    errors.append(f"Date-like column '{col}' cannot be parsed as datetime: {e}")
        # Check if value columns are numeric (date-like columns should be numeric)
        for col in date_like_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append(f"Date column '{col}' in security-level data is not numeric.")

    elif filename == "FundList.csv":
        # Example: Check required columns for FundList
        required_cols = ["Fund Code", "Total Asset Value USD", "Picked"]
        if not all(col in df.columns for col in required_cols):
            errors.append(
                f"Missing required columns for FundList.csv: Expected {required_cols}, got {list(df.columns)}"
            )

    elif filename.startswith("w_"):
        # Checks for weight files
        id_col = df.columns[0] if len(df.columns) > 0 else None
        if not id_col:
            errors.append("No ID column found in weight file (expected in first column).")
        # All columns after the first are expected to be dates
        date_cols = df.columns[1:]
        if not date_cols.any():
            errors.append("No date columns found in weight file.")
        for col in date_cols:
            try:
                pd.to_datetime(col)
            except Exception as e:
                errors.append(f"Column header '{col}' in weight file is not a valid date: {e}")
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append(f"Weight column '{col}' is not numeric.")

    # --- Add more specific validation rules as needed based on data specs ---

    is_valid = len(errors) == 0
    return is_valid, errors


# Example Usage (can be run manually for testing):
if __name__ == "__main__":
    # Create dummy dataframes for testing validation logic
    print("Testing validation functions...")

    # Test case 1: Valid time-series data
    valid_ts_data = {
        "Date": pd.to_datetime(
            ["2023-01-01", "2023-01-01", "2023-01-02", "2023-01-02"]
        ),
        "Code": ["FUNDA", "FUNDB", "FUNDA", "FUNDB"],
        "Value": [10.1, 20.2, 10.5, 20.8],
        "Benchmark": [10.0, 20.0, 10.4, 20.7],
    }
    valid_ts_df = pd.DataFrame(valid_ts_data)
    is_valid, errors = validate_data(valid_ts_df, "ts_ExampleMetric.csv")
    print(f"Valid TS Data Test: Valid={is_valid}, Errors={errors}")
    assert is_valid

    # Test case 2: Invalid time-series data (missing column)
    invalid_ts_data = {
        "Date": pd.to_datetime(["2023-01-01"]),
        # 'Code': ['FUNDA'], # Missing Code column
        "Value": [10.1],
    }
    invalid_ts_df = pd.DataFrame(invalid_ts_data)
    is_valid, errors = validate_data(invalid_ts_df, "ts_AnotherMetric.csv")
    print(f"Invalid TS Data Test (Missing Col): Valid={is_valid}, Errors={errors}")
    assert not is_valid
    assert "Missing required columns" in errors[0]

    # Test case 3: Invalid time-series data (non-numeric value)
    invalid_ts_data_type = {
        "Date": pd.to_datetime(["2023-01-01"]),
        "Code": ["FUNDA"],
        "Value": ["abc"],  # Non-numeric value
    }
    invalid_ts_df_type = pd.DataFrame(invalid_ts_data_type)
    is_valid, errors = validate_data(invalid_ts_df_type, "ts_BadData.csv")
    print(f"Invalid TS Data Test (Bad Type): Valid={is_valid}, Errors={errors}")
    # Note: This specific check might depend on when type conversion happens.
    # If conversion happens *before* validation, this might pass if 'abc' becomes NaN.
    # The check here assumes the raw data from API might be non-numeric.
    assert not is_valid  # Assuming the validation catches non-numeric directly
    assert "not numeric" in errors[0]

    # Test case 4: Empty DataFrame
    empty_df = pd.DataFrame()
    is_valid, errors = validate_data(empty_df, "ts_EmptyData.csv")
    print(f"Empty DF Test: Valid={is_valid}, Errors={errors}")
    assert is_valid  # Currently allows empty with warning
    assert "DataFrame is empty" in errors[0]

    # Test case 5: None DataFrame
    none_df = None
    is_valid, errors = validate_data(none_df, "ts_NoneData.csv")
    print(f"None DF Test: Valid={is_valid}, Errors={errors}")
    assert not is_valid
    assert "DataFrame is None" in errors[0]

    print("Validation tests completed.")


# Helper for date-like column detection (copied from data_audit.py for validation use)
def _is_date_like(s: str) -> bool:
    import re
    s = s.strip()
    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}$",
        r"^\d{2}/\d{2}/\d{4}$",
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    ]
    return any(re.match(p, s) for p in date_patterns)
