# This file defines configuration variables for the Simple Data Checker application.
# It centralizes settings like file paths and visual parameters (e.g., chart colors)
# to make them easily adjustable without modifying the core application code.

"""
Configuration settings for the Flask application.
"""

import os
from pathlib import Path

# Base directory of the application
BASE_DIR = Path(__file__).resolve().parent

# Data folder configuration
# Use environment variable if set, otherwise default to 'Data' subdirectory
DATA_FOLDER_NAME = os.environ.get('DATA_CHECKER_DATA_FOLDER', 'Data')
DATA_FOLDER = os.path.join(BASE_DIR, DATA_FOLDER_NAME) # Absolute path

# Define the standard column name used for security identifiers (e.g., ISIN)
ID_COLUMN = 'ISIN'

# Define the filename for the exclusions list
EXCLUSIONS_FILE = 'exclusions.csv'

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    '#1f77b4',  # Muted Blue
    '#ff7f0e',  # Safety Orange
    '#2ca02c',  # Cooked Asparagus Green
    '#d62728',  # Brick Red
    '#9467bd',  # Muted Purple
    '#8c564b',  # Chestnut Brown
    '#e377c2',  # Raspberry Yogurt Pink
    '#7f7f7f',  # Middle Gray
    '#bcbd22',  # Curry Yellow-Green
    '#17becf'   # Blue-Teal
]

# --- NEW: Comparison Configuration ---
# Defines the different types of security data comparisons available.
# Keys are the identifier used in URLs (e.g., 'spread').
# Values are dictionaries containing:
#   - display_name: User-friendly name for titles and labels.
#   - file1: The filename for the 'original' dataset.
#   - file2: The filename for the 'new' or 'comparison' dataset.
COMPARISON_CONFIG = {
    'spread': {
        'display_name': 'Spread',
        'file1': 'sec_spread.csv',
        'file2': 'sec_spreadSP.csv',
        'value_label': 'Spread' # Label for the 'Value' column in charts/stats
    },
    'duration': {
        'display_name': 'Duration',
        'file1': 'sec_duration.csv',
        'file2': 'sec_durationSP.csv',
        'value_label': 'Duration'
    },
    'spread_duration': {
        'display_name': 'Spread Duration',
        'file1': 'sec_Spread duration.csv', # Note the space in filename
        'file2': 'sec_Spread durationSP.csv', # Note the space in filename
        'value_label': 'Spread Duration'
    }
    # Add new comparison types here in the future
    # 'yield': {
    #     'display_name': 'Yield',
    #     'file1': 'sec_yield.csv',
    #     'file2': 'sec_yieldSP.csv',
    #     'value_label': 'Yield'
    # }
}

# Logging configuration (optional, Flask's default logging can be used)
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'instance', 'app.log'), # Log file path
            'mode': 'a', # Append mode
        },
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['console', 'file'],
            'level': 'DEBUG', # Set root level to DEBUG to capture everything
            'propagate': True
        },
        'werkzeug': { # Quieter logging for Werkzeug (Flask's development server)
             'handlers': ['console', 'file'],
             'level': 'INFO', # Or WARNING
             'propagate': False
         },
         # You can add specific loggers for your modules if needed
         #'app': {
         #    'handlers': ['console', 'file'],
         #    'level': 'DEBUG',
         #    'propagate': False
         #},
    }
}

# To enable more verbose debugging, set the 'level' value to 'DEBUG' in the LOGGING_CONFIG['loggers'][''] section below.
# For example: 'level': 'DEBUG' (already set for root logger). For less verbosity, use 'INFO' or 'WARNING'.

# --- Add comments explaining the purpose of this file ---
# This file centralizes configuration settings for the Simple Data Checker application.
# It defines paths, constants (like color palettes), and specific configurations
# for different features, such as the data comparison types.
# Using a central configuration file makes the application easier to manage and modify.
# Environment variables can be used to override defaults (e.g., DATA_FOLDER).

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    'blue', 'red', 'green', 'purple', '#FF7F50', # Coral
    '#6495ED', # CornflowerBlue
    '#DC143C', # Crimson
    '#00FFFF'  # Aqua
]

# Define allowed data sources for issue tracking and related features
DATA_SOURCES = [
    "S&P", "Production", "Pi", "IVP", "Benchmark", "BANG Bug", "Rimes"
]

# --- Yield Curve Processing Thresholds ---
# Threshold for detecting large non-monotonic drops in curve values (e.g., -0.5 means a drop > 0.5 is flagged)
CURVE_MONOTONICITY_DROP_THRESHOLD = -0.5
# Multiplier for standard deviation in anomaly detection (e.g., 3 means mean + 3*std)
CURVE_ANOMALY_STD_MULTIPLIER = 3
# Minimum absolute threshold for anomaly detection in curve change profile
CURVE_ANOMALY_ABS_THRESHOLD = 0.2 