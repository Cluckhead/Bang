import importlib
from typing import Callable, Dict


def test_analytics_imports_and_noop_calls():
    """
    Smoke test: import analytics modules and execute a minimal no-op path
    where safe, to catch early regressions like missing deps or syntax errors.
    """
    modules = [
        "analytics.file_delivery_processing",
        "analytics.issue_processing",
        "analytics.maxmin_processing",
        "analytics.metric_calculator",
        "analytics.security_data_provider",
        "analytics.security_processing",
        "analytics.staleness_processing",
        "analytics.synth_analytics_csv_processor",
        "analytics.synth_spread_calculator",
        "analytics.synth_spread_calculator_refactored",
        "analytics.ticket_processing",
        "analytics.trade_settlement",
    ]

    # Per-module minimal, safe probe calls to exercise a no-op code path.
    # Probes should be side-effect free and fast.
    probes: Dict[str, Callable[[object], None]] = {}

    try:
        import pandas as pd  # type: ignore
        import numpy as np  # noqa: F401
    except Exception:  # If pandas is unavailable, fallback probes will still import modules
        pd = None  # type: ignore

    # Define probes that are safe regardless of external data presence
    probes["analytics.file_delivery_processing"] = (
        lambda m: m._hash_headers([])
    )
    probes["analytics.issue_processing"] = (
        lambda m: (m._serialize_comments([]), m._deserialize_comments("[]"))
    )
    probes["analytics.synth_spread_calculator"] = (
        lambda m: m.get_supported_day_basis("30E/360")
    )
    probes["analytics.synth_spread_calculator_refactored"] = (
        lambda m: m.convert_term_to_years("1D")
    )
    probes["analytics.ticket_processing"] = (
        lambda m: m.generate_event_hash("Check", "ID", "file.csv: Value 10 > threshold 5")
    )

    # Optional probes that use pandas but should be safe/fast
    if pd is not None:
        probes["analytics.metric_calculator"] = (
            lambda m: m._calculate_column_stats(
                pd.Series(dtype=float), pd.Series(dtype=float), pd.Timestamp("2024-01-01"), "Value"
            )
        )
        probes["analytics.trade_settlement"] = (
            # Returns immediately for empty DataFrame
            lambda m: m.process_trades_with_settlement(pd.DataFrame())
        )
        probes["analytics.security_data_provider"] = (
            # Dataclass construction is side-effect free; avoid provider instantiation
            lambda m: m.SecurityData(isin="TEST", base_isin="TEST")
        )

    for name in modules:
        mod = importlib.import_module(name)
        assert mod is not None, f"Failed to import {name}"

        # Run probe if defined for this module
        probe = probes.get(name)
        if probe is not None:
            probe(mod)

