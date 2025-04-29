# Purpose: Unit tests for attribution_processing.py, covering L2/L1 sum, residual computation, and normalization.

import pytest
import pandas as pd
import numpy as np
import importlib.util
import sys
import os

# Dynamically import attribution_processing from the views directory
spec = importlib.util.spec_from_file_location(
    "attribution_processing",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../views/attribution_processing.py")
    ),
)
attribution_processing = importlib.util.module_from_spec(spec)
sys.modules["attribution_processing"] = attribution_processing
spec.loader.exec_module(attribution_processing)

sum_l2s_block = attribution_processing.sum_l2s_block
sum_l1s_block = attribution_processing.sum_l1s_block
compute_residual_block = attribution_processing.compute_residual_block
calc_residual = attribution_processing.calc_residual
norm = attribution_processing.norm


# --- sum_l2s_block ---
def test_sum_l2s_block():
    df = pd.DataFrame({"preA": [1, 2], "preB": [3, 4]})
    result = sum_l2s_block(df, "pre", ["A", "B"])
    assert result == [3, 7]


# --- sum_l1s_block ---
def test_sum_l1s_block():
    df = pd.DataFrame({"preA": [1, -2], "preB": [3, -4], "preC": [5, 6]})
    l1_groups = {"G1": ["A", "B"], "G2": ["C"]}
    result = sum_l1s_block(df, "pre", l1_groups)
    assert result == [-2, 11]


# --- compute_residual_block ---
def test_compute_residual_block():
    df = pd.DataFrame({"L0": [10, 10], "l2A": [5, 2], "l2B": [3, 4]})
    result = compute_residual_block(df, "L0", "l2", ["A", "B"])
    # L0 sum = 20, l2A sum = 7, l2B sum = 7, residual = 20 - 14 = 6
    assert result == 6


# --- calc_residual ---
def test_calc_residual():
    row = {"L0": 10, "l1A": 3, "l1B": 2}
    result = calc_residual(row, "L0", "l1", ["A", "B"])
    assert result == 5


# --- norm ---
def test_norm():
    row = {"val": 10, "w": 2}
    result = norm(row, "val", "w", True)
    assert result == 5
    # No normalization
    result2 = norm(row, "val", "w", False)
    assert result2 == 10
