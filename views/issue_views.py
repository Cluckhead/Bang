# views/issue_views.py
# Purpose: Defines the Flask Blueprint and routes for the Data Issue Tracking feature.

from flask import Blueprint, render_template, request, redirect, url_for, flash
import issue_processing  # Use the new module
import pandas as pd
from datetime import datetime
import os # Added to check for users.csv

issue_bp = Blueprint('issue_bp', __name__, template_folder='templates')

DATA_SOURCES = ["S&P", "Production", "Pi", "IVP", "Benchmark", "BANG Bug", "Rimes"] # Define allowed sources, added Rimes

# Function to load users from CSV
def load_users():
    """Loads the list of users from users.csv."""
    users_file = os.path.join('Data', 'users.csv')
    if os.path.exists(users_file):
        try:
            users_df = pd.read_csv(users_file)
            # Assuming the column name is 'Name'
            if 'Name' in users_df.columns:
                return users_df['Name'].dropna().tolist()
            else:
                print("Warning: 'Name' column not found in users.csv")
                return [] # Return empty list if column not found
        except Exception as e:
            print(f"Error loading users from {users_file}: {e}")
            return [] # Return empty list on error
    else:
        print(f"Warning: {users_file} not found.")
        return [] # Return empty list if file not found

@issue_bp.route('/issues', methods=['GET', 'POST'])
def manage_issues():
    """Displays existing issues and handles adding new issues."""
    message = None
    message_type = 'info'
    available_funds = issue_processing.load_fund_list() # Get fund list for dropdown
    users = load_users() # Load users for dropdowns

    if request.method == 'POST':
        # Process form for adding a new issue
        try:
            raised_by = request.form.get('raised_by')
            fund_impacted = request.form.get('fund_impacted')
            data_source = request.form.get('data_source')
            issue_date_str = request.form.get('issue_date')
            issue_date = pd.to_datetime(issue_date_str).date() if issue_date_str else None
            description = request.form.get('description')
            jira_link = request.form.get('jira_link', None) # Get optional Jira link

            # Basic Validation
            if not raised_by or not fund_impacted or not data_source or not description or not issue_date:
                 raise ValueError("Missing required fields.")
            # Check if user exists in the loaded list (optional, but good practice)
            if raised_by not in users:
                 print(f"Warning: Raised by user '{raised_by}' not found in users.csv. Allowing submission.")
                 # Depending on requirements, you might want to raise ValueError here instead
            if data_source not in DATA_SOURCES:
                 raise ValueError("Invalid data source selected.")


            issue_id = issue_processing.add_issue(
                raised_by=raised_by,
                fund_impacted=fund_impacted,
                data_source=data_source,
                issue_date=issue_date,
                description=description,
                jira_link=jira_link # Pass Jira link
            )
            message = f"Successfully added new issue (ID: {issue_id})."
            message_type = 'success'
            flash(message, message_type)
            return redirect(url_for('issue_bp.manage_issues')) # Redirect to clear form

        except ValueError as ve:
             message = f"Error adding issue: {ve}"
             message_type = 'danger'
             flash(message, message_type)
        except Exception as e:
            message = f"An unexpected error occurred: {e}"
            message_type = 'danger'
            flash(message, message_type)
        # If error, fall through to render template again with message

    # For GET request or if POST had an error
    issues_df = issue_processing.load_issues()
    open_issues = issues_df[issues_df['Status'] == 'Open'].sort_values(by='DateRaised', ascending=False).to_dict('records')
    closed_issues = issues_df[issues_df['Status'] == 'Closed'].sort_values(by='DateClosed', ascending=False).to_dict('records')

    return render_template('issues_page.html',
                           open_issues=open_issues,
                           closed_issues=closed_issues,
                           available_funds=available_funds,
                           data_sources=DATA_SOURCES,
                           users=users # Pass users to template
                           )


@issue_bp.route('/issues/close', methods=['POST'])
def close_issue_route():
    """Handles closing an existing issue."""
    try:
        issue_id = request.form.get('issue_id')
        closed_by = request.form.get('closed_by')
        resolution_comment = request.form.get('resolution_comment')
        users = load_users() # Load users for validation

        if not issue_id or not closed_by or not resolution_comment:
             raise ValueError("Missing required fields for closing the issue.")

        # Optional: Validate closed_by user
        if closed_by not in users:
            print(f"Warning: Closed by user '{closed_by}' not found in users.csv. Allowing closure.")
            # Depending on requirements, you might want to raise ValueError here

        success = issue_processing.close_issue(issue_id, closed_by, resolution_comment)

        if success:
            flash(f"Issue {issue_id} marked as closed.", 'success')
        else:
             flash(f"Failed to close issue {issue_id}. It might not exist or already be closed.", 'warning') # More specific message

    except ValueError as ve:
         flash(f"Error closing issue: {ve}", 'danger')
    except Exception as e:
        flash(f"An unexpected error occurred while closing the issue: {e}", 'danger')

    return redirect(url_for('issue_bp.manage_issues')) 