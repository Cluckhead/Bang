# config.py
# Purpose: Central configuration for bond calculation package (paths, constants, setup)

from __future__ import annotations

import os
import sys

# Resolve project root relative to this package directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# Ensure local tools (SpreadOMatic) are importable regardless of CWD
_tools_root = os.path.join(PROJECT_ROOT, "tools")
if _tools_root not in sys.path:
    sys.path.insert(0, _tools_root)

# Data and numerical constants
# Resolve DATA_DIR from settings.yaml -> app_config.data_folder when available,
# falling back to the legacy PROJECT_ROOT/Data path.
def _resolve_data_dir() -> str:
    try:
        # Local import to avoid heavy dependencies/circulars at module import time
        from core.settings_loader import get_app_config  # type: ignore

        app_cfg = get_app_config() or {}
        configured_folder = app_cfg.get("data_folder")
        if configured_folder:
            # Support absolute or project-root-relative paths
            return (
                configured_folder
                if os.path.isabs(configured_folder)
                else os.path.join(PROJECT_ROOT, configured_folder)
            )
    except Exception:
        # If settings are unavailable, fall back to default
        pass

    return os.path.join(PROJECT_ROOT, "Data")


DATA_DIR = _resolve_data_dir()
COMPOUNDING = "semiannual"
TOL = 1e-10
MAX_ITER = 100


