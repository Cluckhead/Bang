#!/usr/bin/env python
"""Debug script to test run_preprocessing data folder resolution"""

import os
import sys
import logging

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("=" * 60)
print("DEBUG: run_preprocessing data folder resolution")
print("=" * 60)

# Get script location
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

print(f"\n1. Script directory: {script_dir}")
print(f"2. Project root: {project_root}")
print(f"3. Current working directory: {os.getcwd()}")

# Add project root to Python path (same as run_preprocessing.py does)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"4. Added project root to sys.path")

print(f"\n5. Python path:")
for i, p in enumerate(sys.path[:5]):
    print(f"   [{i}] {p}")

# Test imports
print("\n6. Testing imports...")
try:
    from core import config
    print(f"   ✓ core.config imported")
    print(f"     - BASE_DIR: {config.BASE_DIR}")
    print(f"     - BASE_DIR type: {type(config.BASE_DIR)}")
except Exception as e:
    print(f"   ✗ Failed to import core.config: {e}")
    sys.exit(1)

try:
    from core.settings_loader import get_app_config
    print(f"   ✓ core.settings_loader imported")
    
    # Load app config
    app_config = get_app_config()
    print(f"\n7. App config loaded:")
    print(f"   - data_folder value: '{app_config.get('data_folder')}'")
    print(f"   - Type: {type(app_config.get('data_folder'))}")
    
except Exception as e:
    print(f"   ✗ Failed to import settings_loader: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    from core.utils import get_data_folder_path
    print(f"   ✓ core.utils.get_data_folder_path imported")
except Exception as e:
    print(f"   ✗ Failed to import utils: {e}")
    sys.exit(1)

# Test data folder resolution (same as run_preprocessing.py)
print("\n8. Testing get_data_folder_path()...")

# Test 1: Without arguments (uses BASE_DIR)
print("\n   Test 1: get_data_folder_path() [no args]")
try:
    result = get_data_folder_path()
    print(f"   - Result: {result}")
    print(f"   - Exists: {os.path.exists(result)}")
except Exception as e:
    print(f"   - ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: With project root (as run_preprocessing now does)
print("\n   Test 2: get_data_folder_path(app_root_path=project_root)")
try:
    result = get_data_folder_path(app_root_path=project_root)
    print(f"   - Result: {result}")
    print(f"   - Exists: {os.path.exists(result)}")
except Exception as e:
    print(f"   - ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Direct settings reading
print("\n9. Direct settings.yaml reading:")
settings_path = os.path.join(project_root, "settings.yaml")
print(f"   - Settings path: {settings_path}")
print(f"   - Exists: {os.path.exists(settings_path)}")

if os.path.exists(settings_path):
    try:
        import yaml
        with open(settings_path, 'r') as f:
            settings = yaml.safe_load(f)
        data_folder_value = settings.get('app_config', {}).get('data_folder')
        print(f"   - Raw data_folder from YAML: '{data_folder_value}'")
    except Exception as e:
        print(f"   - Failed to read YAML: {e}")

# Test what run_preprocessing.py's main() would do
print("\n10. Simulating run_preprocessing.py main() logic:")
try:
    # This is the exact logic from the updated run_preprocessing.py
    data_dir = None
    if data_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        
        try:
            data_dir = get_data_folder_path(app_root_path=project_root)
            print(f"   - Resolved data directory: {data_dir}")
        except Exception as e:
            print(f"   - Failed to get data folder: {e}")
            data_dir = os.path.join(project_root, "Data")
            print(f"   - Using fallback: {data_dir}")
    
    print(f"   - Final data_dir: {data_dir}")
    print(f"   - Is directory: {os.path.isdir(data_dir)}")
    
except Exception as e:
    print(f"   - ERROR in simulation: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("END DEBUG")
print("=" * 60)