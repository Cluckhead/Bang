# discount.py
# Purpose: Discount-factor and present-value utilities with configurable
#          compounding basis.

from __future__ import annotations

import math
from typing import List, Literal, Union

from .interpolation import linear_interpolate

__all__ = [
    "discount_factor",
    "pv_cashflows",
    "Compounding",
]

Compounding = Literal["annual", "semiannual", "quarterly", "monthly", "continuous"]


def _normalise_compounding(comp: Union[Compounding, int]) -> Compounding:
    """Normalise compounding input to supported string literal.

    Accepts common integer shorthands: 1→annual, 2→semiannual, 4→quarterly, 12→monthly.
    """
    if isinstance(comp, int):
        mapping = {1: "annual", 2: "semiannual", 4: "quarterly", 12: "monthly"}
        if comp in mapping:
            return mapping[comp]  # type: ignore[return-value]
        raise ValueError(f"Unsupported integer compounding: {comp}")
    return comp


def discount_factor(rate: float, t: float, comp: Union[Compounding, int] = "annual") -> float:
    """Return discount factor under *comp* compounding convention."""
    comp = _normalise_compounding(comp)
    if comp == "annual":
        return 1.0 / (1.0 + rate) ** t
    elif comp == "semiannual":
        m = 2
        return 1.0 / (1.0 + rate / m) ** (m * t)
    elif comp == "quarterly":
        m = 4
        return 1.0 / (1.0 + rate / m) ** (m * t)
    elif comp == "monthly":
        m = 12
        return 1.0 / (1.0 + rate / m) ** (m * t)
    elif comp == "continuous":
        return math.exp(-rate * t)
    else:
        raise ValueError(f"Unsupported compounding convention: {comp}")


def pv_cashflows(
    times: List[float],
    cfs: List[float],
    zero_times: List[float],
    zero_rates: List[float],
    *,
    spread: float = 0.0,
    comp: Union[Compounding, int] = "annual",
    interp: str = "linear",
) -> float:
    """Present value of *cfs* at *times* discounted on the zero curve (+spread).

    Notes
    - ``interp`` selects interpolation method for the zero curve ("linear" or "cubic").
    - ``spread`` is an additive yield adjustment in the same compounding basis as ``comp``.
    """
    total = 0.0
    for cf, t in zip(cfs, times):
        r = linear_interpolate(zero_times, zero_rates, t, method=interp) + spread
        total += cf * discount_factor(r, t, comp)
    return total 
