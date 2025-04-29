#!/usr/bin/env python
# test_staleness.py
# This script tests the staleness detection algorithm for quality assurance purposes.

import os
import pandas as pd
import sys
from datetime import datetime
import argparse

# Import the staleness detection functions
try:
    from staleness_processing import (
        get_stale_securities_details,
        DEFAULT_PLACEHOLDER_VALUES,
    )
except ImportError:
    print(
        "Error: Could not import staleness_processing module. Make sure it's in the current directory."
    )
    sys.exit(1)


def run_test(data_file, threshold_days=5):
    """
    Run a test of the staleness detection functions on a specific data file.

    Args:
        data_file: Path to the CSV file to test
        threshold_days: Number of days threshold for time-based staleness

    Returns:
        List of stale security IDs
    """
    print(f"\n--- Testing Staleness Detection on {data_file} ---")
    print(f"Using days threshold: {threshold_days}")

    # Get the directory containing the file
    data_folder = os.path.dirname(os.path.abspath(data_file))
    filename = os.path.basename(data_file)

    try:
        # Run the staleness detection
        stale_securities, latest_date, total_count = get_stale_securities_details(
            filename=filename, data_folder=data_folder, threshold_days=threshold_days
        )

        # Display results
        print(f"\nResults Summary:")
        print(f"Latest date in file: {latest_date}")
        print(f"Total securities analyzed: {total_count}")
        print(f"Stale securities detected: {len(stale_securities)}")

        if stale_securities:
            print("\nStale Securities Details:")
            print(
                f"{'ID':<15} {'Name':<20} {'Currency':<10} {'Last Update':<15} {'Days Stale':<10} {'Stale Type':<15}"
            )
            print("-" * 90)

            for sec in stale_securities:
                sec_id = sec["id"]
                sec_name = sec["static_info"].get("Security Name", "Unknown")
                currency = sec["static_info"].get("Currency", "Unknown")
                last_update = sec["last_update"]
                days_stale = sec["days_stale"]
                stale_type = sec.get("stale_type", "unknown")

                print(
                    f"{sec_id:<15} {sec_name:<20} {currency:<10} {last_update:<15} {days_stale:<10} {stale_type:<15}"
                )

        # Return the list of stale security IDs for further inspection
        return [sec["id"] for sec in stale_securities]

    except Exception as e:
        print(f"Error testing staleness detection: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Test the staleness detection algorithm"
    )
    parser.add_argument("file_path", help="Path to the CSV file to test")
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Days threshold for time-based staleness (default: 5)",
    )
    parser.add_argument(
        "--check-security", help="Check if a specific security ID is detected as stale"
    )

    args = parser.parse_args()

    # Verify file exists
    if not os.path.exists(args.file_path):
        print(f"Error: File not found: {args.file_path}")
        return

    # Run the test
    stale_ids = run_test(args.file_path, threshold_days=args.threshold)

    # If user requested to check a specific security
    if args.check_security:
        if args.check_security in stale_ids:
            print(f"\nSecurity {args.check_security} IS detected as stale.")
        else:
            print(f"\nSecurity {args.check_security} is NOT detected as stale.")


if __name__ == "__main__":
    main()
