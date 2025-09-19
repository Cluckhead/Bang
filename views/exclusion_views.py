"""
# Purpose: This module defines the Flask Blueprint for handling security exclusion management.
# It provides routes to view the current exclusion list and add new securities to the list.
# It uses a dynamic data_folder_path to locate 'exclusions.csv', 'reference.csv', and 'users.csv'.
# Major update: The available securities list for exclusions is now loaded from reference.csv
# and includes ISIN, Security Name, CCY, Security Sub Type, and Country Of Risk for client-side filtering.
"""

import os
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from datetime import datetime
import logging

# Logging is now handled centrally by the Flask app factory in app.py
logger = logging.getLogger(__name__)

# Define the Blueprint
exclusion_bp = Blueprint("exclusion_bp", __name__, template_folder="../templates")

EXCLUSIONS_FILE = "exclusions.csv"
# Separate CSV for multiple timestamped comments per exclusion
COMMENTS_FILE = "exclusion_comments.csv"
# Assuming sec_spread.csv contains the list of all possible securities
# We need to determine the correct file and column name for security IDs
# Let's tentatively use sec_spread.csv and 'Security ID'
SECURITIES_SOURCE_FILE = "sec_spread.csv"  # Adjust if needed
SECURITY_ID_COLUMN = "Security Name"  # Corrected column name


def load_exclusions(data_folder_path: str):
    """Loads the current list of exclusions from the CSV file.

    Args:
        data_folder_path (str): The absolute path to the data folder.

    Returns:
        list[dict]: A list of dictionaries representing the exclusions, or [] if error.
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to load_exclusions.")
        return []
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)
    try:
        if os.path.exists(exclusions_path) and os.path.getsize(exclusions_path) > 0:
            df = pd.read_csv(
                exclusions_path, parse_dates=["AddDate", "EndDate"], dayfirst=False
            )  # Specify date format if needed
            # Ensure correct types after loading
            df["AddDate"] = pd.to_datetime(df["AddDate"], errors="coerce")
            df["EndDate"] = pd.to_datetime(df["EndDate"], errors="coerce")
            df["SecurityID"] = df["SecurityID"].astype(str)
            # Support both legacy 'Comment' and new 'Reason' column naming
            if "Reason" in df.columns:
                df["Reason"] = df["Reason"].astype(str)
            elif "Comment" in df.columns:
                df = df.rename(columns={"Comment": "Reason"})
                df["Reason"] = df["Reason"].astype(str)
            df = df.sort_values(by="AddDate", ascending=False)
            return df.to_dict("records")
        else:
            logger.info(
                f"'{EXCLUSIONS_FILE}' is empty or does not exist. Returning empty list."
            )
            return []
    except Exception as e:
        logger.error(f"Error loading exclusions from {exclusions_path}: {e}")
        return []  # Return empty list on error


def load_available_securities(data_folder_path: str):
    """
    Loads the list of available securities from reference.csv, including ISIN, Security Name,
    Position Currency, Security Sub Type, and Country Of Risk. This supports client-side filtering and
    searching for the exclusions page.

    Args:
        data_folder_path (str): The absolute path to the data folder.

    Returns:
        list[dict]: A list of dicts, each with keys: ISIN, Security Name, Position Currency, Security Sub Type, Country Of Risk.
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to load_available_securities.")
        return []
    reference_file_path = os.path.join(data_folder_path, "reference.csv")
    try:
        if os.path.exists(reference_file_path):
            # Only load the required columns for performance
            usecols = [
                "ISIN",
                "Security Name",
                "Position Currency",
                "Security Sub Type",
                "Country Of Risk",
            ]
            df = pd.read_csv(
                reference_file_path,
                usecols=usecols,
                encoding_errors="replace",
                on_bad_lines="skip",
            )
            df = df.dropna(subset=["ISIN", "Security Name"])
            # Remove duplicates by ISIN (keep first occurrence)
            df = df.drop_duplicates(subset=["ISIN"])
            # Alias Position Currency to CCY for template simplicity
            df["CCY"] = df["Position Currency"]
            # Convert to list of dicts for template/JS
            securities = df.to_dict("records")
            # Sort by ISIN for consistency
            securities.sort(key=lambda x: x["ISIN"])
            return securities
        else:
            logger.warning(f"reference.csv not found at {reference_file_path}.")
            return []
    except Exception as e:
        logger.error(
            f"Error loading available securities from {reference_file_path}: {e}"
        )
        return []


