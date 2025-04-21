#!/usr/bin/env python
# debug_security.py
# This script provides detailed debugging for a specific security to identify why it's
# not being properly detected as stale data.

import os
import pandas as pd
import numpy as np
import sys

# Security to debug
DEBUG_SECURITY_ID = "XS4035425"
DEBUG_FILE = "Data/sec_Spread.csv"

def debug_security():
    """Analyze a specific security to debug staleness detection issues."""
    print(f"Debugging staleness detection for security: {DEBUG_SECURITY_ID}")
    print(f"In file: {DEBUG_FILE}")
    
    try:
        # Check if file exists
        if not os.path.exists(DEBUG_FILE):
            print(f"Error: File not found: {DEBUG_FILE}")
            return
            
        # Read the CSV file
        df = pd.read_csv(DEBUG_FILE)
        print(f"File loaded successfully. Shape: {df.shape}")
        
        # Get column names
        id_column = df.columns[0]  # Usually ISIN is first column
        print(f"ID column: {id_column}")
        
        # Check if the security exists in the file
        security_rows = df[df[id_column] == DEBUG_SECURITY_ID]
        if security_rows.empty:
            print(f"Security {DEBUG_SECURITY_ID} not found in the file!")
            return
            
        print(f"Security found: {len(security_rows)} rows")
        
        # Analyze the security data
        security_row = security_rows.iloc[0]
        
        # Get date columns (columns after the metadata)
        # First 6 columns are typically metadata: ISIN, Name, Funds, Type, Callable, Currency
        meta_columns = df.columns[:6]
        date_columns = df.columns[6:]
        
        print("\nMetadata for the security:")
        for col in meta_columns:
            print(f"  {col}: {security_row[col]}")
            
        # Get the values for date columns
        values = security_row[date_columns].values
        
        print("\nValue patterns:")
        print("Index | Date       | Value  | Is 100?")
        print("-" * 45)
        
        consecutive_100s = 0
        for i, (col, val) in enumerate(zip(date_columns, values)):
            is_100 = (val == 100)
            if is_100:
                consecutive_100s += 1
            else:
                consecutive_100s = 0
                
            print(f"{i:5d} | {col:10s} | {val!s:6s} | {'Yes' if is_100 else 'No'} {'← Start of ' + str(consecutive_100s) + ' consecutive 100s' if is_100 and consecutive_100s == 1 else ''}")
            
            # Highlight potential staleness pattern
            if consecutive_100s == 3:
                print(f"{'':5s} | {'':10s} | {'':6s} | ^ Found 3 consecutive 100s - should be detected as stale!")
        
        # Analyze the pattern of 100s
        value_counts = pd.Series(values).value_counts()
        print("\nValue distribution:")
        for val, count in value_counts.items():
            print(f"  {val}: {count} occurrences")
            
        # Look for consecutive 100s
        max_consecutive_100s = 0
        current_consecutive = 0
        stale_start_idx = None
        
        for i, val in enumerate(values):
            if val == 100:
                current_consecutive += 1
                if current_consecutive == 1:
                    stale_start_idx = i
                max_consecutive_100s = max(max_consecutive_100s, current_consecutive)
            else:
                current_consecutive = 0
                stale_start_idx = None
                
        print(f"\nMaximum consecutive 100 values: {max_consecutive_100s}")
        
        if max_consecutive_100s >= 3:
            print("This security SHOULD be detected as stale based on having 3+ consecutive 100s.")
            if stale_start_idx is not None:
                stale_start_date = date_columns[stale_start_idx]
                print(f"Staleness begins at: {stale_start_date} (index {stale_start_idx})")
        else:
            print("This security does not have 3+ consecutive 100s, so it might not be detected as stale by that method.")
            
    except Exception as e:
        print(f"Error debugging security: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Override security ID if provided as argument
    if len(sys.argv) > 1:
        DEBUG_SECURITY_ID = sys.argv[1]
        
    debug_security() 