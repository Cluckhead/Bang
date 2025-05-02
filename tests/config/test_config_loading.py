# Purpose: Tests for configuration loading in Simple Data Checker.
# Verifies that COMPARISON_CONFIG and MAXMIN_THRESHOLDS are loaded correctly from their YAML files.
# Uses mocking to isolate file I/O and ensure robust config parsing.

import pytest
import config
from unittest.mock import patch


def test_comparison_config_loaded():
    """Test that COMPARISON_CONFIG is loaded as a non-empty dict from YAML."""
    assert isinstance(config.COMPARISON_CONFIG, dict)
    assert len(config.COMPARISON_CONFIG) > 0
    # Check a known key
    assert 'spread' in config.COMPARISON_CONFIG
    assert 'file1' in config.COMPARISON_CONFIG['spread']


def test_maxmin_thresholds_loaded():
    """Test that MAXMIN_THRESHOLDS is loaded as a non-empty dict from YAML."""
    assert isinstance(config.MAXMIN_THRESHOLDS, dict)
    assert len(config.MAXMIN_THRESHOLDS) > 0
    # Check a known key
    assert 'sec_Spread.csv' in config.MAXMIN_THRESHOLDS
    assert 'min' in config.MAXMIN_THRESHOLDS['sec_Spread.csv']
    assert 'max' in config.MAXMIN_THRESHOLDS['sec_Spread.csv']


def test_comparison_config_mocked(monkeypatch):
    """Test that COMPARISON_CONFIG loads the correct data when load_yaml_config is mocked."""
    dummy_comparison = {
        'dummy': {
            'display_name': 'Dummy',
            'file1': 'dummy1.csv',
            'file2': 'dummy2.csv',
            'value_label': 'Dummy Value',
        }
    }
    with patch('utils.load_yaml_config', return_value=dummy_comparison):
        # Reload config module to trigger re-import with mocked loader
        import importlib
        import config as config_module
        importlib.reload(config_module)
        assert config_module.COMPARISON_CONFIG == dummy_comparison
        assert 'dummy' in config_module.COMPARISON_CONFIG
        assert config_module.COMPARISON_CONFIG['dummy']['file1'] == 'dummy1.csv'


def test_maxmin_thresholds_mocked(monkeypatch):
    """Test that MAXMIN_THRESHOLDS loads the correct data when load_yaml_config is mocked."""
    dummy_thresholds = {
        'dummy.csv': {
            'min': 1,
            'max': 2,
            'display_name': 'Dummy',
            'group': 'Test',
        }
    }
    with patch('utils.load_yaml_config', return_value=dummy_thresholds):
        import importlib
        import config as config_module
        importlib.reload(config_module)
        assert config_module.MAXMIN_THRESHOLDS == dummy_thresholds
        assert 'dummy.csv' in config_module.MAXMIN_THRESHOLDS
        assert config_module.MAXMIN_THRESHOLDS['dummy.csv']['min'] == 1 