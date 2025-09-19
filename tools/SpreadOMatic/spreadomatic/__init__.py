"""SpreadOMatic – modular bond analytics toolkit.

This package breaks the original monolithic *spread_calculator.py* into
cohesive sub-modules:

* `daycount`         – day-count conventions and date helpers
* `interpolation`    – monotone splines & forward-rate helper
* `discount`         – discount-factor & PV utilities
* `cashflows`        – cash-flow extraction / schedule generation
* `yield_spread`     – YTM, G-spread, Z-spread
* `duration`         – durations, convexity, key-rate, CS01
* `oas`              – option-adjusted spread (simple Black model)
* `ytw`              – yield to worst calculations for callable bonds

High-level convenience functions will be added over time.  For now you can
import any analytic directly, e.g.::

    from spreadomatic.yield_spread import solve_ytm
    from spreadomatic.ytw import calculate_ytw
"""

from importlib import import_module as _imp

# Re-export frequently used helpers for convenience
# Use relative imports to work with the current package structure
try:
    # Try relative imports first
    from .daycount import year_fraction
    from .yield_spread import solve_ytm, z_spread
    from .duration import key_rate_durations
    from .ytw import calculate_ytw
except ImportError:
    # Fallback to dynamic imports with proper module path
    import sys
    import os
    
    # Get the current module's package name dynamically
    current_package = __name__
    parent_package = ".".join(current_package.split(".")[:-1])
    
    if parent_package:
        daycount_module = f"{current_package}.daycount"
        yield_module = f"{current_package}.yield_spread" 
        duration_module = f"{current_package}.duration"
        ytw_module = f"{current_package}.ytw"
    else:
        daycount_module = "daycount"
        yield_module = "yield_spread"
        duration_module = "duration"
        ytw_module = "ytw"
    
    year_fraction = _imp(daycount_module).year_fraction  # type: ignore
    solve_ytm = _imp(yield_module).solve_ytm  # type: ignore
    z_spread = _imp(yield_module).z_spread  # type: ignore
    key_rate_durations = _imp(duration_module).key_rate_durations  # type: ignore
    calculate_ytw = _imp(ytw_module).calculate_ytw  # type: ignore 