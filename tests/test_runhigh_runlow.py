"""Unit tests for V1.2 RUNHIGH / RUNLOW (Only Ups / Only Downs) Probability Engine."""
import pytest
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from quote_engine import QuoteEngine
from market_regime import compute_expanded_market_features
from strategy import MarketStateProbabilityModel
from feature_search import search_market_regimes_for_elevated_runs


def test_runhigh_runlow_exact_five_transitions():
    # 8 ticks: index 0 to 7.
    # Signal at i=0. Entry spot at i=1 (price 10.0).
    # Path: i+2 (11.0), i+3 (12.0), i+4 (13.0), i+5 (14.0), i+6 (15.0).
    # That is 5 consecutive upward movements!
    df = pd.DataFrame({
        "epoch": range(1000, 1008),
        "price": [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    })
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1, contract_family="run_high_low")
    out = model.compute_contract_outcomes(df)

    assert out.loc[0, "entry_price"] == 10.0
    assert out.loc[0, "exit_price"] == 15.0
    assert out.loc[0, "runhigh_win"] == 1.0
    assert out.loc[0, "runlow_win"] == 0.0

    # Test single intermediate drop causing RUNHIGH failure
    df_drop = pd.DataFrame({
        "epoch": range(1000, 1008),
        "price": [9.0, 10.0, 11.0, 12.0, 11.5, 14.0, 15.0, 16.0]  # Step 3 drops from 12.0 to 11.5
    })
    out_drop = model.compute_contract_outcomes(df_drop)
    assert out_drop.loc[0, "entry_price"] == 10.0
    assert out_drop.loc[0, "exit_price"] == 15.0  # Finished higher than entry, but NOT uninterrupted!
    assert out_drop.loc[0, "runhigh_win"] == 0.0  # RUNHIGH loses immediately
    assert out_drop.loc[0, "rise_win"] == 1.0     # Comparative Rise/Fall still wins


def test_quote_engine_no_fallback_guarantee():
    qe = QuoteEngine(mode="live")
    # Live mode starts with empty quotes until fetched
    assert qe.get_quote("UP") is None
    assert qe.get_quote("DOWN") is None

    # In research mode, sets exact verified benchmark quote
    qe_research = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    up_q = qe_research.get_quote("UP")
    assert up_q is not None
    assert up_q.stake == 2.0
    assert up_q.payout == 61.03
    assert round(up_q.implied_probability, 5) == round(2.0 / 61.03, 5)


def test_market_state_probability_model():
    np.random.seed(42)
    n = 300
    df = pd.DataFrame({
        "epoch": range(1000, 1000 + n),
        "price": 100.0 + np.cumsum(np.random.normal(0, 1, n)),
        "runhigh_win": np.random.binomial(1, 0.032, n),
        "runlow_win": np.random.binomial(1, 0.032, n),
        "market_regime": ["REGIME_A" if i % 2 == 0 else "REGIME_B" for i in range(n)]
    })
    qe = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    model = MarketStateProbabilityModel(min_sample_size=30, z_threshold=2.0)
    profiles = model.fit(df, qe)

    assert "REGIME_A" in profiles
    assert "REGIME_B" in profiles
    assert profiles["REGIME_A"].sample_size == 150