def load_users(data_folder_path: str):
    """
    Loads the list of users from users.csv for the 'Added By' dropdown.
    Returns a list of user names (strings).
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to load_users.")
        return []
    users_file_path = os.path.join(data_folder_path, "users.csv")
    try:
        if os.path.exists(users_file_path):
            df = pd.read_csv(users_file_path)
            if "Name" in df.columns:
                users = df["Name"].dropna().astype(str).tolist()
                return users
            else:
                logger.warning("'Name' column not found in users.csv.")
                return []
        else:
            logger.warning(f"users.csv not found at {users_file_path}.")
            return []
    except Exception as e:
        logger.error(f"Error loading users from {users_file_path}: {e}")
        return []


def initialize_exclusions_file(data_folder_path: str) -> bool:
    """
    Initializes the exclusions CSV file with the correct header format if it doesn't exist.
    
    Args:
        data_folder_path (str): The absolute path to the data folder.
        
    Returns:
        bool: True if file was created or already exists, False on error.
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to initialize_exclusions_file.")
        return False
        
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)
    
    try:
        # Ensure the data folder exists
        os.makedirs(data_folder_path, exist_ok=True)
        
        # Check if file exists and is not empty
        if os.path.exists(exclusions_path) and os.path.getsize(exclusions_path) > 0:
            logger.debug(f"Exclusions file already exists at {exclusions_path}")
            return True
            
        # Create the file with proper header
        empty_df = pd.DataFrame(columns=["SecurityID", "AddDate", "EndDate", "Reason", "User"])
        empty_df.to_csv(exclusions_path, index=False)
        logger.info(f"Created new exclusions file at {exclusions_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing exclusions file at {exclusions_path}: {e}")
        return False


def add_exclusion(data_folder_path: str, security_id, end_date_str, reason, user):
    """Adds a new exclusion to the CSV file, now including the user who added it."""
    if not data_folder_path:
        logger.error("No data_folder_path provided to add_exclusion.")
        return False, "Internal Server Error: Data folder path not configured."
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)
    try:
        # Basic validation
        if not security_id or not reason or not user:
            logger.warning(
                "Attempted to add exclusion with missing SecurityID, Reason, or User."
            )
            return False, "Security ID, Reason, and User are required."

        add_date = datetime.now().strftime("%Y-%m-%d")
        # Parse end_date, allow it to be empty
        end_date = (
            pd.to_datetime(end_date_str, errors="coerce").strftime("%Y-%m-%d")
            if end_date_str
            else ""
        )

        new_exclusion = pd.DataFrame(
            {
                "SecurityID": [str(security_id)],
                "AddDate": [add_date],
                "EndDate": [end_date],
                "Reason": [str(reason)],
                "User": [str(user)],
            }
        )

        # Append to CSV, create header if file doesn't exist or is empty
        file_exists = os.path.exists(exclusions_path)
        is_empty = file_exists and os.path.getsize(exclusions_path) == 0
        write_header = not file_exists or is_empty

        new_exclusion.to_csv(
            exclusions_path, mode="a", header=write_header, index=False
        )
        logger.info(f"Added exclusion for SecurityID: {security_id} by {user}")
        return True, "Exclusion added successfully."
    except Exception as e:
        logger.error(f"Error adding exclusion to {exclusions_path}: {e}")
        return False, "An error occurred while saving the exclusion."


