"""
This module defines the Flask Blueprint for handling security exclusion management.
It provides routes to view the current exclusion list and add new securities
to the list.
"""
import os
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the Blueprint
exclusion_bp = Blueprint('exclusion_bp', __name__, template_folder='../templates')

EXCLUSIONS_FILE = 'exclusions.csv'
# Assuming sec_spread.csv contains the list of all possible securities
# We need to determine the correct file and column name for security IDs
# Let's tentatively use sec_spread.csv and 'Security ID'
SECURITIES_SOURCE_FILE = 'sec_spread.csv' # Adjust if needed
SECURITY_ID_COLUMN = 'Security Name' # Corrected column name

def get_data_path(filename):
    """Constructs the full path to a data file within the DATA_FOLDER."""
    return os.path.join(current_app.config['DATA_FOLDER'], filename)

def load_exclusions():
    """Loads the current list of exclusions from the CSV file."""
    exclusions_path = get_data_path(EXCLUSIONS_FILE)
    try:
        if os.path.exists(exclusions_path) and os.path.getsize(exclusions_path) > 0:
            df = pd.read_csv(exclusions_path, parse_dates=['AddDate', 'EndDate'], dayfirst=False) # Specify date format if needed
            # Ensure correct types after loading
            df['AddDate'] = pd.to_datetime(df['AddDate'], errors='coerce')
            df['EndDate'] = pd.to_datetime(df['EndDate'], errors='coerce')
            df['SecurityID'] = df['SecurityID'].astype(str)
            df['Comment'] = df['Comment'].astype(str)
            df = df.sort_values(by='AddDate', ascending=False)
            return df.to_dict('records')
        else:
            logging.info(f"'{EXCLUSIONS_FILE}' is empty or does not exist. Returning empty list.")
            return []
    except Exception as e:
        logging.error(f"Error loading exclusions from {exclusions_path}: {e}")
        return [] # Return empty list on error

def load_available_securities():
    """Loads the list of available security IDs from the source file."""
    securities_file_path = get_data_path(SECURITIES_SOURCE_FILE)
    try:
        if os.path.exists(securities_file_path):
            # Load only the necessary column
            # Use security_processing logic if more complex loading is needed
            df_securities = pd.read_csv(securities_file_path, usecols=[SECURITY_ID_COLUMN], encoding_errors='replace', on_bad_lines='skip')
            df_securities.dropna(subset=[SECURITY_ID_COLUMN], inplace=True)
            security_ids = df_securities[SECURITY_ID_COLUMN].astype(str).unique().tolist()
            security_ids.sort() # Sort for dropdown consistency
            return security_ids
        else:
            logging.warning(f"Securities source file '{SECURITIES_SOURCE_FILE}' not found at {securities_file_path}.")
            return []
    except KeyError:
        logging.error(f"Column '{SECURITY_ID_COLUMN}' not found in '{SECURITIES_SOURCE_FILE}'. Cannot load available securities.")
        return []
    except Exception as e:
        logging.error(f"Error loading available securities from {securities_file_path}: {e}")
        return []

def add_exclusion(security_id, end_date_str, comment):
    """Adds a new exclusion to the CSV file."""
    exclusions_path = get_data_path(EXCLUSIONS_FILE)
    try:
        # Basic validation
        if not security_id or not comment:
            logging.warning("Attempted to add exclusion with missing SecurityID or Comment.")
            return False, "Security ID and Comment are required."

        add_date = datetime.now().strftime('%Y-%m-%d')
        # Parse end_date, allow it to be empty
        end_date = pd.to_datetime(end_date_str, errors='coerce').strftime('%Y-%m-%d') if end_date_str else ''

        new_exclusion = pd.DataFrame({
            'SecurityID': [str(security_id)],
            'AddDate': [add_date],
            'EndDate': [end_date],
            'Comment': [str(comment)]
        })

        # Append to CSV, create header if file doesn't exist or is empty
        file_exists = os.path.exists(exclusions_path)
        is_empty = file_exists and os.path.getsize(exclusions_path) == 0
        write_header = not file_exists or is_empty

        new_exclusion.to_csv(exclusions_path, mode='a', header=write_header, index=False)
        logging.info(f"Added exclusion for SecurityID: {security_id}")
        return True, "Exclusion added successfully."
    except Exception as e:
        logging.error(f"Error adding exclusion to {exclusions_path}: {e}")
        return False, "An error occurred while saving the exclusion."

