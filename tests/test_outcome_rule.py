"""Tests for Deriv 5-Tick contract outcome evaluation:
- Signal at tick i (e.g. index 60)
- Entry Spot S_0 at tick i+1 (index 61)
- Expiry Spot S_5 at tick i+6 (index 66)
- Exactly 5 consecutive transitions between entry and expiry
- Ties (Exit == Entry) count as loss for both directions.
"""
import numpy as np
import pandas as pd
import pytest

from features import compute_features


def test_rise_and_fall_win_rules():
    # Construct precise deterministic price sequence of 100 ticks
    # Valid feature range after rolling 50-tick window is indices 55 to 94.
    # We choose index 60 as the decision tick:
    # index 61: entry tick S_0 (price = 100.0)
    # index 66: exit tick S_5 (price = 102.0) -> RISE wins (S_5 > S_0)
    base_prices = [100.0 + i * 0.01 for i in range(100)]
    base_prices[61] = 100.0
    base_prices[66] = 102.0
    df = pd.DataFrame({"price": base_prices, "epoch": np.arange(1700000001, 1700000001 + 100 * 2, 2)})
    f = compute_features(df, duration_ticks=5)
    
    row_60 = f.loc[60]
    assert row_60["entry_price"] == 100.0
    assert row_60["exit_price"] == 102.0
    assert row_60["rise_win"] == 1.0
    assert row_60["fall_win"] == 0.0


def test_tie_counts_as_loss_for_both():
    # If exit price equals entry price, both rise_win and fall_win must be 0.0
    base_prices = [100.0 + i * 0.01 for i in range(100)]
    base_prices[61] = 100.0
    base_prices[66] = 100.0  # Equal -> Tie
    df = pd.DataFrame({"price": base_prices, "epoch": np.arange(1700000001, 1700000001 + 100 * 2, 2)})
    f = compute_features(df, duration_ticks=5)
    
    row_60 = f.loc[60]
    assert row_60["entry_price"] == 100.0
    assert row_60["exit_price"] == 100.0
    assert row_60["rise_win"] == 0.0
    assert row_60["fall_win"] == 0.0


def test_fall_win_rule():
    base_prices = [100.0 + i * 0.01 for i in range(100)]
    base_prices[61] = 100.0
    base_prices[66] = 98.0  # Exit < Entry -> Fall wins
    df = pd.DataFrame({"price": base_prices, "epoch": np.arange(1700000001, 1700000001 + 100 * 2, 2)})
    f = compute_features(df, duration_ticks=5)
    
    row_60 = f.loc[60]
    assert row_60["entry_price"] == 100.0
    assert row_60["exit_price"] == 98.0
    assert row_60["rise_win"] == 0.0
    assert row_60["fall_win"] == 1.0

