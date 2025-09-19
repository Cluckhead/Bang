# interpolation.py
# Purpose: Shape-preserving monotone-convex (PCHIP-style) interpolation helpers for
#          zero curves, plus forward-rate calculation utilities.

from __future__ import annotations

from bisect import bisect_left
from typing import List

__all__ = ["linear_interpolate", "forward_rate"]


# ---------------------------------------------------------------------------
# Monotone-convex cubic Hermite interpolation (Hagan–West / PCHIP variant)
# ---------------------------------------------------------------------------


def linear_interpolate(x_list: List[float], y_list: List[float], x: float, method: str = "linear") -> float:
    """Interpolation with configurable method.

    Parameters
    ----------
    x_list : list[float]
        X coordinates of data points
    y_list : list[float]
        Y coordinates of data points
    x : float
        Point at which to interpolate
    method : str
        Interpolation method: "linear" (default) or "cubic" (PCHIP)

    Notes
    - For backward compatibility and simplicity, defaults to true linear interpolation
    - "cubic" uses monotone shape‑preserving cubic Hermite (PCHIP) interpolation
    - Outside the knot range the nearest endpoint value is returned (flat extrapolation)
    """
    n = len(x_list)
    if n < 2:
        raise ValueError("Need at least two points for interpolation")

    if x <= x_list[0]:
        return y_list[0]
    if x >= x_list[-1]:
        return y_list[-1]

    k = bisect_left(x_list, x) - 1  # x_k <= x < x_{k+1}
    
    if method == "linear":
        # True linear interpolation
        x0, x1 = x_list[k], x_list[k + 1]
        y0, y1 = y_list[k], y_list[k + 1]
        # Linear interpolation formula: y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        t = (x - x0) / (x1 - x0)
        return y0 + (y1 - y0) * t
    
    elif method == "cubic":
        # PCHIP cubic interpolation (original sophisticated method)
        # Slopes & knot derivatives (compute once per call – fine for small curves)
        dx = [x_list[i + 1] - x_list[i] for i in range(n - 1)]
        m = [(y_list[i + 1] - y_list[i]) / dx[i] for i in range(n - 1)]

        d = [0.0] * n
        d[0] = m[0]
        d[-1] = m[-1]
        for i in range(1, n - 1):
            if m[i - 1] * m[i] <= 0:
                d[i] = 0.0
            else:
                w1 = 2.0 * dx[i] + dx[i - 1]
                w2 = dx[i] + 2.0 * dx[i - 1]
                d[i] = (w1 + w2) / (w1 / m[i - 1] + w2 / m[i])

        h = dx[k]
        t = (x - x_list[k]) / h  # normalised 0-1

        y_k, y_k1 = y_list[k], y_list[k + 1]
        d_k, d_k1 = d[k], d[k + 1]

        h00 = (1 + 2 * t) * (1 - t) ** 2
        h10 = t * (1 - t) ** 2
        h01 = t ** 2 * (3 - 2 * t)
        h11 = t ** 2 * (t - 1)

        return (
            h00 * y_k
            + h10 * h * d_k
            + h01 * y_k1
            + h11 * h * d_k1
        )
    else:
        # Default to linear for unknown methods
        return linear_interpolate(x_list, y_list, x, "linear")


def forward_rate(
    zero_times: List[float],
    zero_rates: List[float],
    t1: float,
    t2: float,
    compounding: str = "annual",
    *,
    interp: str = "linear",
) -> float:
    """Annualised forward rate between *t1* and *t2* derived from zero yields.

    Parameters
    ----------
    zero_times : list[float]
        Time points for zero curve
    zero_rates : list[float]
        Zero rates corresponding to time points
    t1, t2 : float
        Start and end times for forward rate period
    compounding : str
        Compounding frequency: "annual", "semiannual", "quarterly", or "continuous"

    Returns
    -------
    float
        Annualised forward rate
    """
    if t2 <= t1:
        raise ValueError("t2 must exceed t1 for forward rate calculation")

    from math import pow, exp  # local import keeps module footprint minimal

    r1 = linear_interpolate(zero_times, zero_rates, t1, method=interp)
    r2 = linear_interpolate(zero_times, zero_rates, t2, method=interp)

    # Calculate discount factors based on compounding convention
    if compounding == "continuous":
        df1 = exp(-r1 * t1)
        df2 = exp(-r2 * t2)
    elif compounding == "annual":
        df1 = 1.0 / pow(1.0 + r1, t1)
        df2 = 1.0 / pow(1.0 + r2, t2)
    elif compounding == "semiannual":
        df1 = 1.0 / pow(1.0 + r1/2, 2 * t1)
        df2 = 1.0 / pow(1.0 + r2/2, 2 * t2)
    elif compounding == "quarterly":
        df1 = 1.0 / pow(1.0 + r1/4, 4 * t1)
        df2 = 1.0 / pow(1.0 + r2/4, 4 * t2)
    else:
        raise ValueError(f"Unsupported compounding: {compounding}")

    return (df1 / df2 - 1.0) / (t2 - t1) 
