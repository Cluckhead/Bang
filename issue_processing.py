# issue_processing.py
# Purpose: Handles loading, adding, and updating data issues stored in a specified data folder (data_folder_path) rather than a hardcoded path.

import pandas as pd
import os
from datetime import datetime
from typing import Optional, List, Tuple, Any, Dict
import logging

# Remove: from config import DATA_FOLDER

# Remove global file paths
# ISSUES_FILE = os.path.join(DATA_FOLDER, 'data_issues.csv')
# FUND_LIST_FILE = os.path.join(DATA_FOLDER, 'FundList.csv')

REQUIRED_ISSUE_COLUMNS = [
    "IssueID",
    "DateRaised",
    "RaisedBy",
    "FundImpacted",
    "DataSource",
    "IssueDate",
    "Description",
    "JiraLink",
    "InScopeForGoLive",
    "Status",
    "DateClosed",
    "ClosedBy",
    "ResolutionComment",
]

logger = logging.getLogger(__name__)


def load_issues(data_folder_path: str) -> pd.DataFrame:
    """Loads the data issues from the CSV file in the specified data folder into a pandas DataFrame."""
    issues_file = os.path.join(data_folder_path, "data_issues.csv")
    try:
        if os.path.exists(issues_file):
            try:
                df = pd.read_csv(
                    issues_file, parse_dates=["DateRaised", "DateClosed", "IssueDate"]
                )

                # --- Check and add missing columns ---
                existing_columns = df.columns.tolist()
                columns_added = False
                for col in REQUIRED_ISSUE_COLUMNS:
                    if col not in existing_columns:
                        logger.info(
                            f"Adding missing column '{col}' to issues DataFrame."
                        )
                        if "Date" in col:
                            df[col] = pd.NaT  # Use NaT for date types
                        elif col == "JiraLink":
                            df[col] = None  # Use None or empty string for JiraLink
                        elif col == "Status":
                            df[col] = "Open"  # Default status
                        elif col == "InScopeForGoLive":
                            df[col] = "No"  # Default to 'No'
                        else:
                            df[col] = None  # Default for other types
                        columns_added = True
                # If columns were added, save the file back immediately
                if columns_added:
                    logger.info("Saving issues file with newly added columns.")
                    _save_issues(
                        df.copy(), data_folder_path
                    )  # Save a copy to avoid modifying df used later
                    # Re-read after saving to ensure correct types
                    df = pd.read_csv(
                        issues_file,
                        parse_dates=["DateRaised", "DateClosed", "IssueDate"],
                    )
                # Ensure Status exists and fill missing with 'Open' (redundant if using REQUIRED_ISSUE_COLUMNS check, but safe)
                if "Status" not in df.columns:
                    df["Status"] = "Open"
                else:
                    df["Status"] = df["Status"].fillna("Open")
                # Convert relevant columns to appropriate types after loading/filling
                df["DateRaised"] = pd.to_datetime(df["DateRaised"]).dt.date
                df["DateClosed"] = pd.to_datetime(df["DateClosed"]).dt.date
                df["IssueDate"] = pd.to_datetime(df["IssueDate"]).dt.date
                df["IssueID"] = df["IssueID"].astype(str)  # Ensure IssueID is string
                df["JiraLink"] = df["JiraLink"].fillna(
                    ""
                )  # Fill NaN Jira links with empty string for display
                # Reorder columns to match REQUIRED_ISSUE_COLUMNS for consistency
                df = df[REQUIRED_ISSUE_COLUMNS]
                return df
            except FileNotFoundError:
                logger.error(f"Issues file not found at {issues_file}.")
                return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
            except pd.errors.EmptyDataError:
                logger.warning(
                    f"Issues file at {issues_file} is empty. Returning empty DataFrame."
                )
                return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
            except pd.errors.ParserError as e:
                logger.error(
                    f"Error parsing issues file {issues_file}: {e}", exc_info=True
                )
                return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
            except Exception as e:
                logger.error(f"Error loading issues file: {e}", exc_info=True)
                return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
        else:
            logger.info(
                f"Issues file not found at {issues_file}. Returning empty DataFrame."
            )
            return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
    except Exception as e:
        logger.error(f"Unexpected error in load_issues: {e}", exc_info=True)
        return pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)


