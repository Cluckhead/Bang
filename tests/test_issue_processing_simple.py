# test_issue_processing_simple.py
# Purpose: Simple tests for analytics/issue_processing.py core functionality

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, date

# Import functions to test
from analytics.issue_processing import (
    load_issues,
    _generate_issue_id,
    _serialize_comments,
    _deserialize_comments,
    REQUIRED_ISSUE_COLUMNS
)


def create_test_csv(path: str, data: Dict[str, Any]) -> None:
    """Helper to create test CSV files."""
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)


class TestLoadIssuesBasic:
    """Test basic load_issues functionality."""

    def test_load_issues_missing_file_returns_empty_with_columns(self, tmp_path):
        """Test that missing file returns empty DataFrame with required columns."""
        df = load_issues(str(tmp_path))
        
        # Should return empty DataFrame with all required columns
        assert df.empty
        for col in REQUIRED_ISSUE_COLUMNS:
            assert col in df.columns, f"Missing required column: {col}"

    def test_load_issues_with_all_columns(self, tmp_path):
        """Test loading issues file that has all required columns."""
        issue_data = {
            'IssueID': ['ISSUE-001'],
            'DateRaised': ['2025-01-01'],
            'RaisedBy': ['TestUser'],
            'FundImpacted': ['F1'],
            'DataSource': ['TestSource'],
            'IssueDate': ['2025-01-01'],
            'Description': ['Test issue'],
            'JiraLink': ['JIRA-123'],
            'InScopeForGoLive': ['Yes'],
            'Status': ['Open'],
            'DateClosed': [''],
            'ClosedBy': [''],
            'ResolutionComment': [''],
            'Comments': ['[]']
        }
        
        create_test_csv(str(tmp_path / "data_issues.csv"), issue_data)
        
        df = load_issues(str(tmp_path))
        
        assert len(df) == 1
        assert df.loc[0, 'IssueID'] == 'ISSUE-001'
        assert df.loc[0, 'Description'] == 'Test issue'
        assert df.loc[0, 'Status'] == 'Open'

    def test_load_issues_handles_empty_file(self, tmp_path):
        """Test handling of empty CSV file."""
        # Create empty file with headers only
        empty_df = pd.DataFrame(columns=['IssueID', 'Description'])
        empty_df.to_csv(str(tmp_path / "data_issues.csv"), index=False)
        
        df = load_issues(str(tmp_path))
        
        # Should add missing columns and return empty DataFrame
        assert df.empty
        for col in REQUIRED_ISSUE_COLUMNS:
            assert col in df.columns


class TestGenerateIssueId:
    """Test the _generate_issue_id function."""

    def test_generate_first_issue_id(self):
        """Test generating the first issue ID."""
        empty_series = pd.Series([], dtype=str)
        issue_id = _generate_issue_id(empty_series)
        assert issue_id == 'ISSUE-001'

    def test_generate_incremental_issue_id(self):
        """Test generating incremental issue IDs."""
        existing_ids = pd.Series(['ISSUE-001', 'ISSUE-002'])
        next_id = _generate_issue_id(existing_ids)
        assert next_id == 'ISSUE-003'

    def test_generate_id_with_gaps(self):
        """Test generating ID with gaps in sequence."""
        existing_ids = pd.Series(['ISSUE-001', 'ISSUE-005', 'ISSUE-003'])
        next_id = _generate_issue_id(existing_ids)
        assert next_id == 'ISSUE-006'  # Should be max + 1

    def test_generate_id_handles_invalid_format(self):
        """Test handling of invalid issue ID formats."""
        mixed_ids = pd.Series(['ISSUE-001', 'INVALID-ID', 'ISSUE-002'])
        next_id = _generate_issue_id(mixed_ids)
        assert next_id == 'ISSUE-003'  # Should only count valid ISSUE-XXX format

    def test_generate_id_handles_empty_and_nan(self):
        """Test handling of empty strings and NaN values."""
        mixed_series = pd.Series(['ISSUE-001', '', np.nan, 'ISSUE-002'])
        next_id = _generate_issue_id(mixed_series)
        assert next_id == 'ISSUE-003'


class TestCommentSerialization:
    """Test comment serialization functions."""

    def test_serialize_comments_valid_list(self):
        """Test serializing valid comment list."""
        comments = [
            {'user': 'User1', 'timestamp': '2025-01-01', 'comment': 'First comment'},
            {'user': 'User2', 'timestamp': '2025-01-02', 'comment': 'Second comment'}
        ]
        
        result = _serialize_comments(comments)
        assert isinstance(result, str)
        
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == comments

    def test_serialize_empty_comments(self):
        """Test serializing empty comments list."""
        result = _serialize_comments([])
        assert result == '[]'

    def test_deserialize_valid_json(self):
        """Test deserializing valid JSON string."""
        comments_json = '[{"user": "User1", "comment": "Test"}]'
        result = _deserialize_comments(comments_json)
        
        assert len(result) == 1
        assert result[0]['user'] == 'User1'
        assert result[0]['comment'] == 'Test'

    def test_deserialize_empty_string(self):
        """Test deserializing empty string."""
        assert _deserialize_comments('') == []
        assert _deserialize_comments('[]') == []

    def test_deserialize_invalid_json(self):
        """Test deserializing invalid JSON returns empty list."""
        assert _deserialize_comments('invalid json') == []
        assert _deserialize_comments('[invalid}') == []
        # 'null' is valid JSON but deserializes to None, which the function might return
        null_result = _deserialize_comments('null')
        assert null_result == [] or null_result is None

    def test_serialize_deserialize_roundtrip(self):
        """Test that serialize/deserialize is a perfect roundtrip."""
        original_comments = [
            {
                'user': 'TestUser',
                'timestamp': '2025-01-01 10:00:00',
                'comment': 'Comment with "quotes" and [brackets] and {braces}'
            }
        ]
        
        serialized = _serialize_comments(original_comments)
        deserialized = _deserialize_comments(serialized)
        
        assert deserialized == original_comments


class TestConstants:
    """Test module constants."""

    def test_required_issue_columns_defined(self):
        """Test that required issue columns are properly defined."""
        expected_columns = [
            'IssueID', 'DateRaised', 'RaisedBy', 'FundImpacted', 'DataSource',
            'IssueDate', 'Description', 'JiraLink', 'InScopeForGoLive', 'Status',
            'DateClosed', 'ClosedBy', 'ResolutionComment', 'Comments'
        ]
        
        assert len(REQUIRED_ISSUE_COLUMNS) == len(expected_columns)
        for col in expected_columns:
            assert col in REQUIRED_ISSUE_COLUMNS

    def test_required_columns_are_strings(self):
        """Test that all required column names are strings."""
        for col in REQUIRED_ISSUE_COLUMNS:
            assert isinstance(col, str)
            assert len(col) > 0