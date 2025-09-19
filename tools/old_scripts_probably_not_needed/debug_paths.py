#!/usr/bin/env python
"""Debug script to check path resolution"""

import os
import sys
from pathlib import Path

# Add project root to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

print("=== Path Debugging ===\n")

print(f"1. Script location: {__file__}")
print(f"2. Script directory: {script_dir}")
print(f"3. Current working directory: {os.getcwd()}")

# Import config and check BASE_DIR
from core.config import BASE_DIR
print(f"\n4. config.BASE_DIR: {BASE_DIR}")
print(f"   - Type: {type(BASE_DIR)}")
print(f"   - Exists: {BASE_DIR.exists()}")

# Check settings file
settings_file = os.path.join(str(BASE_DIR), "settings.yaml")
print(f"\n5. Settings file path: {settings_file}")
print(f"   - Exists: {os.path.exists(settings_file)}")

# Try to load settings
try:
    from core.settings_loader import get_app_config
    app_config = get_app_config()
    print(f"\n6. App config loaded successfully")
    print(f"   - data_folder setting: {app_config.get('data_folder')}")
except Exception as e:
    print(f"\n6. Failed to load app config: {e}")

# Try to get data folder path
try:
    from core.utils import get_data_folder_path
    
    print(f"\n7. Testing get_data_folder_path()...")
    
    # Without arguments
    data_path = get_data_folder_path()
    print(f"   - Result (no args): {data_path}")
    print(f"   - Exists: {os.path.exists(data_path)}")
    
    # With project root
    data_path_with_root = get_data_folder_path(app_root_path=str(BASE_DIR))
    print(f"   - Result (with BASE_DIR): {data_path_with_root}")
    print(f"   - Exists: {os.path.exists(data_path_with_root)}")
    
except Exception as e:
    print(f"\n7. Failed to get data folder path: {e}")
    import traceback
    traceback.print_exc()

print("\n=== End Debug ===")