def _save_issues(df: pd.DataFrame, data_folder_path: str) -> None:
    """Saves the DataFrame back to the CSV file in the specified data folder."""
    issues_file = os.path.join(data_folder_path, "data_issues.csv")
    try:
        # Ensure all required columns exist before saving
        for col in REQUIRED_ISSUE_COLUMNS:
            if col not in df.columns:
                logger.warning(f"Column '{col}' missing before saving. Adding it.")
                if "Date" in col:
                    df[col] = pd.NaT
                elif col == "JiraLink":
                    df[col] = None
                elif col == "Status":
                    df[col] = "Open"
                elif col == "InScopeForGoLive":
                    df[col] = "No"
                else:
                    df[col] = None
        # Reorder columns before saving
        df_to_save = df[REQUIRED_ISSUE_COLUMNS].copy()
        # Convert date columns to string format YYYY-MM-DD for CSV consistency
        date_cols = ["DateRaised", "DateClosed", "IssueDate"]
        for col in date_cols:
            if col in df_to_save.columns:
                # Handle NaT before formatting
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime(
                    "%Y-%m-%d"
                )
                df_to_save[col] = df_to_save[col].replace(
                    "NaT", ""
                )  # Replace NaT string with empty string
        # Handle potential NaN in other object columns (like JiraLink, RaisedBy etc)
        object_cols = df_to_save.select_dtypes(include=["object"]).columns
        for col in object_cols:
            df_to_save[col] = df_to_save[col].fillna(
                ""
            )  # Replace NaN with empty string
        df_to_save.to_csv(issues_file, index=False)
    except PermissionError:
        logger.error(
            f"Permission denied when saving issues file: {issues_file}", exc_info=True
        )
    except OSError as e:
        logger.error(
            f"OS error when saving issues file: {issues_file}: {e}", exc_info=True
        )
    except Exception as e:
        logger.error(f"Error saving issues file: {e}", exc_info=True)


def _generate_issue_id(existing_ids: pd.Series) -> str:
    """Generates a unique sequential issue ID (e.g., ISSUE-001)."""
    valid_ids = existing_ids.dropna().astype(str).str.strip()
    valid_ids = valid_ids[valid_ids != ""]
    if valid_ids.empty:
        return "ISSUE-001"
    numeric_parts = (
        valid_ids.str.extract(r"ISSUE-(\d+)", expand=False).dropna().astype(int)
    )
    if numeric_parts.empty:
        logger.warning("No existing IDs match the format 'ISSUE-XXX'. Starting from 1.")
        return "ISSUE-001"
    max_num = numeric_parts.max()
    new_num = max_num + 1
    return f"ISSUE-{new_num:03d}"


def add_issue(
    raised_by: str,
    fund_impacted: str,
    data_source: str,
    issue_date: Any,
    description: str,
    jira_link: Optional[str] = None,
    in_scope_for_go_live: str = "No",
    data_folder_path: Optional[str] = None,
) -> str:
    """Adds a new issue to the CSV file in the specified data folder."""
    try:
        df = load_issues(data_folder_path)
        new_id = _generate_issue_id(df["IssueID"])
        new_issue = pd.DataFrame(
            {
                "IssueID": [new_id],
                "DateRaised": [datetime.now().date()],
                "RaisedBy": [raised_by],
                "FundImpacted": [fund_impacted],
                "DataSource": [data_source],
                "IssueDate": [issue_date],  # Date the issue relates to
                "Description": [description],
                "JiraLink": [
                    jira_link if jira_link else ""
                ],  # Add Jira link, ensure it's not None
                "InScopeForGoLive": [in_scope_for_go_live],
                "Status": ["Open"],
                "DateClosed": [pd.NaT],
                "ClosedBy": [None],
                "ResolutionComment": [None],
            }
        )
        # Ensure the new issue DataFrame has all the required columns in the correct order
        for col in REQUIRED_ISSUE_COLUMNS:
            if col not in new_issue.columns:
                new_issue[col] = (
                    pd.NaT if "Date" in col else ("" if col == "JiraLink" else None)
                )
        new_issue = new_issue[REQUIRED_ISSUE_COLUMNS]
        df_updated = pd.concat([df, new_issue], ignore_index=True)
        _save_issues(df_updated, data_folder_path)
        return new_id  # Return the ID of the newly added issue
    except Exception as e:
        logger.error(f"Error adding new issue: {e}", exc_info=True)
        return ""


