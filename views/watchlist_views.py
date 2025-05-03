"""
This module defines the Flask Blueprint for the Watchlist feature.
It provides routes and helper functions to manage a global list of securities
that users want to monitor regularly. The watchlist is stored in Data/Watchlist.csv
and supports adding, clearing, and tracking when each security was last checked.

Features:
- Only one active entry per ISIN (unique constraint)
- Users can add a security with a reason and their name
- Users can clear (not delete) a security, recording who/why/when
- LastChecked timestamp is updated when a user clicks through from the watchlist
- All actions are logged using the central Flask logger
- Loads users from users.csv and securities from reference.csv
- Replicates the style and conventions of exclusions/issues features
"""

import os
import pandas as pd
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    current_app,
    flash,
)
from datetime import datetime
import logging

# Define the Blueprint
watchlist_bp = Blueprint("watchlist_bp", __name__, template_folder="../templates")

WATCHLIST_FILE = "Watchlist.csv"


# --- Helper Functions ---
def load_watchlist(data_folder_path: str):
    """
    Loads the current watchlist from the CSV file.
    Returns a list of dicts, each representing a watchlist entry.
    """
    if not data_folder_path:
        current_app.logger.error(
            "No data_folder_path provided to load_watchlist.", exc_info=True
        )
        return []
    watchlist_path = os.path.join(data_folder_path, WATCHLIST_FILE)
    try:
        if os.path.exists(watchlist_path) and os.path.getsize(watchlist_path) > 0:
            df = pd.read_csv(
                watchlist_path, parse_dates=["DateAdded", "LastChecked", "ClearedDate"]
            )
            # Ensure correct types
            df["ISIN"] = df["ISIN"].astype(str)
            df["Security Name"] = df["Security Name"].astype(str)
            df["Reason"] = df["Reason"].astype(str)
            df["AddedBy"] = df["AddedBy"].astype(str)
            df["Status"] = df["Status"].astype(str)
            # Fill NaN for optional fields
            for col in ["LastChecked", "ClearedBy", "ClearedDate", "ClearReason"]:
                if col in df.columns:
                    df[col] = df[col].fillna("")
            # Sort: active first, then by DateAdded desc
            df["Status"] = df["Status"].fillna("Active")
            df = df.sort_values(by=["Status", "DateAdded"], ascending=[True, False])
            return df.to_dict("records")
        else:
            return []
    except Exception as e:
        current_app.logger.error(f"Error loading watchlist: {e}", exc_info=True)
        return []


def save_watchlist(df: pd.DataFrame, data_folder_path: str):
    """Saves the watchlist DataFrame to CSV."""
    watchlist_path = os.path.join(data_folder_path, WATCHLIST_FILE)
    try:
        df.to_csv(watchlist_path, index=False)
    except Exception as e:
        current_app.logger.error(f"Error saving watchlist: {e}", exc_info=True)


def load_users(data_folder_path: str):
    """Loads the list of users from users.csv for dropdowns."""
    users_file_path = os.path.join(data_folder_path, "users.csv")
    try:
        if os.path.exists(users_file_path):
            df = pd.read_csv(users_file_path)
            if "Name" in df.columns:
                return df["Name"].dropna().astype(str).tolist()
        return []
    except Exception as e:
        current_app.logger.error(f"Error loading users: {e}", exc_info=True)
        return []


def load_available_securities(data_folder_path: str):
    """Loads securities from reference.csv for the ISIN dropdown, including Ticker and Security Sub Type for filtering."""
    reference_file_path = os.path.join(data_folder_path, "reference.csv")
    try:
        if os.path.exists(reference_file_path):
            usecols = ["ISIN", "Security Name", "Ticker", "Security Sub Type"]
            df = pd.read_csv(
                reference_file_path,
                usecols=usecols,
                encoding_errors="replace",
                on_bad_lines="skip",
            )
            df = df.dropna(subset=["ISIN", "Security Name"])
            df = df.drop_duplicates(subset=["ISIN"])
            return df.to_dict("records")
        return []
    except Exception as e:
        current_app.logger.error(f"Error loading securities: {e}", exc_info=True)
        return []


def add_to_watchlist(data_folder_path: str, isin: str, reason: str, user: str):
    """
    Adds a new security to the watchlist. Only one active entry per ISIN is allowed.
    If ISIN exists and is active, returns error. If ISIN exists and is cleared, allows re-adding as active.
    """
    watchlist = load_watchlist(data_folder_path)
    now = datetime.now()
    # Check for existing active entry
    for entry in watchlist:
        if entry["ISIN"] == isin and entry["Status"] == "Active":
            return False, "This security is already on the watchlist."
    # Get Security Name from reference
    securities = load_available_securities(data_folder_path)
    sec_name = next((s["Security Name"] for s in securities if s["ISIN"] == isin), None)
    if not sec_name:
        return False, "Security not found."
    # Create DataFrame from watchlist
    df = pd.DataFrame(watchlist)
    # If the DataFrame is empty, initialize it with the required columns to avoid KeyError
    required_columns = [
        "ISIN",
        "Security Name",
        "Reason",
        "DateAdded",
        "AddedBy",
        "LastChecked",
        "Status",
        "ClearedBy",
        "ClearedDate",
        "ClearReason",
    ]
    if df.empty:
        df = pd.DataFrame(columns=required_columns)
    # Remove any cleared entry for this ISIN (will re-add as active)
    if not df.empty:
        df = df[~((df["ISIN"] == isin) & (df["Status"] == "Cleared"))]
    # Add new entry
    new_entry = {
        "ISIN": isin,
        "Security Name": sec_name,
        "Reason": reason,
        "DateAdded": now.strftime("%Y-%m-%d"),
        "AddedBy": user,
        "LastChecked": "",
        "Status": "Active",
        "ClearedBy": "",
        "ClearedDate": "",
        "ClearReason": "",
    }
    df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    save_watchlist(df, data_folder_path)
    current_app.logger.info(f"Added to watchlist: {isin} by {user}")
    return True, "Security added to watchlist."