def remove_exclusion(
    data_folder_path: str, security_id_to_remove, add_date_str_to_remove
):
    """Removes a specific exclusion entry from the CSV file based on SecurityID and AddDate.

    Args:
        data_folder_path (str): The absolute path to the data folder.
        security_id_to_remove:
        add_date_str_to_remove:

    Returns:
        tuple[bool, str]: (Success status, Message)
    """
    if not data_folder_path:
        logger.error("No data_folder_path provided to remove_exclusion.")
        return False, "Internal Server Error: Data folder path not configured."
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)
    try:
        if not os.path.exists(exclusions_path) or os.path.getsize(exclusions_path) == 0:
            logger.warning(
                f"Attempted to remove exclusion, but '{EXCLUSIONS_FILE}' is empty or does not exist."
            )
            return False, "Exclusion file is empty or missing."

        df = pd.read_csv(exclusions_path)

        # Ensure columns used for matching are strings
        df["SecurityID"] = df["SecurityID"].astype(str)
        # Keep AddDate as string for direct comparison with the string from the form
        df["AddDate"] = df["AddDate"].astype(str)
        security_id_to_remove = str(security_id_to_remove)

        original_count = len(df)

        # Filter out the row(s) to remove
        # Match both SecurityID and the AddDate string
        df_filtered = df[
            ~(
                (df["SecurityID"] == security_id_to_remove)
                & (df["AddDate"] == add_date_str_to_remove)
            )
        ]

        if len(df_filtered) == original_count:
            logger.warning(
                f"Exclusion entry for SecurityID '{security_id_to_remove}' with AddDate '{add_date_str_to_remove}' not found for removal."
            )
            return False, "Exclusion entry not found."

        # Overwrite the CSV with the filtered data
        df_filtered.to_csv(exclusions_path, index=False)
        logger.info(
            f"Removed exclusion entry for SecurityID: {security_id_to_remove}, AddDate: {add_date_str_to_remove}"
        )
        return True, "Exclusion removed successfully."

    except Exception as e:
        logger.error(f"Error removing exclusion from {exclusions_path}: {e}")
        return False, "An error occurred while removing the exclusion."


# ---------------------------------
# New helper functions for editing
# ---------------------------------


def add_exclusion_comment(
    data_folder_path: str,
    security_id: str,
    add_date_str: str,
    comment_text: str,
    user: str,
):
    """Appends a timestamped comment for an existing exclusion to COMMENTS_FILE.

    Args:
        data_folder_path: Absolute data folder.
        security_id: SecurityID key of the exclusion.
        add_date_str: Original AddDate (YYYY-MM-DD) that identifies the exclusion.
        comment_text: Free-text reason/comment.
        user: User name submitting the comment.

    Returns:
        tuple(bool, str): Success status and message.
    """
    if not (data_folder_path and security_id and add_date_str and comment_text and user):
        return False, "All fields are required to add a comment."

    comments_path = os.path.join(data_folder_path, COMMENTS_FILE)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        new_row = pd.DataFrame(
            {
                "SecurityID": [str(security_id)],
                "AddDate": [add_date_str],
                "Timestamp": [timestamp],
                "User": [str(user)],
                "Reason": [str(comment_text)],
            }
        )

        file_exists = os.path.exists(comments_path)
        new_row.to_csv(comments_path, mode="a", header=not file_exists, index=False)
        return True, "Comment added."
    except Exception as e:
        logger.error(f"Error appending comment to {comments_path}: {e}")
        return False, "Failed to save comment."


def load_exclusion_comments(data_folder_path: str, security_id: str, add_date_str: str):
    """Loads all comments for a given exclusion, sorted by timestamp desc."""
    if not data_folder_path:
        return []

    comments_path = os.path.join(data_folder_path, COMMENTS_FILE)
    if not os.path.exists(comments_path):
        return []

    try:
        df = pd.read_csv(comments_path, parse_dates=["Timestamp"], dayfirst=False)
        # Filter by keys
        df_filtered = df[
            (df["SecurityID"].astype(str) == str(security_id))
            & (df["AddDate"].astype(str) == str(add_date_str))
        ].copy()
        df_filtered = df_filtered.sort_values(by="Timestamp", ascending=False)
        return df_filtered.to_dict("records")
    except Exception as e:
        logger.error(f"Error loading comments from {comments_path}: {e}")
        return []


