# Purpose: Batch preprocessing script for Simple Data Checker.
# This script finds all pre_*.csv and pre_w_*.csv files in the data folder, processes them using preprocessing.process_input_file,
# and writes the output files (sec_*.csv, w_*.csv) for downstream analysis. Intended for use as a standalone or CLI utility.

import os
import logging
import sys

# Optional: import project-wide configuration – currently unused but left for future extension
import config  # noqa: F401

from utils import get_data_folder_path
from preprocessing import process_input_file

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logger.info("--- Starting batch preprocessing ---")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = get_data_folder_path(app_root_path=script_dir)
        logger.info(f"Using data directory: {data_dir}")
        if not os.path.isdir(data_dir):
            logger.error(f"Data directory not found or is not a directory: {data_dir}. Cannot proceed.")
            sys.exit(1)
        # Use a single central Dates file expected to live at the *root* of the data folder.
        # Note: capitalisation chosen to align with most modules ("Dates.csv").
        dates_path = os.path.join(data_dir, "Dates.csv")
        config_dict = {}  # Placeholder for future config

        # -----------------------------------------------------------------
        # Recursively traverse the data directory to locate *all* pre_*.csv
        # files (including those nested in sub-directories).
        # -----------------------------------------------------------------
        for root, _dirs, files in os.walk(data_dir):
            for filename in files:
                if not (filename.lower().startswith("pre_") and filename.lower().endswith(".csv")):
                    continue  # Skip non-pre files quickly

                input_path = os.path.join(root, filename)

                # Determine output file name according to naming convention
                if filename.lower().startswith("pre_w_"):
                    output_filename = filename.replace("pre_w_", "w_", 1)
                else:
                    output_filename = filename.replace("pre_", "sec_", 1)

                output_path = os.path.join(root, output_filename)

                logger.info(
                    f"Processing '{input_path}' -> '{output_path}' (dates from '{dates_path}')"
                )

                process_input_file(input_path, output_path, dates_path, config_dict)
        logger.info("--- Batch preprocessing finished ---")
    except Exception as e:
        logger.error(f"Error in run_preprocessing: {e}", exc_info=True)
        sys.exit(1) 