def remove_exclusion(security_id_to_remove, add_date_str_to_remove):
    """Removes a specific exclusion entry from the CSV file based on SecurityID and AddDate."""
    exclusions_path = get_data_path(EXCLUSIONS_FILE)
    try:
        if not os.path.exists(exclusions_path) or os.path.getsize(exclusions_path) == 0:
            logging.warning(f"Attempted to remove exclusion, but '{EXCLUSIONS_FILE}' is empty or does not exist.")
            return False, "Exclusion file is empty or missing."

        df = pd.read_csv(exclusions_path)

        # Ensure columns used for matching are strings
        df['SecurityID'] = df['SecurityID'].astype(str)
        # Keep AddDate as string for direct comparison with the string from the form
        df['AddDate'] = df['AddDate'].astype(str)
        security_id_to_remove = str(security_id_to_remove)

        original_count = len(df)

        # Filter out the row(s) to remove
        # Match both SecurityID and the AddDate string
        df_filtered = df[~((df['SecurityID'] == security_id_to_remove) & (df['AddDate'] == add_date_str_to_remove))]

        if len(df_filtered) == original_count:
            logging.warning(f"Exclusion entry for SecurityID '{security_id_to_remove}' with AddDate '{add_date_str_to_remove}' not found for removal.")
            return False, "Exclusion entry not found."

        # Overwrite the CSV with the filtered data
        df_filtered.to_csv(exclusions_path, index=False)
        logging.info(f"Removed exclusion entry for SecurityID: {security_id_to_remove}, AddDate: {add_date_str_to_remove}")
        return True, "Exclusion removed successfully."

    except Exception as e:
        logging.error(f"Error removing exclusion from {exclusions_path}: {e}")
        return False, "An error occurred while removing the exclusion."

@exclusion_bp.route('/exclusions', methods=['GET', 'POST'])
def manage_exclusions():
    """
    Handles viewing and adding security exclusions.
    GET: Displays the list of current exclusions and the form to add new ones.
    POST: Processes the form submission to add a new exclusion.
    """
    message = None
    message_type = 'info' # Can be 'success' or 'error'

    if request.method == 'POST':
        security_id = request.form.get('security_id')
        end_date_str = request.form.get('end_date')
        comment = request.form.get('comment')

        success, msg = add_exclusion(security_id, end_date_str, comment)
        if success:
            # Redirect to the same page using GET to prevent form resubmission
            return redirect(url_for('exclusion_bp.manage_exclusions', _external=True))
        else:
            message = msg
            message_type = 'error'
            # Fall through to render the page again with the error message

    # For both GET requests and POST failures, load data and render template
    current_exclusions = load_exclusions()
    available_securities = load_available_securities()

    return render_template('exclusions_page.html',
                           exclusions=current_exclusions,
                           available_securities=available_securities,
                           message=message,
                           message_type=message_type)

@exclusion_bp.route('/exclusions/remove', methods=['POST'])
def remove_exclusion_route():
    """Handles the POST request to remove an exclusion."""
    security_id = request.form.get('security_id')
    add_date_str = request.form.get('add_date') # Get AddDate as string

    if not security_id or not add_date_str:
        # Handle missing identifiers (shouldn't happen with hidden fields but good practice)
        # Redirect back with an error message (using flash or query params)
        logging.warning("Remove exclusion attempt missing SecurityID or AddDate.")
        # For simplicity, redirect back to the main page; flash messages would be better
        return redirect(url_for('exclusion_bp.manage_exclusions'))

    success, msg = remove_exclusion(security_id, add_date_str)

    # Regardless of success/failure, redirect back to the main exclusions page.
    # Consider using flash messages to display the success/error message after redirect.
    # For now, the message `msg` is logged but not shown to the user on redirect.
    return redirect(url_for('exclusion_bp.manage_exclusions')) 