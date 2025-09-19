# Purpose: This file defines configuration variables for the Simple Data Checker application.
# It centralizes settings like file paths, feature configurations (e.g., comparisons, thresholds),
# and visual parameters (e.g., chart colors) to make them easily adjustable
# without modifying the core application code.

# Standard column name constants
FUNDS_COL = "Funds"
ISIN_COL = "ISIN"
SEC_NAME_COL = "Security Name"
DATE_COL = "Date"
VALUE_COL = "Value"
CODE_COL = "Code"
TYPE_COL = "Type"
CURRENCY_COL = "Currency"
PICKED_COL = "Picked"
TOTAL_ASSET_VALUE_COL = "Total Asset Value USD"
FUND_CODE_COL = "Fund Code"

# This file defines configuration variables for the Simple Data Checker application.
# It centralizes settings like file paths, feature configurations (e.g., comparisons, thresholds),
# and visual parameters (e.g., chart colors) to make them easily adjustable
# without modifying the core application code.

"""
Configuration settings for the Flask application.
"""

import os
from pathlib import Path
from typing import List, Dict
from core.utils import load_yaml_config
import yaml
from core.settings_loader import (
    get_comparison_config,
    get_maxmin_thresholds,
    get_metric_file_map,
    get_attribution_columns
)

# Base directory of the application (now points to core/ directory)
BASE_DIR = Path(__file__).resolve().parent.parent  # Go up one level to project root

# -------------------------------------------
# Data folder configuration logic (updated)
# -------------------------------------------
# Priority order for determining the data folder location:
# 1. Environment variable `DATA_CHECKER_DATA_FOLDER` (absolute or relative)
# 2. `data_folder` entry inside `config/app_config.yaml`
# 3. Default folder name "Data" (relative to the project root)

# DATA_FOLDER is now set by app.py via get_data_folder_path()
# This prevents the module-level code from running before Flask context exists
DATA_FOLDER = None  # Will be set by app.py

# Define the standard column name used for security identifiers (e.g., ISIN)
ID_COLUMN = "ISIN"

# Define the filename for the exclusions list
EXCLUSIONS_FILE = "exclusions.csv"
W_SECS_FILENAME = "w_secs.csv"  # Filename for security weights/holdings

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE: List[str] = [
    "blue",
    "red",
    "green",
    "purple",
    "#FF7F50",
    "#6495ED",
    "#DC143C",
    "#00FFFF",
    "#FFA500",
    "#8A2BE2",
    "#228B22",
    "#FF1493",
    "#A52A2A",
    "#20B2AA",
]

# Bloomberg YAS URL syntax (format string, use {ticker} for the BBG Ticker Yellow)
BLOOMBERG_YAS_URL_FORMAT = "blp://function/YAS?ticker={ticker}"

# --- NEW: Comparison Configuration ---
# Loads the different types of security data comparisons from YAML.
COMPARISON_CONFIG: Dict[str, Dict[str, str]] = get_comparison_config()

# --- NEW: Max/Min Value Threshold Configuration ---
# Loads max/min value thresholds for files from YAML.
MAXMIN_THRESHOLDS: Dict[str, Dict[str, str]] = get_maxmin_thresholds()

# --- Metric File Map (Aggregate/Security-level mapping) ---
# Loads the mapping of each metric to its aggregate and security-level files, display names, and units.
METRIC_FILE_MAP: Dict[str, Dict[str, str]] = get_metric_file_map()

# Logging configuration (optional, Flask's default logging can be used)
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
        },
        "file": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.FileHandler",
            "filename": os.path.join(BASE_DIR, "instance", "app.log"),  # Log file path
            "mode": "a",  # Append mode
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["console", "file"],
            "level": "DEBUG",  # Set root level to DEBUG to capture everything
            "propagate": True,
        },
        "werkzeug": {  # Quieter logging for Werkzeug (Flask's development server)
            "handlers": ["console", "file"],
            "level": "INFO",  # Or WARNING
            "propagate": False,
        },
        # You can add specific loggers for your modules if needed
        #'app': {
        #    'handlers': ['console', 'file'],
        #    'level': 'DEBUG',
        #    'propagate': False
        # },
    },
}

# To enable more verbose debugging, set the 'level' value to 'DEBUG' in the LOGGING_CONFIG['loggers'][''] section below.
# For example: 'level': 'DEBUG' (already set for root logger). For less verbosity, use 'INFO' or 'WARNING'.

