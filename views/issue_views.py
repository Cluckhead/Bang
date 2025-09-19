# views/issue_views.py
# Purpose: Defines the Flask Blueprint and routes for the Data Issue Tracking feature.

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
import analytics.issue_processing as issue_processing  # Use the new module
import pandas as pd
from datetime import datetime
import os  # Added to check for users.csv
from core.config import DATA_SOURCES, JIRA_BASE_URL  # Import from config.py
from analytics.issue_processing import get_issue_by_id, add_comment_to_issue
from typing import List
import re  # Added for regex pattern matching

issue_bp = Blueprint("issue_bp", __name__, template_folder="templates")


def process_jira_link(jira_link: str) -> tuple:
    """
    Process a Jira link to ensure it's a full URL.
    
    Args:
        jira_link: Either a full URL or just an issue key (e.g., PROJ-123)
        
    Returns:
        tuple: (full_url, display_text) - The full URL and text to display
    """
    if not jira_link:
        return None, None
        
    # Trim whitespace
    jira_link = jira_link.strip()
    
    # Check if it's already a full URL (starts with http:// or https://)
    if jira_link.startswith(('http://', 'https://')):
        # Extract the issue key from the URL for display
        # Common patterns: /browse/PROJ-123 or /issues/PROJ-123
        match = re.search(r'/(?:browse|issues)/([A-Z]+-\d+)', jira_link)
        if match:
            display_text = match.group(1)
        else:
            display_text = "Link"
        return jira_link, display_text
    else:
        # Assume it's just an issue key like PROJ-123
        # Validate it matches the pattern (letters-numbers)
        if re.match(r'^[A-Z]+-\d+$', jira_link, re.IGNORECASE):
            full_url = JIRA_BASE_URL + jira_link
            return full_url, jira_link
        else:
            # If it doesn't match the pattern, return as-is
            return jira_link, jira_link


# Function to load users from CSV
def load_users() -> List[str]:
    """Loads the list of users from users.csv."""
    data_folder = current_app.config["DATA_FOLDER"] # Get DATA_FOLDER from app config
    users_file = os.path.join(data_folder, "users.csv") # Use data_folder
    if os.path.exists(users_file):
        try:
            users_df = pd.read_csv(users_file)
            # Assuming the column name is 'Name'
            if "Name" in users_df.columns:
                return users_df["Name"].dropna().tolist()
            else:
                current_app.logger.warning(
                    "Warning: 'Name' column not found in users.csv"
                )
                return []  # Return empty list if column not found
        except Exception as e:
            current_app.logger.error(f"Error loading users from {users_file}: {e}")
            return []  # Return empty list on error
    else:
        current_app.logger.warning(f"Warning: {users_file} not found.")
        return []  # Return empty list if file not found


@issue_bp.route("/issues", methods=["GET", "POST"])
def manage_issues():
    """Displays existing issues and handles adding new issues."""
    message = None
    message_type = "info"
    data_folder = current_app.config["DATA_FOLDER"]
    available_funds = issue_processing.load_fund_list(
        data_folder
    )  # Pass data_folder_path
    users = load_users()  # Load users for dropdowns

    if request.method == "POST":
        # Process form for adding a new issue
        try:
            raised_by = request.form.get("raised_by")
            fund_impacted = request.form.get("fund_impacted")
            data_source = request.form.get("data_source")
            issue_date_str = request.form.get("issue_date")
            issue_date = (
                pd.to_datetime(issue_date_str).date() if issue_date_str else None
            )
            description = request.form.get("description")
            jira_link = request.form.get("jira_link", None)  # Get optional Jira link
            in_scope_for_go_live = request.form.get("in_scope_for_go_live", "No")

            # Basic Validation
            if (
                not raised_by
                or not fund_impacted
                or not data_source
                or not description
                or not issue_date
            ):
                raise ValueError("Missing required fields.")
            # Check if user exists in the loaded list (optional, but good practice)
            if raised_by not in users:
                current_app.logger.warning(
                    f"Warning: Raised by user '{raised_by}' not found in users.csv. Allowing submission."
                )
                # Depending on requirements, you might want to raise ValueError here instead
            if data_source not in DATA_SOURCES:
                raise ValueError("Invalid data source selected.")

            issue_id = issue_processing.add_issue(
                raised_by=raised_by,
                fund_impacted=fund_impacted,
                data_source=data_source,
                issue_date=issue_date,
                description=description,
                jira_link=jira_link,  # Pass Jira link
                in_scope_for_go_live=in_scope_for_go_live,
                data_folder_path=data_folder,  # Pass data_folder_path
            )
            message = f"Successfully added new issue (ID: {issue_id})."
            message_type = "success"
            flash(message, message_type)
            return redirect(url_for("issue_bp.manage_issues"))  # Redirect to clear form

        except ValueError as ve:
            message = f"Error adding issue: {ve}"
            message_type = "danger"
            flash(message, message_type)
        except Exception as e:
            message = f"An unexpected error occurred: {e}"
            message_type = "danger"
            flash(message, message_type)
        # If error, fall through to render template again with message

    # For GET request or if POST had an error
    issues_df = issue_processing.load_issues(data_folder)  # Pass data_folder_path
    open_issues = (
        issues_df[issues_df["Status"] == "Open"]
        .sort_values(by="DateRaised", ascending=False)
        .to_dict("records")
    )
    closed_issues = (
        issues_df[issues_df["Status"] == "Closed"]
        .sort_values(by="DateClosed", ascending=False)
        .to_dict("records")
    )
    
    # Process Jira links for open issues
    for issue in open_issues:
        if issue.get("JiraLink"):
            issue["JiraURL"], issue["JiraDisplay"] = process_jira_link(issue["JiraLink"])
        else:
            issue["JiraURL"], issue["JiraDisplay"] = None, None
            
    # Process Jira links for closed issues
    for issue in closed_issues:
        if issue.get("JiraLink"):
            issue["JiraURL"], issue["JiraDisplay"] = process_jira_link(issue["JiraLink"])
        else:
            issue["JiraURL"], issue["JiraDisplay"] = None, None

    return render_template(
        "issues_page.html",
        open_issues=open_issues,
        closed_issues=closed_issues,
        available_funds=available_funds,
        data_sources=DATA_SOURCES,
        users=users,  # Pass users to template
    )


