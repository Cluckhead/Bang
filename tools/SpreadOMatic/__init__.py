# SpreadOMatic package (wrapper)
# Purpose: Expose the internal `spreadomatic` sub-package at import path
# `tools.SpreadOMatic`.  This lets callers simply write
# `from tools.SpreadOMatic.spreadomatic import ...` while retaining the original
# directory structure.

from importlib import import_module as _imp

# Re-export the main sub-package for convenience
spreadomatic = _imp('tools.SpreadOMatic.spreadomatic')

__all__ = [
    'spreadomatic',
]
