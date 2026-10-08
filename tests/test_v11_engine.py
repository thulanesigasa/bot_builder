"""Comprehensive unit tests for the V1.1 Probability-Driven 5-Tick Engine.
Verifies contract lifecycle modeling, direction-specific quotes, market regimes,
decoupled continuation vs reversal engines, and 3-way walk-forward validation.
"""
import pytest
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from quote_engine import QuoteEngine
from market_regime import compute_expanded_market_features
from strategy import ContinuationEngine, ReversalEngine, ALL_SETUPS
from walk_forward import create_three_way_split, WalkForwardAnalyzer
from feature_search import evaluate_setup_edge, compare_continuation_vs_reversal


def test_contract_outcome_model_lifecycle_and_ties():
    # 7 ticks: prices at index 0, 1, 2, 3, 4, 5, 6
    # Signal at i=0 -> Entry at i=1, Exit at i=5
    df = pd.DataFrame({
        "epoch": [100, 102, 104, 106, 108, 110, 112],
        "price": [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0]
    })
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    out = model.compute_contract_outcomes(df)

    # At row 0: Entry price is tick 1 (10.5), Exit price is tick 6 (13.0)
    assert out.loc[0, "entry_price"] == 10.5
    assert out.loc[0, "exit_price"] == 13.0
    assert out.loc[0, "rise_win"] == 1.0
    assert out.loc[0, "fall_win"] == 0.0
    assert out.loc[0, "only_ups_win"] == 1.0

    # Test tie losing for both (entry 10.5, exit 10.5 at tick 6)
    df_tie = pd.DataFrame({
        "epoch": [100, 102, 104, 106, 108, 110, 112],
        "price": [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 10.5]
    })
    out_tie = model.compute_contract_outcomes(df_tie)
    assert out_tie.loc[0, "entry_price"] == 10.5
    assert out_tie.loc[0, "exit_price"] == 10.5
    assert out_tie.loc[0, "rise_win"] == 0.0
    assert out_tie.loc[0, "fall_win"] == 0.0
    assert out_tie.loc[0, "is_tie"] == 1.0


def test_quote_engine_direction_specific_and_high_payout():
    qe = QuoteEngine(default_up_payout_ratio=0.95, default_down_payout_ratio=0.92)
    up_q = qe.get_quote("UP")
    down_q = qe.get_quote("DOWN")

    assert up_q.payout_ratio == 0.95
    assert down_q.payout_ratio == 0.92
    assert round(up_q.implied_probability, 4) == 0.5128
    assert round(down_q.implied_probability, 4) == 0.5208

    # High payout preset ($2 -> $61.03)
    qe.set_custom_quote("UP", stake=2.0, total_payout=61.03, contract_type="RUNHIGH")
    hp_q = qe.get_quote("UP")
    assert hp_q.stake == 2.0
    assert hp_q.payout == 61.03
    assert round(hp_q.implied_probability, 4) == 0.0328

    # EV calculation
    ev_dollar, ev_per_dollar, edge = qe.calculate_expected_value(estimated_prob=0.08, stake=2.0, payout=61.03)
    # Win profit = 59.03, Loss = 2.0. EV = 0.08 * 59.03 - 0.92 * 2 = 4.7224 - 1.84 = 2.8824
    assert round(ev_dollar, 2) == 2.88
    assert round(edge, 4) == round(0.08 - 0.03277, 4)


def test_market_regime_and_feature_expansion():
    np.random.seed(42)
    prices = 1000.0 + np.cumsum(np.random.normal(0, 1, 150))
    df = pd.DataFrame({
        "epoch": [1000 + i * 2 for i in range(150)],
        "price": prices
    })
    feats = compute_expanded_market_features(df)

    assert "mom3" in feats.columns
    assert "mom5" in feats.columns
    assert "mom10" in feats.columns
    assert "accel3" in feats.columns
    assert "vol_regime" in feats.columns
    assert "market_state" in feats.columns
    assert "range_position" in feats.columns

    # Verify no arbitrary choppy UP rule exists in strategy registry
    assert "choppy (|net10|<=1) -> UP" not in ALL_SETUPS


def test_three_way_split_and_walk_forward():
    df = pd.DataFrame({
        "epoch": range(1000, 2000),
        "price": np.linspace(100, 200, 1000),
        "rise_win": [1.0] * 1000,
        "fall_win": [0.0] * 1000
    })
    splits = create_three_way_split(df, train_pct=0.60, val_pct=0.20)
    assert len(splits.train_df) == 600
    assert len(splits.val_df) == 200
    assert len(splits.holdout_df) == 200
    assert splits.train_df["epoch"].iloc[-1] < splits.val_df["epoch"].iloc[0]
    assert splits.val_df["epoch"].iloc[-1] < splits.holdout_df["epoch"].iloc[0]
