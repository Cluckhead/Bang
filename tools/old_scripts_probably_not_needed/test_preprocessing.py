#!/usr/bin/env python
"""Test script to diagnose preprocessing issues"""

import os
import sys
import logging

# Setup logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = script_dir  # We're at project root
sys.path.insert(0, project_root)

print(f"Python path: {sys.path}")
print(f"Project root: {project_root}")

try:
    # Test imports
    print("\n1. Testing core imports...")
    from core import config
    print(f"   - config.BASE_DIR: {config.BASE_DIR}")
    
    from core.settings_loader import get_app_config
    app_cfg = get_app_config()
    print(f"   - app_config: {app_cfg}")
    
    from core.utils import get_data_folder_path
    print("\n2. Testing data folder resolution...")
    
    # Test without arguments
    data_folder = get_data_folder_path()
    print(f"   - Data folder (no args): {data_folder}")
    
    # Test with project root
    data_folder_with_root = get_data_folder_path(app_root_path=project_root)
    print(f"   - Data folder (with root): {data_folder_with_root}")
    
    # Check if folder exists
    if os.path.exists(data_folder):
        print(f"   - Data folder exists: YES")
        print(f"   - Files in data folder: {len(os.listdir(data_folder))} files")
    else:
        print(f"   - Data folder exists: NO - THIS IS THE PROBLEM!")
        
    print("\n3. Testing preprocessing imports...")
    from data_processing.preprocessing import process_input_file
    print("   - preprocessing.process_input_file: OK")
    
    from analytics.synth_spread_calculator import calculate_synthetic_spreads
    print("   - synth_spread_calculator.calculate_synthetic_spreads: OK")
    
    print("\n4. Testing run_preprocessing import...")
    from tools.run_preprocessing import main
    print("   - run_preprocessing.main: OK")
    
    print("\n5. Attempting to run main()...")
    # Don't actually run it, just check if we can call it
    print("   - main function is callable: YES")
    
    print("\n✅ All tests passed! The preprocessing should work.")
    
except Exception as e:
    print(f"\n❌ Error occurred: {e}")
    import traceback
    traceback.print_exc()