# This file defines configuration variables for the Simple Data Checker application.
# It centralizes settings like file paths and visual parameters (e.g., chart colors)
# to make them easily adjustable without modifying the core application code.

"""
Configuration settings for the Flask application.
"""

DATA_FOLDER = 'Data'

# Define a list of distinct colors for chart lines
# Add more colors if you expect more fund columns
COLOR_PALETTE = [
    'blue', 'red', 'green', 'purple', '#FF7F50', # Coral
    '#6495ED', # CornflowerBlue
    '#DC143C', # Crimson
    '#00FFFF'  # Aqua
] 