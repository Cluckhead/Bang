# Purpose: Script to populate attribution cache after CSV files are created/updated.
# Can be run manually or integrated into data pipeline after attribution file creation.
import os
import sys
import time
import argparse
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

from views.attribution_cache import AttributionCache
from core.utils import get_data_folder_path

def main():
    parser = argparse.ArgumentParser(description='Populate attribution cache for performance optimization')
    parser.add_argument('--fund', type=str, help='Specific fund code to cache (default: all funds)')
    parser.add_argument('--data-folder', type=str, help='Override data folder path')
    parser.add_argument('--clear', action='store_true', help='Clear cache before populating')
    parser.add_argument('--force', action='store_true', help='Force refresh even if cache exists')
    
    args = parser.parse_args()
    
    # Get data folder
    data_folder = args.data_folder or get_data_folder_path()
    
    # Initialize cache
    cache = AttributionCache(data_folder)
    
    # Clear cache if requested
    if args.clear:
        print("Clearing existing cache...")
        cache.clear_cache()
    
    # Get funds to process
    if args.fund:
        funds = [args.fund]
    else:
        # Get all available funds by scanning for att_factors_*.csv files
        funds = []
        for filename in os.listdir(data_folder):
            if filename.startswith("att_factors_") and filename.endswith(".csv"):
                fund_code = filename[12:-4]  # Extract fund code
                if fund_code:
                    funds.append(fund_code)
        funds = sorted(funds)
    
    if not funds:
        print("No attribution files found to cache.")
        return
    
    print(f"Found {len(funds)} fund(s) to process: {', '.join(funds)}")
    
    # Process each fund
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    for fund in funds:
        print(f"\nProcessing {fund}...")
        
        try:
            # Check if cache exists and is valid
            if not args.force:
                # Try loading cache to see if it's valid
                test_cache = cache.load_cache(fund, 'daily_l0')
                if test_cache is not None:
                    print(f"  Cache already valid for {fund}, skipping (use --force to refresh)")
                    continue
            
            # Refresh cache
            if cache.refresh_cache(fund):
                print(f"  ✓ Successfully cached aggregates for {fund}")
                success_count += 1
            else:
                print(f"  ✗ Failed to cache {fund} - source file not found")
                error_count += 1
                
        except Exception as e:
            print(f"  ✗ Error processing {fund}: {str(e)}")
            error_count += 1
    
    # Summary
    total_time = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"Cache population complete!")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {error_count}")
    print(f"  Cache location: {cache.cache_folder}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main() 