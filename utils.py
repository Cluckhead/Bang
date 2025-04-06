# This file contains utility functions used throughout the Simple Data Checker application.
# These functions provide common helper functionalities like parsing specific string formats
# or validating data types, helping to keep the main application logic cleaner.

"""
Utility functions for the Flask application.
"""
import re
import pandas as pd

def _is_date_like(column_name):
    """Check if a column name looks like a date (e.g., DD/MM/YYYY).
    Simple regex, adjust if date formats vary significantly.
    Ensures the pattern matches the entire string.
    """
    return bool(re.match(r'^\d{2}/\d{2}/\d{4}$', str(column_name)))

def parse_fund_list(fund_string):
    """Safely parses the fund list string like '[FUND1,FUND2]' or '[FUND1]' into a list.
       Handles potential errors and variations in spacing.
    """
    if not isinstance(fund_string, str) or not fund_string.startswith('[') or not fund_string.endswith(']'):
        return [] # Return empty list if format is unexpected
    try:
        # Remove brackets and split by comma
        content = fund_string[1:-1]
        # Split by comma, strip whitespace from each element
        funds = [f.strip() for f in content.split(',') if f.strip()]
        return funds
    except Exception as e:
        print(f"Error parsing fund string '{fund_string}': {e}")
        return [] 