# --- Add comments explaining the purpose of this file ---
# This file centralizes configuration settings for the Simple Data Checker application.
# It defines paths, constants (like color palettes), and specific configurations
# for different features, such as the data comparison types.
# Using a central configuration file makes the application easier to manage and modify.
# Environment variables can be used to override defaults (e.g., DATA_FOLDER).

# Define allowed data sources for issue tracking and related features
DATA_SOURCES = ["S&P", "Production", "Pi", "IVP", "Benchmark", "BANG Bug", "Rimes"]

# --- JIRA Configuration ---
# Base URL for JIRA issues - used to convert issue keys like PROJ-123 into full URLs
# Change this to match your organization's JIRA instance
JIRA_BASE_URL = "https://jira.example.com/browse/"

# --- Yield Curve Processing Thresholds ---
# Threshold for detecting large non-monotonic drops in curve values (e.g., -0.5 means a drop > 0.5 is flagged)
CURVE_MONOTONICITY_DROP_THRESHOLD = -0.5
# Multiplier for standard deviation in anomaly detection (e.g., 3 means mean + 3*std)
CURVE_ANOMALY_STD_MULTIPLIER = 3
# Minimum absolute threshold for anomaly detection in curve change profile
CURVE_ANOMALY_ABS_THRESHOLD = 0.2

# List of known metadata column names used for identifying non-data columns in wide-format files
METADATA_COLS: list = [
    FUNDS_COL,
    ISIN_COL,
    SEC_NAME_COL,
    DATE_COL,
    CODE_COL,
    TYPE_COL,
    CURRENCY_COL,
    FUND_CODE_COL,
]

# List of placeholder values used for staleness detection (e.g., 100 for missing/placeholder data)
STALENESS_PLACEHOLDERS: list = [100]

# Default threshold (in days) for staleness detection
STALENESS_THRESHOLD_DAYS: int = 5

# --- Data Processing Configuration ---
# Controls whether zeros in CSV data should be replaced with NaN to prevent chart and correlation issues
REPLACE_ZEROS_WITH_NAN: bool = True

# Number of securities to display per page in security views
SECURITIES_PER_PAGE: int = 50

# Number of comparison rows to display per page in generic comparison views
COMPARISON_PER_PAGE: int = 50

# List of regex patterns for detecting date-like column names (used in utils._is_date_like and elsewhere)
DATE_COLUMN_PATTERNS: list = [
    r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
    r"\d{2}/\d{2}/\d{4}",  # DD/MM/YYYY
    r"\d{2}-\d{2}-\d{4}",  # DD-MM-YYYY
    r"\d{4}/\d{2}/\d{2}",  # YYYY/MM/DD
    r"^Date$",  # Exact 'Date'
    r"^Position Date$",  # Exact 'Position Date'
    r"^Trade Date$",  # Exact 'Trade Date'
    r"^AsOfDate$",  # Exact 'AsOfDate'
    r"^Effective Date$",  # Exact 'Effective Date'
]

# List of regex patterns for detecting benchmark column names
BENCHMARK_COLUMN_PATTERNS: list = [
    r"^Benchmark.*$",  # Any column starting with "Benchmark"
    r"^Bench.*$",      # Columns starting with "Bench" (e.g., Bench Duration)
    r"^BM.*$",         # Abbreviated benchmark names starting with "BM"
]

# Pattern for ISIN suffixing when duplicate Security Names are found (used in process_data.py)
ISIN_SUFFIX_PATTERN: str = "{isin}-{n}"

# L1 and L2 factor groupings for attribution (used in views/attribution_views.py)
ATTRIBUTION_L1_GROUPS = {
    "Rates": [
        "Rates Carry Daily",
        "Rates Convexity Daily",
        "Rates Curve Daily",
        "Rates Duration Daily",
        "Rates Roll Daily",
    ],
    "Credit": [
        "Credit Spread Change Daily",
        "Credit Convexity Daily",
        "Credit Carry Daily",
        "Credit Defaulted",
    ],
    "FX": ["FX Carry Daily", "FX Change Daily"],
}
ATTRIBUTION_L2_GROUPS = {
    "Credit": [
        "Credit Spread Change Daily",
        "Credit Convexity Daily",
        "Credit Carry Daily",
        "Credit Defaulted",
    ],
    "Rates": [
        "Rates Carry Daily",
        "Rates Convexity Daily",
        "Rates Curve Daily",
        "Rates Duration Daily",
        "Rates Roll Daily",
    ],
    "FX": ["FX Carry Daily", "FX Change Daily"],
}

