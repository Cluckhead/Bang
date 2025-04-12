# process_w_secs.py
"""
This script specifically processes the pre_w_secs.csv file to create w_secs.csv
with dates from Dates.csv as the column headers for the weight values.
"""

import os
import pandas as pd
import logging

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_securities_file():
    """Process the pre_w_secs.csv file to replace weight columns with dates."""
    # Get paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, 'Data')
    input_path = os.path.join(data_dir, 'pre_w_secs.csv')
    output_path = os.path.join(data_dir, 'w_secs.csv')
    dates_path = os.path.join(data_dir, 'Dates.csv')
    
    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return
        
    if not os.path.exists(dates_path):
        logger.error(f"Dates file not found: {dates_path}")
        return
    
    try:
        # Load the dates
        dates_df = pd.read_csv(dates_path)
        dates = dates_df['Date'].tolist()
        logger.info(f"Loaded {len(dates)} dates from {dates_path}")
        
        # Reverse the dates so newest is on the right
        dates = dates[::-1]
        logger.info(f"Reversed dates order, newest date will be on the right")
        
        # Read the securities data with explicit encoding
        df = pd.read_csv(input_path, encoding='utf-8', encoding_errors='replace')
        logger.info(f"Read securities file with {len(df)} rows and {len(df.columns)} columns")
        
        # Get column names
        columns = df.columns.tolist()
        
        # Assuming the first 10 columns are metadata that we want to keep
        # (Typically: ISIN, Name, Fund, Type, Description, Rating, Bloomberg, Exchange, Country, Currency)
        metadata_cols = columns[:10]
        logger.info(f"Keeping metadata columns: {metadata_cols}")
        
        # All columns after index 9 are weight values that should be replaced with dates
        weight_cols = columns[10:]
        logger.info(f"Found {len(weight_cols)} weight columns to replace with dates")
        
        # Check if we have enough dates
        if len(weight_cols) > len(dates):
            logger.warning(f"Not enough dates ({len(dates)}) for all weight columns ({len(weight_cols)}). Using available dates only.")
            dates = dates[:len(weight_cols)]
        elif len(weight_cols) < len(dates):
            logger.warning(f"More dates ({len(dates)}) than weight columns ({len(weight_cols)}). Using first {len(weight_cols)} dates.")
            dates = dates[:len(weight_cols)]
        
        # Create new column names (metadata + dates)
        new_columns = metadata_cols + dates
        
        # Replace the column names
        df.columns = new_columns
        
        # Save the result (make sure no other program has the file open)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Removed existing file: {output_path}")
            except PermissionError:
                logger.error(f"Cannot delete {output_path} - it may be open in another program.")
                return
                
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Successfully created {output_path} with {len(df)} rows")
        
    except Exception as e:
        logger.error(f"Error processing securities file: {e}", exc_info=True)

if __name__ == "__main__":
    process_securities_file() 