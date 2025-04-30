#!/usr/bin/env python
# direct_test.py
# This script directly reads the CSV and checks for placeholder values
# to show exactly what's happening with our specific security

import pandas as pd
import os
import config
import argparse

# Test parameters
def main():
    parser = argparse.ArgumentParser(description="Direct placeholder detection for a security in a CSV file.")
    parser.add_argument("--security_id", type=str, default="XS4035425", help="Security ID to check")
    parser.add_argument("--csv_file", type=str, default="Data/sec_Spread.csv", help="CSV file to check")
    parser.add_argument("--placeholder_value", type=float, default=None, help="Placeholder value to check (default: config.STALENESS_PLACEHOLDERS[0])")
    parser.add_argument("--consecutive_threshold", type=int, default=None, help="Consecutive threshold (default: config.STALENESS_THRESHOLD_DAYS)")
    args = parser.parse_args()

    SECURITY_ID = args.security_id
    CSV_FILE = args.csv_file
    PLACEHOLDER_VALUE = args.placeholder_value if args.placeholder_value is not None else config.STALENESS_PLACEHOLDERS[0]
    CONSECUTIVE_THRESHOLD = args.consecutive_threshold if args.consecutive_threshold is not None else config.STALENESS_THRESHOLD_DAYS

    print(f"Testing direct placeholder detection for {SECURITY_ID} in {CSV_FILE}")

    # Check if file exists
    if not os.path.exists(CSV_FILE):
        print(f"Error: File {CSV_FILE} not found")
        return

    # Load the CSV
    try:
        df = pd.read_csv(CSV_FILE)
        print(f"CSV loaded successfully: {df.shape}")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return

    # Find the security
    security_rows = df[df.iloc[:, 0] == SECURITY_ID]
    if security_rows.empty:
        print(f"Security {SECURITY_ID} not found")
        return

    print(f"Found security: {len(security_rows)} rows")

    # Extract the data
    row = security_rows.iloc[0]

    # Get date columns (assume first 6 columns are metadata)
    meta_columns = df.columns[:6]
    date_columns = df.columns[6:]

    # Get security metadata
    print("\nSecurity metadata:")
    for col in meta_columns:
        print(f"  {col}: {row[col]}")

    # Get values for date columns
    values = row[date_columns].values

    # Simple placeholder detection algorithm
    consecutive_count = 0
    stale_start_idx = None

    print("\nValue analysis:")
    print(
        f"{'Index':5s} | {'Date':10s} | {'Value':8s} | {'Is 100?':7s} | {'Consecutive':10s}"
    )
    print("-" * 50)

    for i, (date, val) in enumerate(zip(date_columns, values)):
        is_placeholder = False

        # Check if value is placeholder (with flexible comparison)
        try:
            num_val = float(val)
            is_placeholder = abs(num_val - PLACEHOLDER_VALUE) < 0.0001
        except (ValueError, TypeError):
            is_placeholder = False

        if is_placeholder:
            consecutive_count += 1
            if consecutive_count == 1:
                stale_start_idx = i
        else:
            consecutive_count = 0
            stale_start_idx = None

        print(
            f"{i:5d} | {date:10s} | {val!s:8s} | {'Yes' if is_placeholder else 'No':7s} | {consecutive_count:10d}"
        )

        # Check for staleness threshold
        if consecutive_count == CONSECUTIVE_THRESHOLD:
            print(
                f"FOUND {CONSECUTIVE_THRESHOLD} CONSECUTIVE PLACEHOLDERS - THIS IS STALE DATA"
            )
            print(
                f"Starting at index {stale_start_idx}, date: {date_columns[stale_start_idx]}"
            )

    # Final result
    print("\nAnalysis Summary:")
    max_consecutive = 0
    current_consecutive = 0
    for val in values:
        try:
            num_val = float(val)
            is_placeholder = abs(num_val - PLACEHOLDER_VALUE) < 0.0001
        except (ValueError, TypeError):
            is_placeholder = False

        if is_placeholder:
            current_consecutive += 1
            max_consecutive = max(current_consecutive, max_consecutive)
        else:
            current_consecutive = 0

    print(f"Maximum consecutive placeholder values: {max_consecutive}")
    if max_consecutive >= CONSECUTIVE_THRESHOLD:
        print(f"RESULT: Security {SECURITY_ID} SHOULD be detected as stale")
    else:
        print(f"RESULT: Security {SECURITY_ID} should NOT be detected as stale")


if __name__ == "__main__":
    main()