def close_issue(
    issue_id: str,
    closed_by: str,
    resolution_comment: str,
    data_folder_path: Optional[str],
) -> bool:
    """Marks an issue as closed in the CSV file in the specified data folder."""
    try:
        df = load_issues(data_folder_path)
        # Ensure IssueID is string for comparison
        df["IssueID"] = df["IssueID"].astype(str)
        issue_id_str = str(issue_id)  # Ensure input is also string
        # Find the index of the issue
        matching_indices = df[df["IssueID"] == issue_id_str].index
        if not matching_indices.empty:
            idx = matching_indices[
                0
            ]  # Take the first index if multiple matches (shouldn't happen)
            # Check if already closed to prevent accidental updates
            if df.loc[idx, "Status"] == "Closed":
                logger.warning(f"Issue ID {issue_id_str} is already closed.")
                return False  # Indicate no change was made
            df.loc[idx, "Status"] = "Closed"
            df.loc[idx, "DateClosed"] = datetime.now().date()
            df.loc[idx, "ClosedBy"] = closed_by
            df.loc[idx, "ResolutionComment"] = resolution_comment
            _save_issues(df, data_folder_path)
            return True
        else:
            logger.warning(f"Issue ID {issue_id_str} not found.")
            return False
    except Exception as e:
        logger.error(f"Error closing issue {issue_id}: {e}", exc_info=True)
        return False


def load_fund_list(data_folder_path: str) -> List[str]:
    """Loads the list of funds from FundList.csv in the specified data folder."""
    fund_list_file = os.path.join(data_folder_path, "FundList.csv")
    try:
        if os.path.exists(fund_list_file):
            try:
                fund_df = pd.read_csv(fund_list_file)
                fund_code_col = None
                # Try common column names for fund codes
                potential_cols = ["FundCode", "Code", "Fund Code"]
                for col in potential_cols:
                    if col in fund_df.columns:
                        fund_code_col = col
                        break
                if fund_code_col:
                    return sorted(
                        fund_df[fund_code_col].dropna().astype(str).unique().tolist()
                    )
                else:
                    logger.warning(
                        f"Could not find a suitable fund code column ({', '.join(potential_cols)}) in {fund_list_file}"
                    )
                    return []  # Return empty if column not found
            except FileNotFoundError:
                logger.error(f"Fund list file not found at {fund_list_file}.")
                return []
            except pd.errors.EmptyDataError:
                logger.warning(
                    f"Fund list file at {fund_list_file} is empty. Returning empty list."
                )
                return []
            except pd.errors.ParserError as e:
                logger.error(
                    f"Error parsing fund list file {fund_list_file}: {e}", exc_info=True
                )
                return []
            except Exception as e:
                logger.error(f"Error loading fund list: {e}", exc_info=True)
                return []
        else:
            logger.info(
                f"Fund list file not found at {fund_list_file}. Returning empty list."
            )
            return []
    except Exception as e:
        logger.error(f"Unexpected error in load_fund_list: {e}", exc_info=True)
        return []


# --- Initial File Creation / Update Check ---
def initialize_issue_file(data_folder_path: str) -> None:
    """Initializes the issues file in the specified data folder if it does not exist."""
    issues_file = os.path.join(data_folder_path, "data_issues.csv")
    try:
        if not os.path.exists(issues_file):
            df = pd.DataFrame(columns=REQUIRED_ISSUE_COLUMNS)
            _save_issues(df, data_folder_path)
            logger.info(f"Initialized new issues file at {issues_file}.")
        else:
            logger.info(f"Issues file already exists at {issues_file}.")
    except Exception as e:
        logger.error(
            f"Error initializing issues file at {issues_file}: {e}", exc_info=True
        )


# (Removed call to initialize_issue_file(data_folder_path=None))
