"""Unit tests for V1.3 Statistical Edge Discovery Engine:
- Exact 5-transition lifecycle verification
- Systematic multi-factor state grid search
- Probability lift calculation and candidate auditing
- Brier score, Brier Skill Score (BSS), and Expected Calibration Error (ECE)
- Dynamic historical quote stream and zero-fallback guarantee
"""
import pytest
import numpy as np
import pandas as pd

from contract_model import ContractOutcomeModel
from quote_engine import QuoteEngine, ProposalQuote
from market_regime import compute_expanded_market_features
from feature_search import SystematicStateGridSearch, audit_candidates_on_validation
from probability import (
    compute_probability_lift,
    compute_brier_score,
    compute_brier_skill_score,
    compute_calibration_curve,
    bonferroni_critical_z
)


def test_contract_lifecycle_exact_five_transitions():
    # 8 ticks: index 0 to 7.
    # Signal at i=0. Entry spot at i=1 (price 100.0).
    # Forward ticks:
    # i=2: 101.0 (Step 1 UP)
    # i=3: 102.0 (Step 2 UP)
    # i=4: 103.0 (Step 3 UP)
    # i=5: 104.0 (Step 4 UP)
    # i=6: 105.0 (Step 5 UP - Expiry Spot S_5)
    # i=7: 106.0 (Extra tick)
    df = pd.DataFrame({
        "epoch": range(1000, 1008),
        "price": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    })
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    out = model.compute_contract_outcomes(df)

    assert out.loc[0, "entry_price"] == 100.0
    assert out.loc[0, "exit_price"] == 105.0
    assert out.loc[0, "runhigh_win"] == 1.0
    assert out.loc[0, "runlow_win"] == 0.0

    # Test single intermediate flat tick killing RUNHIGH
    df_flat = pd.DataFrame({
        "epoch": range(1000, 1008),
        "price": [99.0, 100.0, 101.0, 101.0, 103.0, 104.0, 105.0, 106.0]  # Step 2 is flat (101.0 == 101.0)
    })
    out_flat = model.compute_contract_outcomes(df_flat)
    assert out_flat.loc[0, "runhigh_win"] == 0.0
    assert out_flat.loc[0, "runlow_win"] == 0.0


def test_probability_lift_and_calibration_metrics():
    # Test probability lift calculation
    lift = compute_probability_lift(conditional_prob=0.08, baseline_prob=0.032)
    assert round(lift, 2) == 2.50

    # Perfect forecast vs random forecast
    y_true = np.array([1, 0, 0, 0, 1])
    y_prob = np.array([0.9, 0.1, 0.1, 0.1, 0.8])
    brier = compute_brier_score(y_true, y_prob)
    assert brier < 0.10

    # Brier skill score relative to baseline rate of 0.40
    bss = compute_brier_skill_score(y_true, y_prob, baseline_prob=0.40)
    assert bss > 0.0  # Positive skill demonstrated

    # Calibration curve
    cal = compute_calibration_curve(y_true, y_prob, n_bins=3, baseline_prob=0.40)
    assert "ece" in cal
    assert "brier_skill_score" in cal
    assert cal["ece"] >= 0.0


def test_systematic_state_grid_search_and_validation_audit():
    np.random.seed(42)
    n = 200
    prices = 1000.0 + np.cumsum(np.random.normal(0, 1, n))
    df = pd.DataFrame({
        "epoch": range(1000, 1000 + n),
        "price": prices
    })
    feats = compute_expanded_market_features(df)
    model = ContractOutcomeModel(duration_ticks=5, entry_offset=1)
    outcomes = model.compute_contract_outcomes(df)
    for col in ["runhigh_win", "runlow_win"]:
        feats[col] = outcomes[col]
    feats = feats.dropna()

    qe = QuoteEngine(mode="research", benchmark_stake=2.0, benchmark_payout=61.03)
    grid = SystematicStateGridSearch(min_sample_size=15, candidate_z_threshold=1.0, min_lift_threshold=1.0)
    results = grid.search(feats, qe)

    assert results["total_states_evaluated"] > 100
    assert "bonferroni_critical_z" in results
    assert "top_runhigh_by_lift" in results
    assert "top_runlow_by_lift" in results

    # Audit candidates on holdout
    val_sub = feats.iloc[-50:].copy()
    audit = audit_candidates_on_validation(val_sub, results["runhigh_candidates"][:5], qe, min_val_n=5)
    assert isinstance(audit, list)


def test_quote_engine_historical_stream_lookup():
    qe = QuoteEngine(mode="research")
    now_epoch = 1700000000

    # Record two timestamped quotes
    qe.record_quote_snapshot(epoch=now_epoch, runhigh_payout=62.50, runlow_payout=60.00, stake=2.0)
    qe.record_quote_snapshot(epoch=now_epoch + 100, runhigh_payout=65.00, runlow_payout=58.00, stake=2.0)

    # Lookup at epoch + 10 (should match first quote)
    q1 = qe.get_quote("UP", epoch=now_epoch + 10)
    assert q1 is not None
    assert q1.payout == 62.50
    assert q1.source == "historical_quote_stream"

    # Lookup at epoch + 110 (should match second quote)
    q2 = qe.get_quote("UP", epoch=now_epoch + 110)
    assert q2 is not None
    assert q2.payout == 65.00

    # Down quote
    q_down = qe.get_quote("DOWN", epoch=now_epoch + 110)
    assert q_down is not None
    assert q_down.payout == 58.00
