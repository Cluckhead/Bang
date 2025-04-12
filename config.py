# This file defines configuration variables for the Simple Data Checker application.
# It centralizes settings like file paths and visual parameters (e.g., chart colors)
# to make them easily adjustable without modifying the core application code.

"""
Configuration settings for the Flask application.
"""

# Define the primary data directory.
# This path is read by the `utils.get_data_folder_path` function during application startup.
# - If this is an absolute path (e.g., 'C:/MyApp/Data', '/var/data'), it will be used directly.
# - If this is a relative path (e.g., 'Data', '../SharedData'), it will be resolved
#   to an absolute path relative to the application's root directory (determined by Flask's app.root_path
#   or the script's location for standalone scripts).
# **Use forward slashes (/) for paths, even on Windows, for consistency.**
# If this variable is missing, empty, or the file doesn't exist, the utility function
# will fall back to using 'Data' relative to the application root.
DATA_FOLDER = 'Data'

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    'blue', 'red', 'green', 'purple', '#FF7F50', # Coral
    '#6495ED', # CornflowerBlue
    '#DC143C', # Crimson
    '#00FFFF'  # Aqua
] 