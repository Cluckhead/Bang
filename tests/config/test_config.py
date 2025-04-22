# Purpose: Unit tests for config.py to verify configuration structure and types are maintained.

import pytest
import config

def test_color_palette_is_list():
    """Test that COLOR_PALETTE is a list of strings."""
    assert isinstance(config.COLOR_PALETTE, list)
    assert all(isinstance(color, str) for color in config.COLOR_PALETTE)

def test_data_folder_is_string():
    """Test that DATA_FOLDER is a string and not empty."""
    assert isinstance(config.DATA_FOLDER, str)
    assert config.DATA_FOLDER.strip() != ""

def test_id_column_is_string():
    """Test that ID_COLUMN is a string and not empty."""
    assert isinstance(config.ID_COLUMN, str)
    assert config.ID_COLUMN.strip() != ""

def test_exclusions_file_is_string():
    """Test that EXCLUSIONS_FILE is a string and not empty."""
    assert isinstance(config.EXCLUSIONS_FILE, str)
    assert config.EXCLUSIONS_FILE.strip() != "" 