# Purpose: Test script to verify attribution pages handle missing att_ files gracefully.
# This script temporarily renames attribution files and tests the error handling.

import os
import shutil
import tempfile
import requests
from pathlib import Path
import time

def test_attribution_pages_with_missing_files():
    """Test that attribution pages don't crash when att_ files are missing."""
    
    # Configuration
    base_url = "http://localhost:5000"  # Adjust if your Flask app runs on different port
    data_folder = Path("Data")
    
    # Find all attribution files
    att_files = list(data_folder.glob("att_factors_*.csv"))
    
    if not att_files:
        print("No attribution files found to test with.")
        return
    
    print(f"Found {len(att_files)} attribution files to test with")
    
    # Create backup directory
    backup_dir = Path(tempfile.mkdtemp(prefix="att_backup_"))
    print(f"Backing up files to: {backup_dir}")
    
    try:
        # Backup all attribution files
        for att_file in att_files:
            shutil.copy2(att_file, backup_dir / att_file.name)
            print(f"Backed up: {att_file.name}")
        
        # Remove attribution files temporarily
        for att_file in att_files:
            att_file.unlink()
            print(f"Temporarily removed: {att_file.name}")
        
        # Test all attribution endpoints
        test_endpoints = [
            "/attribution/summary",
            "/attribution/charts", 
            "/attribution/radar",
            "/attribution/security",
            "/attribution/security/timeseries?fund=TEST&isin=TEST123456"
        ]
        
        print("\nTesting attribution endpoints with missing files...")
        for endpoint in test_endpoints:
            try:
                response = requests.get(f"{base_url}{endpoint}", timeout=10)
                status = "✅ PASS" if response.status_code == 200 else f"❌ FAIL ({response.status_code})"
                print(f"{endpoint}: {status}")
                
                # Check for common error indicators in response
                if response.status_code == 200:
                    content = response.text.lower()
                    if "internal server error" in content or "500" in content:
                        print(f"  ⚠️  Warning: Page loaded but may contain errors")
                    elif "no attribution" in content or "not found" in content:
                        print(f"  ✅ Good: Error handled gracefully")
                        
            except requests.exceptions.RequestException as e:
                print(f"{endpoint}: ❌ FAIL (Connection error: {e})")
                
        print("\nTest completed. Check the results above.")
        
    finally:
        # Restore all files
        print("\nRestoring attribution files...")
        for backup_file in backup_dir.glob("att_factors_*.csv"):
            target_file = data_folder / backup_file.name
            shutil.copy2(backup_file, target_file)
            print(f"Restored: {backup_file.name}")
        
        # Clean up backup directory
        shutil.rmtree(backup_dir)
        print(f"Cleaned up backup directory: {backup_dir}")

if __name__ == "__main__":
    print("Attribution Missing Files Test")
    print("=" * 40)
    print("This script will temporarily remove attribution files and test error handling.")
    print("Make sure your Flask app is running on http://localhost:5000")
    
    confirm = input("\nProceed with test? (y/N): ").strip().lower()
    if confirm == 'y':
        test_attribution_pages_with_missing_files()
    else:
        print("Test cancelled.") 