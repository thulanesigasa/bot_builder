"""Tests ensuring zero lookahead bias in feature engineering.
Features at tick index i must remain identical regardless of any future tick values after i.
"""
import numpy as np
import pandas as pd
import pytest

from features import compute_features

INDICATOR_COLUMNS = [
    "streak", "net5", "net10", "net20", "volatility",
    "mom", "accel", "from_high", "from_low", "last_tick"
]


def test_no_lookahead_when_future_changes():
    np.random.seed(42)
    n = 200
    epochs = np.arange(1700000001, 1700000001 + n * 2, 2)
    
    # Generate original prices
    steps1 = np.random.normal(0, 1.0, n)
    prices1 = 100.0 + np.cumsum(steps1)
    df1 = pd.DataFrame({"epoch": epochs, "price": prices1})
    f1 = compute_features(df1, duration_ticks=5)

    # Pick an arbitrary test row i (e.g. index 100)
    target_idx = 100
    
    # Create dataset 2: exactly identical prices up to target_idx,
    # but radically different prices after target_idx (e.g. massive jump and high volatility)
    prices2 = prices1.copy()
    np.random.seed(999)
    prices2[target_idx + 1:] = 500.0 + np.cumsum(np.random.normal(5.0, 10.0, n - (target_idx + 1)))
    df2 = pd.DataFrame({"epoch": epochs, "price": prices2})
    f2 = compute_features(df2, duration_ticks=5)

    # Indicators at target_idx must be bitwise/numerically identical
    row1 = f1.loc[target_idx]
    row2 = f2.loc[target_idx]

    for col in INDICATOR_COLUMNS:
        val1 = row1[col]
        val2 = row2[col]
        assert np.isclose(val1, val2, rtol=1e-9, atol=1e-9), (
            f"Lookahead violation detected in column '{col}' at index {target_idx}: {val1} != {val2}"
        )
