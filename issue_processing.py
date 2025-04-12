# issue_processing.py
# Purpose: Handles loading, adding, and updating data issues stored in Data/data_issues.csv.

import pandas as pd
import os
from datetime import datetime
from config import DATA_FOLDER

ISSUES_FILE = os.path.join(DATA_FOLDER, 'data_issues.csv')
FUND_LIST_FILE = os.path.join(DATA_FOLDER, 'FundList.csv')


def load_issues():
    """Loads the data issues from the CSV file into a pandas DataFrame."""
    if os.path.exists(ISSUES_FILE):
        try:
            df = pd.read_csv(ISSUES_FILE,
                             parse_dates=['DateRaised', 'DateClosed', 'IssueDate'])
            # Ensure Status exists and fill missing with 'Open' for backward compatibility if needed
            if 'Status' not in df.columns:
                df['Status'] = 'Open'
            else:
                df['Status'] = df['Status'].fillna('Open')

            # Ensure required columns exist, fill with NaT/None if missing
            required_cols = {
                'IssueID': None, 'DateRaised': pd.NaT, 'RaisedBy': None,
                'FundImpacted': None, 'DataSource': None, 'IssueDate': pd.NaT,
                'Description': None, 'Status': 'Open', 'DateClosed': pd.NaT,
                'ClosedBy': None, 'ResolutionComment': None
            }
            for col, default in required_cols.items():
                if col not in df.columns:
                    df[col] = default

            # Convert relevant columns to appropriate types after loading/filling
            df['DateRaised'] = pd.to_datetime(df['DateRaised']).dt.date
            df['DateClosed'] = pd.to_datetime(df['DateClosed']).dt.date
            df['IssueDate'] = pd.to_datetime(df['IssueDate']).dt.date
            df['IssueID'] = df['IssueID'].astype(str) # Ensure IssueID is string
            return df
        except Exception as e:
            print(f"Error loading issues file: {e}")
            # Return an empty DataFrame with correct columns on error
            return pd.DataFrame(columns=list(required_cols.keys()))
    else:
        # Return an empty DataFrame with correct columns if file doesn't exist
        return pd.DataFrame(columns=list(required_cols.keys()))

def _save_issues(df):
    """Saves the DataFrame back to the CSV file."""
    try:
        # Convert date columns to string format for CSV consistency
        date_cols = ['DateRaised', 'DateClosed', 'IssueDate']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d')

        df.to_csv(ISSUES_FILE, index=False)
    except Exception as e:
        print(f"Error saving issues file: {e}")

def _generate_issue_id(existing_ids):
    """Generates a unique sequential issue ID (e.g., ISSUE-001)."""
    # Check if the series is empty or if all existing IDs are null/NaN
    if existing_ids.empty or existing_ids.isnull().all():
        return "ISSUE-001"

    # Filter out potential NaN values before extracting numbers
    max_num = existing_ids.str.extract(r'ISSUE-(\d+)', expand=False).astype(int).max()
    new_num = max_num + 1
    return f"ISSUE-{new_num:03d}"

def add_issue(raised_by, fund_impacted, data_source, issue_date, description):
    """Adds a new issue to the CSV file."""
    df = load_issues()

    new_id = _generate_issue_id(df['IssueID'])

    new_issue = pd.DataFrame({
        'IssueID': [new_id],
        'DateRaised': [datetime.now().date()],
        'RaisedBy': [raised_by],
        'FundImpacted': [fund_impacted],
        'DataSource': [data_source],
        'IssueDate': [issue_date], # Date the issue relates to
        'Description': [description],
        'Status': ['Open'],
        'DateClosed': [pd.NaT],
        'ClosedBy': [None],
        'ResolutionComment': [None]
    })

    df_updated = pd.concat([df, new_issue], ignore_index=True)
    _save_issues(df_updated)
    return new_id # Return the ID of the newly added issue

def close_issue(issue_id, closed_by, resolution_comment):
    """Marks an issue as closed in the CSV file."""
    df = load_issues()

    # Ensure IssueID is string for comparison
    df['IssueID'] = df['IssueID'].astype(str)
    issue_id_str = str(issue_id) # Ensure input is also string

    if issue_id_str in df['IssueID'].values:
        idx = df[df['IssueID'] == issue_id_str].index
        df.loc[idx, 'Status'] = 'Closed'
        df.loc[idx, 'DateClosed'] = datetime.now().date()
        df.loc[idx, 'ClosedBy'] = closed_by
        df.loc[idx, 'ResolutionComment'] = resolution_comment
        _save_issues(df)
        return True
    else:
        print(f"Issue ID {issue_id_str} not found.")
        return False

def load_fund_list():
    """Loads the list of funds from FundList.csv."""
    if os.path.exists(FUND_LIST_FILE):
        try:
            # Assuming FundList.csv has a column named 'FundCode' or similar
            # Adjust the column name as necessary
            fund_df = pd.read_csv(FUND_LIST_FILE)
            if 'FundCode' in fund_df.columns: # Check for 'FundCode'
                return fund_df['FundCode'].unique().tolist()
            elif 'Code' in fund_df.columns: # Fallback check for 'Code'
                 return fund_df['Code'].unique().tolist()
            elif 'Fund Code' in fund_df.columns: # Add check for 'Fund Code' with space
                 return fund_df['Fund Code'].unique().tolist()
            else:
                 print(f"Warning: Could not find a suitable fund code column ('FundCode', 'Code', or 'Fund Code') in {FUND_LIST_FILE}")
                 return [] # Return empty if column not found
        except Exception as e:
            print(f"Error loading fund list: {e}")
            return []
    else:
        print("Warning: FundList.csv not found.")
        return []

# Ensure the issues file exists with headers if it doesn't
if not os.path.exists(ISSUES_FILE):
    print(f"Creating initial issues file: {ISSUES_FILE}")
    # Create empty DataFrame with correct columns and save it
    initial_df = pd.DataFrame(columns=[
        'IssueID', 'DateRaised', 'RaisedBy', 'FundImpacted', 'DataSource',
        'IssueDate', 'Description', 'Status', 'DateClosed', 'ClosedBy',
        'ResolutionComment'
    ])
    _save_issues(initial_df) 