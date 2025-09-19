# Purpose: Batch preprocessing script for Simple Data Checker.
# This script finds all pre_*.csv and pre_w_*.csv files in the data folder, processes them using preprocessing.process_input_file,
# and writes the output files (sec_*.csv, w_*.csv) for downstream analysis. Intended for use as a standalone or CLI utility.

import os
import logging
import sys

# Add project root to path for imports when running as standalone script
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)  # Go up from tools/ to project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import from refactored structure
from core import config  # noqa: F401
from core.io_lock import install_pandas_file_locks
from core.utils import get_data_folder_path
from data_processing.preprocessing import process_input_file

logger = logging.getLogger(__name__)

# Ensure file-locked CSV I/O is installed when running standalone/CLI
try:
    install_pandas_file_locks()
except Exception:
    pass

# -----------------------------------------------------------------------------
# Public entry-point callable
# -----------------------------------------------------------------------------


def main(data_dir: str | None = None, *, config_dict: dict | None = None, quiet: bool = False) -> None:
    """Batch-process all *pre_*.csv files under *data_dir*.

    Parameters
    ----------
    data_dir
        Absolute path to the folder that should be scanned for *pre_*.csv /
        *pre_w_*.csv files.  If *None* the function resolves the data folder
        via :pyfunc:`utils.get_data_folder_path`, using the data_folder setting
        from settings.yaml relative to the project root.
    config_dict
        Optional dictionary for future configuration hooks.  Currently unused
        but kept for forward-compatibility with the full cleanup plan.
    quiet
        If True, reduces logging verbosity to show only essential information.
    """

    if config_dict is None:
        config_dict = {}

    logger = logging.getLogger(__name__)

    # Reduce logging verbosity for preprocessing module if quiet mode is enabled
    if quiet:
        logging.getLogger('data_processing.preprocessing').setLevel(logging.WARNING)

    # ---------------------------------------------------------------------
    # Resolve *data_dir* if caller did not supply it
    # ---------------------------------------------------------------------
    if data_dir is None:
        # Get the project root directory (parent of tools/)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)  # Go up from tools/ to project root
        
        try:
            # Pass the project root to ensure correct relative path resolution
            data_dir = get_data_folder_path(app_root_path=project_root)
            logger.info(f"Resolved data directory from settings: {data_dir}")
        except Exception as e:
            # Fallback to a default Data folder relative to project root
            logger.warning(f"Failed to get data folder from settings: {e}")
            data_dir = os.path.join(project_root, "Data")
            logger.info(f"Using fallback data directory: {data_dir}")

    logger.info(f"Using data directory: {data_dir}")

    if not os.path.isdir(data_dir):
        raise FileNotFoundError(
            f"Data directory not found or is not a directory: {data_dir}"
        )

    # Central Dates file
    dates_path = os.path.join(data_dir, "Dates.csv")

    processed_files: list[str] = []
    total_files = 0

    # Count total files first for progress reporting
    for root, _dirs, files in os.walk(data_dir):
        for filename in files:
            if (filename.lower().startswith("pre_") and filename.lower().endswith(".csv")):
                total_files += 1

    if total_files == 0:
        logger.info("No pre_*.csv files found to process.")
        return

    logger.info(f"Found {total_files} files to process...")
    
    # Recursively walk the data directory
    file_count = 0
    for root, _dirs, files in os.walk(data_dir):
        for filename in files:
            if not (
                filename.lower().startswith("pre_")
                and filename.lower().endswith(".csv")
            ):
                continue

            file_count += 1
            input_path = os.path.join(root, filename)

            if filename.lower().startswith("pre_w_"):
                output_filename = filename.replace("pre_w_", "w_", 1)
            else:
                # Strip the 'pre_' prefix only. If the remainder already starts
                # with 'sec_' this will naturally produce 'sec_*.csv'; otherwise
                # it simply removes the preprocessing marker without duplicating
                # the 'sec_' prefix.
                output_filename = filename[len("pre_") :]

            output_path = os.path.join(root, output_filename)

            # Only log progress every 50 files to reduce noise
            if file_count % 50 == 0 or file_count == total_files:
                logger.info(f"Progress: {file_count}/{total_files} files processed")

            process_input_file(input_path, output_path, dates_path, config_dict)

            processed_files.append(output_path)

    logger.info(
        "Batch preprocessing finished. Created/updated %s file(s).",
        len(processed_files),
    )
    
    # Calculate synthetic spreads after preprocessing
    logger.info("--- Starting synthetic spread calculation ---")
    try:
        from analytics.synth_spread_calculator import calculate_synthetic_spreads
        calculate_synthetic_spreads(data_dir)
        logger.info("--- Synthetic spread calculation completed ---")
    except Exception as e:
        logger.error(f"Error calculating synthetic spreads: {e}", exc_info=True)


# -----------------------------------------------------------------------------
# CLI entry-point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    logger.info("--- Starting batch preprocessing (CLI) ---")
    
    # Debug info
    logger.info(f"Running from: {os.path.abspath(__file__)}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    try:
        # Enable quiet mode by default to reduce noise
        main(quiet=True)
    except FileNotFoundError as e:
        logger.error(f"Data folder not found: {e}")
        logger.error("Please check that the 'data_folder' setting in settings.yaml points to a valid directory")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error in run_preprocessing (CLI): {e}", exc_info=True)
        sys.exit(1)
    logger.info("--- Batch preprocessing finished (CLI) ---")
