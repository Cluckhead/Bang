# Purpose: Unit tests for issue_processing.py, covering issue loading, ID generation, adding, closing, and fund list loading.

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import os
import issue_processing

def test_load_issues_valid(tmp_path):
    # Create a valid data_issues.csv
    data = pd.DataFrame({
        'IssueID': ['ISSUE-001'],
        'DateRaised': ['2024-01-01'],
        'RaisedBy': ['Alice'],
        'FundImpacted': ['FUND1'],
        'DataSource': ['S&P'],
        'IssueDate': ['2024-01-01'],
        'Description': ['desc'],
        'JiraLink': [''],
        'Status': ['Open'],
        'DateClosed': [''],
        'ClosedBy': [''],
        'ResolutionComment': ['']
    })
    folder = tmp_path
    file_path = folder / 'data_issues.csv'
    data.to_csv(file_path, index=False)
    df = issue_processing.load_issues(str(folder))
    assert not df.empty
    assert 'IssueID' in df.columns
    assert df.iloc[0]['IssueID'] == 'ISSUE-001'

def test_load_issues_file_not_found(tmp_path):
    # No data_issues.csv in the folder
    df = issue_processing.load_issues(str(tmp_path))
    assert df.empty or set(df.columns) == set(issue_processing.REQUIRED_ISSUE_COLUMNS)

def test_generate_issue_id():
    # No existing IDs
    ids = pd.Series([])
    assert issue_processing._generate_issue_id(ids) == 'ISSUE-001'
    # Existing IDs
    ids = pd.Series(['ISSUE-001', 'ISSUE-002'])
    assert issue_processing._generate_issue_id(ids) == 'ISSUE-003'
    # Non-matching IDs
    ids = pd.Series(['foo', 'bar'])
    assert issue_processing._generate_issue_id(ids) == 'ISSUE-001'

def test_add_issue(tmp_path):
    # Add an issue to an empty folder
    folder = str(tmp_path)
    new_id = issue_processing.add_issue('Bob', 'FUND2', 'S&P', '2024-01-02', 'desc2', None, folder)
    df = issue_processing.load_issues(folder)
    assert new_id.startswith('ISSUE-')
    assert (df['IssueID'] == new_id).any()
    assert (df['RaisedBy'] == 'Bob').any()

def test_close_issue(tmp_path):
    # Add and then close an issue
    folder = str(tmp_path)
    new_id = issue_processing.add_issue('Carol', 'FUND3', 'S&P', '2024-01-03', 'desc3', None, folder)
    closed = issue_processing.close_issue(new_id, 'Admin', 'Fixed', folder)
    df = issue_processing.load_issues(folder)
    assert closed is True
    row = df[df['IssueID'] == new_id].iloc[0]
    assert row['Status'] == 'Closed'
    assert row['ClosedBy'] == 'Admin'
    assert row['ResolutionComment'] == 'Fixed'

def test_load_fund_list(tmp_path):
    # Create a FundList.csv with various column names
    folder = tmp_path
    for col in ['FundCode', 'Code', 'Fund Code']:
        df = pd.DataFrame({col: ['FUND1', 'FUND2']})
        file_path = folder / 'FundList.csv'
        df.to_csv(file_path, index=False)
        result = issue_processing.load_fund_list(str(folder))
        assert set(result) == {'FUND1', 'FUND2'} 