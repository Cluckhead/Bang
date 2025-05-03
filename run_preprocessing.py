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

# -----------------------------------------------------------------------------
# Public entry-point callable
# -----------------------------------------------------------------------------

def main(data_dir: str | None = None, *, config_dict: dict | None = None) -> None:
    """Batch-process all *pre_*.csv files under *data_dir*.

    Parameters
    ----------
    data_dir
        Absolute path to the folder that should be scanned for *pre_*.csv /
        *pre_w_*.csv files.  If *None* the function resolves the data folder
        via :pyfunc:`utils.get_data_folder_path`, using the directory that
        contains *run_preprocessing.py* as *app_root_path*.
    config_dict
        Optional dictionary for future configuration hooks.  Currently unused
        but kept for forward-compatibility with the full cleanup plan.
    """

    if config_dict is None:
        config_dict = {}

    logger = logging.getLogger(__name__)

    # ---------------------------------------------------------------------
    # Resolve *data_dir* if caller did not supply it
    # ---------------------------------------------------------------------
    if data_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = get_data_folder_path(app_root_path=script_dir)

    logger.info(f"Using data directory: {data_dir}")

    if not os.path.isdir(data_dir):
        raise FileNotFoundError(
            f"Data directory not found or is not a directory: {data_dir}"
        )

    # Central Dates file
    dates_path = os.path.join(data_dir, "Dates.csv")

    processed_files: list[str] = []

    # Recursively walk the data directory
    for root, _dirs, files in os.walk(data_dir):
        for filename in files:
            if not (filename.lower().startswith("pre_") and filename.lower().endswith(".csv")):
                continue

            input_path = os.path.join(root, filename)

            if filename.lower().startswith("pre_w_"):
                output_filename = filename.replace("pre_w_", "w_", 1)
            else:
                # Strip the 'pre_' prefix only. If the remainder already starts
                # with 'sec_' this will naturally produce 'sec_*.csv'; otherwise
                # it simply removes the preprocessing marker without duplicating
                # the 'sec_' prefix.
                output_filename = filename[len("pre_"):]

            output_path = os.path.join(root, output_filename)

            logger.info(
                f"Processing '{input_path}' -> '{output_path}' (dates from '{dates_path}')"
            )

            process_input_file(input_path, output_path, dates_path, config_dict)

            processed_files.append(output_path)

    logger.info("Batch preprocessing finished. Created/updated %s file(s).", len(processed_files))

# -----------------------------------------------------------------------------
# CLI entry-point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logger.info("--- Starting batch preprocessing (CLI) ---")
    try:
        main()
    except Exception as e:
        logger.error(f"Error in run_preprocessing (CLI): {e}", exc_info=True)
        sys.exit(1)
    logger.info("--- Batch preprocessing finished (CLI) ---") 