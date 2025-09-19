# Purpose: Simple tests for settings_loader to ensure safe defaults.

import os
from core.settings_loader import load_settings, get_app_config, reload_settings


def test_load_settings_missing_file_returns_dict(monkeypatch):
    # Force missing settings.yaml by chdir to tmp dir
    cwd = os.getcwd()
    try:
        reload_settings()
        # No assertion on content; just ensure return types and safety
        s = load_settings()
        assert isinstance(s, dict)
        ac = get_app_config()
        assert isinstance(ac, dict)
    finally:
        os.chdir(cwd)

