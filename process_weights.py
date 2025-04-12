# process_weights.py
"""
This script processes weight files by replacing duplicate headers with dates from Dates.csv.
It directly processes pre_w_*.csv files to create corresponding w_*.csv files.
"""

import os
import logging
from weight_processing import process_weight_file

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Process all weight files in the Data directory."""
    # Get the current directory and data directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, 'Data')
    
    # Path to Dates.csv
    dates_path = os.path.join(data_dir, 'Dates.csv')
    
    if not os.path.exists(dates_path):
        logger.error(f"Dates.csv not found at {dates_path}. Cannot proceed.")
        return
    
    # List of weight files to process
    weight_files = [
        ('pre_w_Bench.csv', 'w_Bench.csv'),
        ('pre_w_Funds.csv', 'w_Funds.csv'),
        ('pre_w_secs.csv', 'w_secs.csv')
    ]
    
    # Process each weight file
    for input_file, output_file in weight_files:
        input_path = os.path.join(data_dir, input_file)
        output_path = os.path.join(data_dir, output_file)
        
        if os.path.exists(input_path):
            logger.info(f"Processing weight file: {input_path} -> {output_path}")
            process_weight_file(input_path, output_path, dates_path)
        else:
            logger.warning(f"Input file not found: {input_path}")

if __name__ == "__main__":
    main() 