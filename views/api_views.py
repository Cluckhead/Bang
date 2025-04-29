# Purpose: Main entry point for API views. Imports and exposes API blueprints and routes for the Simple Data Checker app.
# No function definitions in this file.

"""
Main entry point for API views.
This file now imports from the split modules to maintain backward compatibility.
"""

# Import all components from the split files
from views.api_core import (
    api_bp,
    USE_REAL_TQS_API,
    _simulate_and_print_tqs_call,
    _fetch_real_tqs_data,
    _find_key_columns,
    get_data_file_statuses,
)

from views.api_routes_data import get_data_page
from views.api_routes_call import run_api_calls, rerun_api_call

# The api_bp Blueprint is now available from this module as before
# All the previously defined functions are also available through this import structure