def update_exclusion_end_date(
    data_folder_path: str, security_id: str, add_date_str: str, new_end_date_str: str
):
    """Updates the EndDate of an existing exclusion row."""
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)

    if not os.path.exists(exclusions_path):
        return False, "Exclusions file not found."

    try:
        df = pd.read_csv(exclusions_path)
        mask = (df["SecurityID"].astype(str) == str(security_id)) & (
            df["AddDate"].astype(str) == str(add_date_str)
        )

        if not mask.any():
            return False, "Exclusion entry not found."

        # Update EndDate
        df.loc[mask, "EndDate"] = (
            pd.to_datetime(new_end_date_str, errors="coerce").strftime("%Y-%m-%d")
            if new_end_date_str
            else ""
        )

        df.to_csv(exclusions_path, index=False)
        return True, "End date updated."
    except Exception as e:
        logger.error(f"Error updating exclusion end date in {exclusions_path}: {e}")
        return False, "Failed to update end date."


def update_exclusion_entry(
    data_folder_path: str,
    security_id: str,
    add_date_str: str,
    new_end_date_str: str | None = None,
    new_reason: str | None = None,
) -> tuple[bool, str]:
    """Updates EndDate and/or Reason of an existing exclusion row.

    Only the provided fields are modified; supply None to leave unchanged.
    """
    exclusions_path = os.path.join(data_folder_path, EXCLUSIONS_FILE)

    if not os.path.exists(exclusions_path):
        return False, "Exclusions file not found."

    try:
        df = pd.read_csv(exclusions_path)
        mask = (df["SecurityID"].astype(str) == str(security_id)) & (
            df["AddDate"].astype(str) == str(add_date_str)
        )

        if not mask.any():
            return False, "Exclusion entry not found."

        # Update EndDate if provided
        if new_end_date_str is not None:
            df.loc[mask, "EndDate"] = (
                pd.to_datetime(new_end_date_str, errors="coerce").strftime("%Y-%m-%d")
                if new_end_date_str
                else ""
            )

        # Update Reason if provided
        if new_reason is not None:
            df.loc[mask, "Reason"] = str(new_reason)

        df.to_csv(exclusions_path, index=False)
        return True, "Exclusion updated."
    except Exception as e:
        logger.error(f"Error updating exclusion in {exclusions_path}: {e}")
        return False, "Failed to update exclusion."


@exclusion_bp.route("/exclusions", methods=["GET", "POST"])
def manage_exclusions():
    """
    Handles viewing and adding security exclusions.
    GET: Displays the list of current exclusions and the form to add new ones.
    POST: Processes the form submission to add a new exclusion.
    """
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        return "Internal Server Error: Data folder not configured", 500

    # Initialize exclusions file if it doesn't exist
    initialize_exclusions_file(data_folder)

    message = None
    message_type = "info"  # Can be 'success' or 'error'

    if request.method == "POST":
        security_id = request.form.get("security_id")
        end_date_str = request.form.get("end_date")
        reason = request.form.get("reason")
        user = request.form.get("user")

        # Pass the absolute data_folder path to the helper function
        success, msg = add_exclusion(
            data_folder, security_id, end_date_str, reason, user
        )
        if success:
            # Redirect to the same page using GET to prevent form resubmission
            return redirect(url_for("exclusion_bp.manage_exclusions", _external=True))
        else:
            message = msg
            message_type = "error"
            # Fall through to render the page again with the error message

    # For both GET requests and POST failures, load data and render template
    # Pass the absolute data_folder path to the helper functions
    current_exclusions = load_exclusions(data_folder)
    available_securities = load_available_securities(data_folder)
    users = load_users(data_folder)

    return render_template(
        "exclusions_page.html",
        exclusions=current_exclusions,
        available_securities=available_securities,
        users=users,
        message=message,
        message_type=message_type,
    )