def clear_watchlist_entry(
    data_folder_path: str, isin: str, cleared_by: str, clear_reason: str
):
    """
    Marks a watchlist entry as cleared, recording who/why/when.
    """
    watchlist = load_watchlist(data_folder_path)
    df = pd.DataFrame(watchlist)
    now = datetime.now()
    # Handle empty DataFrame case
    if df.empty:
        return False, "Active watchlist entry not found."
    idx = df[(df["ISIN"] == isin) & (df["Status"] == "Active")].index
    if len(idx) == 0:
        return False, "Active watchlist entry not found."
    df.loc[idx, "Status"] = "Cleared"
    df.loc[idx, "ClearedBy"] = cleared_by
    df.loc[idx, "ClearedDate"] = now.strftime("%Y-%m-%d")
    df.loc[idx, "ClearReason"] = clear_reason
    save_watchlist(df, data_folder_path)
    current_app.logger.info(f"Cleared watchlist entry: {isin} by {cleared_by}")
    return True, "Watchlist entry cleared."


def update_last_checked(data_folder_path: str, isin: str):
    """
    Updates the LastChecked timestamp for a given ISIN (when user clicks through).
    """
    watchlist = load_watchlist(data_folder_path)
    df = pd.DataFrame(watchlist)
    # Handle empty DataFrame case
    if df.empty:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    idx = df[(df["ISIN"] == isin) & (df["Status"] == "Active")].index
    if len(idx) == 0:
        return False
    df.loc[idx, "LastChecked"] = now
    save_watchlist(df, data_folder_path)
    current_app.logger.info(f"Updated LastChecked for {isin}")
    return True


# --- Routes ---
@watchlist_bp.route("/watchlist", methods=["GET", "POST"])
def manage_watchlist():
    """
    Handles viewing and adding to the watchlist.
    GET: Shows the current watchlist and add form.
    POST: Adds a new entry if valid.
    """
    data_folder = current_app.config["DATA_FOLDER"]
    message = None
    message_type = "info"
    if request.method == "POST":
        isin = request.form.get("isin")
        reason = request.form.get("reason")
        user = request.form.get("user")
        if not isin or not reason or not user:
            message = "ISIN, reason, and user are required."
            message_type = "danger"
        else:
            success, msg = add_to_watchlist(data_folder, isin, reason, user)
            if success:
                flash(msg, "success")
                return redirect(url_for("watchlist_bp.manage_watchlist"))
            else:
                message = msg
                message_type = "danger"
    watchlist = load_watchlist(data_folder)
    users = load_users(data_folder)
    securities = load_available_securities(data_folder)
    return render_template(
        "watchlist_page.html",
        watchlist=watchlist,
        users=users,
        securities=securities,
        message=message,
        message_type=message_type,
    )


@watchlist_bp.route("/watchlist/clear", methods=["POST"])
def clear_watchlist():
    """Handles POST request to clear a watchlist entry."""
    data_folder = current_app.config["DATA_FOLDER"]
    # Use standard form names matching the add form for consistency
    isin = request.form.get("isin")
    cleared_by = request.form.get("user")  # Use 'user' from form
    clear_reason = request.form.get("reason")  # Use 'reason' from form

    if not isin or not cleared_by or not clear_reason:
        flash("ISIN, user, and reason are required to clear an entry.", "danger")
    else:
        success, msg = clear_watchlist_entry(
            data_folder, isin, cleared_by, clear_reason
        )
        flash(msg, "success" if success else "danger")

    return redirect(url_for("watchlist_bp.manage_watchlist"))


@watchlist_bp.route("/watchlist/check/<isin>", methods=["GET"])
def check_watchlist_entry(isin):
    """
    Updates LastChecked for the ISIN and redirects to the security details page.
    If the update fails (e.g., ISIN not active), redirects back to the watchlist with an error flash.
    """
    data_folder = current_app.config["DATA_FOLDER"]
    success = update_last_checked(data_folder, isin)

    if success:
        # Redirect to the security details page
        # NOTE: The security_details endpoint requires both 'metric_name' and 'security_id'.
        # Here, we default to 'Duration' as the metric. Change as needed for your app logic.
        return redirect(
            url_for(
                "security.security_details", metric_name="Duration", security_id=isin
            )
        )
    else:
        flash(
            f"Failed to update check time or find active entry for ISIN {isin}.",
            "danger",
        )
        return redirect(url_for("watchlist_bp.manage_watchlist"))
