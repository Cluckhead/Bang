#!/usr/bin/env python
"""Test if settings are now loaded correctly from tools directory"""

import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

print("Testing settings loading from tools/ directory...")
print(f"Script dir: {script_dir}")
print(f"Project root: {project_root}")
print(f"Current working directory: {os.getcwd()}")

# Test settings loading
from core.settings_loader import get_app_config, SETTINGS_FILE
print(f"\nSettings file path resolved to: {SETTINGS_FILE}")

app_config = get_app_config()
data_folder = app_config.get('data_folder')
print(f"data_folder from settings: '{data_folder}'")

if data_folder == 'This is a test':
    print("✅ SUCCESS! Settings are being loaded correctly.")
    print("The test value 'This is a test' was retrieved.")
else:
    print(f"❌ FAILED! Expected 'This is a test', got '{data_folder}'")

# Now test get_data_folder_path
from core.utils import get_data_folder_path

print("\nTesting get_data_folder_path()...")
try:
    # This should fail because 'This is a test' is not a valid directory
    result = get_data_folder_path(app_root_path=project_root)
    print(f"Result: {result}")
except Exception as e:
    print(f"Expected error (since 'This is a test' is not a valid path): {e}")