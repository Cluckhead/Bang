# Purpose: Utility functions for attribution calculations (residuals, L1/L2 aggregation, normalization) used by attribution views.
from typing import List, Dict, Any
import pandas as pd


def sum_l2s_block(df_block: pd.DataFrame, prefix: str, l2_cols: List[str]) -> List[Any]:
    """
    Sums each L2 column in l2_cols for the given DataFrame block, using the specified prefix.
    Returns a list of sums in the same order as l2_cols.
    """
    return [
        df_block[f"{prefix}{col}"].sum() if f"{prefix}{col}" in df_block else 0
        for col in l2_cols
    ]


def sum_l1s_block(
    df_block: pd.DataFrame, prefix: str, l1_groups: Dict[str, List[str]]
) -> List[Any]:
    """
    Sums all L2 columns for each L1 group in l1_groups for the given DataFrame block, using the specified prefix.
    Returns a list of sums in the order of l1_groups.values().
    """
    return [
        df_block[[f"{prefix}{col}" for col in l2s if f"{prefix}{col}" in df_block]]
        .sum()
        .sum()
        for l2s in l1_groups.values()
    ]


def compute_residual_block(
    df_block: pd.DataFrame, l0_col: str, l2_prefix: str, l2_cols: List[str]
) -> Any:
    """
    Computes the residual for a DataFrame block: L0 minus the sum of all L2 columns (with prefix).
    """
    l0 = df_block[l0_col].sum() if l0_col in df_block else 0
    l2_sum = sum(
        [
            (
                df_block[f"{l2_prefix}{col}"].sum()
                if f"{l2_prefix}{col}" in df_block
                else 0
            )
            for col in l2_cols
        ]
    )
    return l0 - l2_sum


def calc_residual(row, l0, l1_prefix, l1_factors):
    """
    Computes the residual for a row: L0 minus the sum of all L1 factors (with prefix).
    """
    l1_sum = sum([row.get(f"{l1_prefix}{f}", 0) for f in l1_factors])
    return row.get(l0, 0) - l1_sum


def norm(row: Dict[str, Any], col: str, weight_col: str, normalize: bool) -> Any:
    """
    Normalizes a value in a row by the weight column if normalize is True and weight is nonzero.
    """
    w = row.get(weight_col, 0)
    v = row.get(col, 0) if col is not None else None
    if normalize and w:
        return v / w if v is not None else None
    return v
