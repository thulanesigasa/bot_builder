"""Null hypothesis validation test.
Shuffles price differences to destroy any serial dependency or pattern.
All setups on the shuffled series must fall back to approximately 50% win rate
(within random sampling variance, no setup should exceed z > 3.0).
"""
import numpy as np
import pandas as pd
import pytest

from features import compute_features
from strategy import SETUPS
from probability import evaluate_setup


def test_null_shuffled_increments():
    np.random.seed(12345)
    n = 25_000
    epochs = np.arange(1700000001, 1700000001 + n * 2, 2)
    
    # Generate random increments and shuffle them
    increments = np.random.normal(0, 1.25, n)
    np.random.shuffle(increments)
    prices = 1000.0 + np.cumsum(increments)
    
    df = pd.DataFrame({"epoch": epochs, "price": prices})
    f = compute_features(df, duration_ticks=5)
    
    # Evaluate every setup
    payout_ratio = 0.953
    for name, (fn, side) in SETUPS.items():
        mask = fn(f)
        stats = evaluate_setup(f, mask, side, payout_ratio, name=name)
        if stats.sample_size > 100:
            if side in ("runhigh", "runlow", "only_ups", "only_downs"):
                # Under null distribution for 5 consecutive transitions, win rate is ~3.125% (between 1.5% and 5.0%)
                assert 0.015 <= stats.win_rate <= 0.050, (
                    f"RUNHIGH/RUNLOW setup '{name}' unexpectedly deviated from baseline 3.125%: WR = {stats.win_rate:.2%}"
                )
            else:
                # Under null distribution for binary Rise/Fall, win rate must be close to 50%
                assert 0.44 <= stats.win_rate <= 0.56, (
                    f"Setup '{name}' unexpectedly deviated from 50% on null shuffled series: WR = {stats.win_rate:.2%}"
                )
            # No setup should pass z > 3.0 against break-even
            assert stats.z_score < 3.0, (
                f"Setup '{name}' produced false positive edge on null data: z = {stats.z_score:.2f}"
            )