@exclusion_bp.route("/exclusions/remove", methods=["POST"])
def remove_exclusion_route():
    """Handles the POST request to remove an exclusion."""
    # Retrieve the configured absolute data folder path
    data_folder = current_app.config["DATA_FOLDER"]
    if not data_folder:
        current_app.logger.error("DATA_FOLDER is not configured in the application.")
        # Redirect back with an error indication (flash message would be better)
        return redirect(url_for("exclusion_bp.manage_exclusions"))

    security_id = request.form.get("security_id")
    add_date_str = request.form.get("add_date")  # Get AddDate as string

    if not security_id or not add_date_str:
        # Handle missing identifiers (shouldn't happen with hidden fields but good practice)
        # Redirect back with an error message (using flash or query params)
        logger.warning("Remove exclusion attempt missing SecurityID or AddDate.")
        # For simplicity, redirect back to the main page; flash messages would be better
        return redirect(url_for("exclusion_bp.manage_exclusions"))

    # Pass the absolute data_folder path to the helper function
    success, msg = remove_exclusion(data_folder, security_id, add_date_str)

    # Regardless of success/failure, redirect back to the main exclusions page.
    # Consider using flash messages to display the success/error message after redirect.
    # For now, the message `msg` is logged but not shown to the user on redirect.
    return redirect(url_for("exclusion_bp.manage_exclusions"))


# ---------------------------------
# Editing route
# ---------------------------------


@exclusion_bp.route(
    "/exclusions/edit/<security_id>/<add_date>", methods=["GET", "POST"]
)
def edit_exclusion(security_id, add_date):
    """View and edit an existing exclusion, including EndDate change and adding comments."""
    data_folder = current_app.config.get("DATA_FOLDER")
    if not data_folder:
        return "Internal Server Error: Data folder not configured", 500

    message = None
    message_type = "info"

    # POST processing
    if request.method == "POST":
        new_end_date_input = request.form.get("end_date")
        new_end_date = new_end_date_input if new_end_date_input else None

        new_reason_input = request.form.get("reason")
        new_reason = new_reason_input.strip() if new_reason_input and new_reason_input.strip() != "" else None

        comment_text = request.form.get("comment")
        user = request.form.get("user")

        # Update main exclusion fields if supplied
        if (new_end_date is not None) or (new_reason is not None):
            success, msg = update_exclusion_entry(
                data_folder, security_id, add_date, new_end_date, new_reason
            )
            message = msg
            message_type = "success" if success else "danger"

        # Save additional comment if provided (historical)
        if comment_text and user:
            c_success, c_msg = add_exclusion_comment(
                data_folder, security_id, add_date, comment_text, user
            )
            # If message not yet set to error, update accordingly
            if c_success:
                message = (message + " " if message else "") + c_msg
                message_type = "success"
            else:
                message = c_msg
                message_type = "danger"

        # After processing, reload page to show updated info (PRG pattern)
        return redirect(
            url_for(
                "exclusion_bp.edit_exclusion",
                security_id=security_id,
                add_date=add_date,
            )
        )

    # GET processing - load exclusion details and comments
    current_exclusions = load_exclusions(data_folder)
    exclusion = next(
        (
            ex
            for ex in current_exclusions
            if str(ex["SecurityID"]) == str(security_id)
            and ex["AddDate"].strftime("%Y-%m-%d") == add_date
        ),
        None,
    )

    if not exclusion:
        return "Exclusion entry not found", 404

    comments = load_exclusion_comments(data_folder, security_id, add_date)
    users = load_users(data_folder)

    return render_template(
        "exclusion_edit_page.html",
        exclusion=exclusion,
        comments=comments,
        users=users,
        message=message,
        message_type=message_type,
    )
