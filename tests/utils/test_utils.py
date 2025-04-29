# Purpose: Unit tests for utility functions in utils.py, covering date parsing, fund list parsing, data folder path, exclusions, weights, and NaN replacement.

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
import os

import utils


# _is_date_like tests
def test_is_date_like_valid_formats():
    # TODO: Implement tests for valid date strings
    pass


def test_is_date_like_invalid_formats():
    # TODO: Implement tests for invalid date strings
    pass


# parse_fund_list tests
def test_parse_fund_list_valid():
    # TODO: Implement tests for valid fund list inputs
    pass


def test_parse_fund_list_empty():
    # TODO: Implement tests for empty input
    pass


def test_parse_fund_list_malformed():
    # TODO: Implement tests for malformed input
    pass


# get_data_folder_path tests
def test_get_data_folder_path_config_set(mocker, tmp_path):
    """Test when config.DATA_FOLDER is set to a valid absolute path."""
    fake_path = str(tmp_path / "data_folder")
    mocker.patch("config.DATA_FOLDER", fake_path, create=True)
    mocker.patch("os.path.isabs", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    # Should return the absolute path from config
    result = utils.get_data_folder_path()
    assert result == fake_path


def test_get_data_folder_path_config_missing(mocker, tmp_path):
    """Test when config.DATA_FOLDER is missing (ImportError)."""
    # Remove 'config' from sys.modules so import will fail
    mocker.patch.dict("sys.modules", {"config": None})
    fake_cwd = str(tmp_path)
    mocker.patch("os.getcwd", return_value=fake_cwd)
    mocker.patch("os.path.isabs", return_value=False)
    mocker.patch("os.path.isdir", return_value=True)
    # Should fall back to default relative path resolved from cwd
    result = utils.get_data_folder_path()
    assert result == os.path.abspath(os.path.join(fake_cwd, "Data"))


def test_get_data_folder_path_relative_path(mocker, tmp_path):
    """Test when config.DATA_FOLDER is a relative path."""
    mocker.patch("config.DATA_FOLDER", "relative_folder", create=True)
    fake_cwd = str(tmp_path)
    mocker.patch("os.getcwd", return_value=fake_cwd)
    mocker.patch("os.path.isabs", return_value=False)
    mocker.patch("os.path.isdir", return_value=True)
    # Should resolve relative path from cwd
    result = utils.get_data_folder_path()
    assert result == os.path.abspath(os.path.join(fake_cwd, "relative_folder"))


def test_get_data_folder_path_absolute_path(mocker, tmp_path):
    """Test when config.DATA_FOLDER is an absolute path."""
    abs_path = str(tmp_path / "abs_data")
    mocker.patch("config.DATA_FOLDER", abs_path, create=True)
    mocker.patch("os.path.isabs", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    # Should use the absolute path directly
    result = utils.get_data_folder_path()
    assert result == abs_path


def test_get_data_folder_path_path_not_exist(mocker, tmp_path):
    """Test when the resolved path does not exist (os.path.isdir returns False)."""
    mocker.patch("config.DATA_FOLDER", "Data", create=True)
    fake_cwd = str(tmp_path)
    mocker.patch("os.getcwd", return_value=fake_cwd)
    mocker.patch("os.path.isabs", return_value=False)
    mocker.patch("os.path.isdir", return_value=False)
    # Should still return the resolved path, but log a warning
    result = utils.get_data_folder_path()
    assert result == os.path.abspath(os.path.join(fake_cwd, "Data"))


# load_exclusions tests
def test_load_exclusions_file_not_found(mocker):
    # TODO: Mock os.path.exists and test file not found
    pass


def test_load_exclusions_empty_file(mocker):
    # TODO: Mock pd.read_csv to return empty DataFrame
    pass


def test_load_exclusions_valid_file(mocker):
    # TODO: Mock pd.read_csv to return valid DataFrame
    pass


# load_weights_and_held_status tests
def test_load_weights_and_held_status_wide_format(mocker):
    # TODO: Mock pd.read_csv for wide format
    pass


def test_load_weights_and_held_status_long_format(mocker):
    # TODO: Mock pd.read_csv for long format
    pass


def test_load_weights_and_held_status_missing_columns(mocker):
    # TODO: Mock pd.read_csv with missing columns
    pass


def test_load_weights_and_held_status_date_parsing(mocker):
    # TODO: Mock pd.read_csv with date parsing variations
    pass


def test_load_weights_and_held_status_calculation_logic(mocker):
    # TODO: Mock pd.read_csv and test calculation logic
    pass


# replace_nan_with_none tests
def test_replace_nan_with_none_nested_dict():
    # TODO: Test with nested dictionaries containing NaN
    pass


def test_replace_nan_with_none_list():
    # TODO: Test with lists containing NaN
    pass


def test_replace_nan_with_none_various_types():
    # TODO: Test with various data types including np.nan and pd.NA
    pass
