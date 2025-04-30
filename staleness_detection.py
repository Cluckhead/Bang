#!/usr/bin/env python
# staleness_detection.py
# This script analyzes CSV financial data files to detect stale data patterns, particularly
# looking for securities with repeated placeholder values that indicate stale or missing data.

import os
import pandas as pd
import numpy as np
from datetime import datetime
import argparse
import config


def is_placeholder_value(value, placeholder_indicators=[100]):
    """
    Check if a value appears to be a placeholder (stale data indicator).

    Args:
        value: The value to check
        placeholder_indicators: List of common placeholder values

    Returns:
        Boolean indicating if the value is likely a placeholder
    """
    if pd.isna(value):
        return True

    # Check against common placeholder values with float comparison
    try:
        # Try to convert to numeric for comparison
        numeric_value = float(value)
        for placeholder in placeholder_indicators:
            # Use approximate equality to handle float precision issues
            placeholder_float = float(placeholder)
            if abs(numeric_value - placeholder_float) < 0.0001:
                return True
    except (ValueError, TypeError):
        # If value can't be converted to numeric, it's not our placeholder
        pass

    return False


def detect_stale_data(
    file_path, placeholder_values=[100], consecutive_threshold=3, quiet=False
):
    """
    Analyze a CSV file to detect securities with stale/placeholder data.

    Args:
        file_path: Path to the CSV file
        placeholder_values: List of values considered as placeholders/stale indicators
        consecutive_threshold: Number of consecutive placeholders to consider stale
        quiet: If True, suppresses informational output

    Returns:
        DataFrame with results of stale data analysis
    """
    if not quiet:
        print(f"Analyzing file: {file_path}")

    try:
        # Read the CSV file
        df = pd.read_csv(file_path)

        # Check if the file has expected structure
        if (
            df.shape[1] < 7 and not quiet
        ):  # Need at least ID, name, metadata columns + some data columns
            print(
                f"Warning: File format may be incorrect. Found only {df.shape[1]} columns."
            )
            return pd.DataFrame()

        # Get the column that contains the security IDs
        id_column = df.columns[0]  # Assuming ISIN is always first column

        # Identify date columns (should be all columns beyond the metadata)
        # Assuming first 6 columns are metadata: ISIN, Name, Funds, Type, Callable, Currency
        date_columns = df.columns[6:]

        # Results container
        results = []

        # Process each security
        for idx, row in df.iterrows():
            security_id = row[id_column]
            security_name = row[df.columns[1]] if df.shape[1] > 1 else "Unknown"

            # Get the data values for date columns
            values = row[date_columns].values

            # Check for placeholder patterns
            consecutive_placeholders = 0
            stale_start_idx = None

            for i, val in enumerate(values):
                if is_placeholder_value(val, placeholder_values):
                    consecutive_placeholders += 1
                    if consecutive_placeholders == 1:
                        stale_start_idx = i
                else:
                    consecutive_placeholders = 0
                    stale_start_idx = None

                # If we've found enough consecutive placeholders, mark as stale
                if consecutive_placeholders >= consecutive_threshold:
                    # Get the date when staleness begins
                    stale_start_date = date_columns[stale_start_idx]

                    # Calculate percentage of data points that are stale
                    stale_pct = consecutive_placeholders / len(date_columns) * 100

                    results.append(
                        {
                            "security_id": security_id,
                            "security_name": security_name,
                            "stale_start_date": stale_start_date,
                            "stale_consecutive_values": consecutive_placeholders,
                            "stale_percent": stale_pct,
                            "is_stale": True,
                        }
                    )
                    break

            # If no staleness found, add a record showing it's not stale
            if consecutive_placeholders < consecutive_threshold:
                results.append(
                    {
                        "security_id": security_id,
                        "security_name": security_name,
                        "stale_start_date": None,
                        "stale_consecutive_values": 0,
                        "stale_percent": 0,
                        "is_stale": False,
                    }
                )

        # Convert to DataFrame
        results_df = pd.DataFrame(results)
        return results_df

    except Exception as e:
        if not quiet:
            print(f"Error analyzing file: {e}")
        return pd.DataFrame()


def main():
    """Main function to run the stale data detection script."""
    parser = argparse.ArgumentParser(
        description="Detect stale data in financial CSV files"
    )
    parser.add_argument("file_path", help="Path to the CSV file to analyze")
    parser.add_argument(
        "--placeholder",
        type=int,
        nargs="+",
        default=config.STALENESS_PLACEHOLDERS,
        help="Placeholder values to detect (default: config.STALENESS_PLACEHOLDERS)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=config.STALENESS_THRESHOLD_DAYS,
        help="Number of consecutive placeholders to consider data stale (default: config.STALENESS_THRESHOLD_DAYS)",
    )
    parser.add_argument("--output", help="Output file path for results CSV (optional)")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    parser.add_argument(
        "--compact", action="store_true", help="Display results in compact format"
    )

    args = parser.parse_args()

    # Check if file exists
    if not os.path.exists(args.file_path):
        print(f"Error: File not found: {args.file_path}")
        return

    # Run the analysis
    results = detect_stale_data(
        args.file_path,
        placeholder_values=args.placeholder,
        consecutive_threshold=args.threshold,
        quiet=args.quiet,
    )

    # Display summary
    if not results.empty:
        stale_count = results["is_stale"].sum()
        total_count = len(results)

        if not args.quiet:
            if args.compact:
                print(
                    f"Results: {total_count} securities, {stale_count} stale ({stale_count/total_count*100:.1f}%)"
                )
            else:
                print(f"\nAnalysis Results:")
                print(f"Total securities: {total_count}")
                print(
                    f"Stale securities: {stale_count} ({stale_count/total_count*100:.1f}%)"
                )

            # Show stale securities
            if stale_count > 0 and not args.compact:
                print("\nStale Securities:")
                stale_df = results[results["is_stale"]]
                for idx, row in stale_df.iterrows():
                    print(
                        f"- {row['security_id']} ({row['security_name']}): Stale from {row['stale_start_date']}, {row['stale_consecutive_values']} consecutive values"
                    )

        # Save results if requested
        if args.output:
            results.to_csv(args.output, index=False)
            if not args.quiet:
                print(f"\nResults saved to: {args.output}")
    elif not args.quiet:
        print("Analysis failed or no results found.")


if __name__ == "__main__":
    main()
