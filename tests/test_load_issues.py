# Purpose: Test issue_processing.load_issues adds missing columns without altering row count.

import pandas as pd
from issue_processing import load_issues, REQUIRED_ISSUE_COLUMNS


def _write_issues_csv(tmp_path):
    content = (
        "IssueID,DateRaised,RaisedBy,FundImpacted,DataSource,IssueDate,Description,Status,DateClosed,ClosedBy\n"
        "ISSUE-001,2024-01-01,User1,F1,S&P,2024-01-01,Desc,Open,,\n"
    )
    f = tmp_path / "data_issues.csv"
    f.write_text(content)


def test_load_issues_adds_missing_cols(tmp_path):
    _write_issues_csv(tmp_path)

    df = load_issues(str(tmp_path))

    # All required columns now present
    assert set(REQUIRED_ISSUE_COLUMNS).issubset(df.columns)
    # Row count unchanged (1)
    assert len(df) == 1 