@issue_bp.route("/issues/close", methods=["POST"])
def close_issue_route():
    """Handles closing an existing issue."""
    try:
        issue_id = request.form.get("issue_id")
        closed_by = request.form.get("closed_by")
        resolution_comment = request.form.get("resolution_comment")
        users = load_users()  # Load users for validation
        data_folder = current_app.config["DATA_FOLDER"]

        if not issue_id or not closed_by or not resolution_comment:
            raise ValueError("Missing required fields for closing the issue.")

        # Optional: Validate closed_by user
        if closed_by not in users:
            current_app.logger.warning(
                f"Warning: Closed by user '{closed_by}' not found in users.csv. Allowing closure."
            )
            # Depending on requirements, you might want to raise ValueError here

        success = issue_processing.close_issue(
            issue_id, closed_by, resolution_comment, data_folder
        )  # Pass data_folder_path

        if success:
            flash(f"Issue {issue_id} marked as closed.", "success")
        else:
            flash(
                f"Failed to close issue {issue_id}. It might not exist or already be closed.",
                "warning",
            )  # More specific message

    except ValueError as ve:
        flash(f"Error closing issue: {ve}", "danger")
    except Exception as e:
        flash(f"An unexpected error occurred while closing the issue: {e}", "danger")

    return redirect(url_for("issue_bp.manage_issues"))


@issue_bp.route("/issues/<issue_id>", methods=["GET", "POST"])
def issue_detail(issue_id):
    """Display single issue detail; allow adding comments or updating status."""
    data_folder = current_app.config["DATA_FOLDER"]
    users = load_users()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_comment":
            commenter = request.form.get("comment_user")
            comment_text = request.form.get("comment_text")
            if commenter and comment_text:
                success = add_comment_to_issue(issue_id, commenter, comment_text, data_folder)
                flash("Comment added." if success else "Failed to add comment.", "success" if success else "danger")
            else:
                flash("User and comment required", "warning")
        elif action == "close_issue":
            closed_by = request.form.get("closed_by")
            resolution_comment = request.form.get("resolution_comment")
            if closed_by and resolution_comment:
                success = issue_processing.close_issue(issue_id, closed_by, resolution_comment, data_folder)
                flash("Issue closed." if success else "Failed to close issue.", "success" if success else "danger")
            else:
                flash("All fields required to close issue", "warning")
        return redirect(url_for("issue_bp.issue_detail", issue_id=issue_id))

    # GET flow: load issue and comments
    issue_row = get_issue_by_id(issue_id, data_folder)
    if issue_row is None:
        flash(f"Issue {issue_id} not found", "danger")
        return redirect(url_for("issue_bp.manage_issues"))

    from json import loads
    comments = loads(issue_row.get("Comments", "[]")) if isinstance(issue_row.get("Comments"), str) else []

    # Prepare Jira link display
    jira_url, jira_display = process_jira_link(issue_row.get("JiraLink", "")) if issue_row.get("JiraLink") else (None, None)

    return render_template(
        "issue_detail_page.html",
        issue=issue_row,
        comments=comments,
        users=users,
        jira_url=jira_url,
        jira_display=jira_display,
    )