# List of expected statistic keys for generic comparison details (used in views/generic_comparison_views.py)
GENERIC_COMPARISON_STATS_KEYS = [
    "Level_Correlation",
    "Change_Correlation",
    "Mean_Abs_Diff",
    "Max_Abs_Diff",
    "Same_Date_Range",
    "is_held",
    "StaticCol",
    "NaN_Count_Orig",
    "NaN_Count_New",
    "Total_Points",
]

# Example data and selectors for Playwright screenshot script
PLAYWRIGHT_EXAMPLE_DATA = {
    "EXAMPLE_METRIC": "Metric1",
    "EXAMPLE_SECURITY_METRIC": "spread",
    "EXAMPLE_SECURITY_ID": "XS4363421503",
    "EXAMPLE_FUND_CODE": "IG01",
    "EXAMPLE_COMPARISON": "spread",
    "EXAMPLE_CURRENCY": "USD",
    "EXAMPLE_MAXMIN_FILE": "sec_Spread.csv",
    "EXAMPLE_BREACH_TYPE": "max",
    "EXAMPLE_FUND_GROUP": "IG01",
}
PLAYWRIGHT_SELECTORS = {
    "inspect_modal": "button:has-text('Inspect')",
    "raise_issue_modal": "button.btn-warning:has-text('Raise Data Issue')",
    "add_exclusion_modal": "button.btn-danger:has-text('Add Exclusion')",
    "add_watchlist_modal": "button.btn-success:has-text('Add to Watchlist')",
    "clear_watchlist_modal": "button.btn-danger:has-text('Clear')",
}

# Static info groupings for security details (used in views/security_views.py)
STATIC_INFO_GROUPS = [
    ("Identifiers", [ISIN_COL, SEC_NAME_COL, "BBG ID", "BBG Ticker Yellow"]),
    (
        "Classification",
        [
            "Security Sub Type",
            "SS Project - In Scope",
            "Is Distressed",
            "Rating",
            "BBG LEVEL 3",
            "Position Currency",
            "Country Of Risk",
        ],
    ),
    ("Call/Redemption", ["Call Indicator", "Make Whole Call"]),
    ("Financials", ["Coupon Rate", "Maturity Date"]),
]

# List of regex patterns for identifying ID columns (ISIN, Security Name, Code, etc.)
ID_COLUMN_PATTERNS = [
    r"^ISIN$",
    r"^Security Name$",
    r"^Code$",
    r"^SecurityID$",
    r"^Fund Code$",
]

# List of regex patterns for identifying static columns (Type, Currency, etc.)
STATIC_COLUMN_PATTERNS = [
    r"^Type$",
    r"^Currency$",
    r"^CCY$",  # legacy support
    r"^Position\s*Currency$",  # new header
    r"^Security Name$",
    r"^Security Sub Type$",
    r"^Country Of Risk$",
    r"^Rating$",
]

# List of regex patterns for identifying code columns (Code, Fund Code, etc.)
CODE_COLUMN_PATTERNS = [
    r"^Code$",
    r"^Fund Code$",
    r"^SecurityID$",
]

# List of regex patterns for identifying benchmark columns
BENCHMARK_COLUMN_PATTERNS = [
    r"^Benchmark.*$",  # Any column starting with "Benchmark"
    r"^Bench.*$",      # Columns starting with "Bench" (e.g., Bench Duration)
    r"^BM.*$",         # Abbreviated benchmark names starting with "BM"
]

# List of regex patterns for identifying scope columns (SS Project - In Scope, etc.)
SCOPE_COLUMN_PATTERNS = [
    r"SS\s*Project\s*-\s*In\s*Scope",
    r"In\s*Scope",
]

# Attribution column header config (prefixes, factors, etc.)
try:
    ATTRIBUTION_COLUMNS_CONFIG = get_attribution_columns()
except Exception as e:
    ATTRIBUTION_COLUMNS_CONFIG = None
    # Optionally log or print error here

# Default column order for the main securities summary table
SECURITIES_SUMMARY_COLUMNS_ORDER = [
    ISIN_COL,
    SEC_NAME_COL,
    TYPE_COL,
    CURRENCY_COL,
    'Latest Value',
    'Change',
    'Max |Δ| (bps)',  # NEW – biggest daily move over full history
    '% Days >| 50 bps|',  # NEW – % of days with abs(move) > threshold
    'Change Z-Score',
    'Mean',
    'Max',
    'Min'
]

LARGE_MOVE_THRESHOLD_BPS: int = 50  # Threshold (in basis points) for flagging large daily spread moves
