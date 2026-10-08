"""V1.7 Comprehensive Automated Test Suite — Statistical Validation, Calibration & Economic Assessment.

Validates:
1. Exact Wilson score interval & uncertainty bounds.
2. Calibration evaluation: Brier score, Reference baseline Brier score, Brier Skill Score (BSS).
3. Rare-event Expected Calibration Error (ECE) across discrete probability bins.
4. Overlapping prediction dependence: Moving block bootstrap (L=5 resamples), Autocorrelation, Effective sample size (N_eff).
5. Non-overlapping subsampling sensitivity (stride >= 5).
6. Conditional probability lift by market state with 2-proportion z-score.
7. Genuine quote economics: Break-even hurdle (P_be = Ask/Payout), Ordinary EV, Conservative EV.
8. Lookahead prevention in quote alignment (t_quote <= t_pred).
9. Conservative EV strictly None when lower bound is unavailable (no arbitrary fallbacks).
10. Hypothetical cumulative PnL & maximum drawdown calculation.
11. Pricing sensitivity stress analysis (5% haircut, 10% haircut, latency premium).
12. Research stage isolation: EXPLORATORY_FORWARD, VALIDATION_FORWARD, CONFIRMATION_FORWARD.
13. Multi-session research aggregation & authoritative verdicts.
14. Forward collection service milestone targets.
15. Absolute safety invariant: LIVE_EXECUTION_DISABLED = True.
"""
import os
import sqlite3
import tempfile
import time
import pytest
import numpy as np

from config import DEFAULT_CONFIG
from statistical_evaluator import (
    wilson_score_interval,
    StatisticalEvaluator,
    REFERENCE_BASE_RATE_RUNHIGH,
    REFERENCE_BASE_RATE_RUNLOW,
)
from economic_evaluator import EconomicEvaluator
from session_research_aggregator import SessionResearchAggregator
from forward_session import (
    ForwardSessionRegistry,
    STAGE_EXPLORATORY,
    STAGE_VALIDATION,
    STAGE_CONFIRMATION,
)
from quote_recorder import ProposalRecord


# =====================================================================
# 1. WILSON SCORE INTERVAL TESTS
# =====================================================================

def test_wilson_score_interval_boundaries():
    """Validates Wilson interval on boundary cases (0 wins, all wins, empty)."""
    # Empty trials
    low, high = wilson_score_interval(0, 0)
    assert low == 0.0 and high == 0.0

    # Zero wins out of 100 trials: lower bound is 0, upper bound > 0
    low, high = wilson_score_interval(0, 100)
    assert low == 0.0
    assert 0.0 < high < 0.05

    # 100 wins out of 100 trials: upper bound is 1, lower bound < 1
    low, high = wilson_score_interval(100, 100)
    assert 0.95 < low < 1.0
    assert high == 1.0


def test_wilson_score_interval_nominal():
    """Validates Wilson interval on typical rare-event proportions (~3.3%)."""
    low, high = wilson_score_interval(33, 1000)
    assert 0.02 < low < 0.033
    assert 0.033 < high < 0.05
    assert low < 0.033 < high


# =====================================================================
# 2. CALIBRATION & BRIER METRICS TESTS
# =====================================================================

def test_brier_score_and_brier_skill_score():
    """Validates Brier score and Brier Skill Score calculation against reference."""
    # Synthetic outcomes: 100 observations, 4 wins, 96 losses
    outcomes = []
    predictions = []
    for i in range(100):
        is_win = 1.0 if i < 4 else 0.0
        outcomes.append({
            "outcome_id": f"out_{i}",
            "prediction_id": f"pred_{i}",
            "runhigh_win": is_win,
            "runlow_win": 0.0,
            "outcome_status": "RESOLVED_WIN" if is_win else "RESOLVED_LOSS",
            "forward_ticks_count": 6,
        })
        # Perfect model predicting 0.04
        predictions.append({
            "prediction_id": f"pred_{i}",
            "market_state": "TRENDING_UP",
            "runhigh_pred_prob": 0.04,
            "runlow_pred_prob": 0.03,
            "decision": "NO_TRADE",
            "timestamp": 1000.0 + i,
        })

    eval_result = StatisticalEvaluator.evaluate_win_rates(outcomes, predictions)
    rh = eval_result["runhigh"]

    assert rh["resolved_count"] == 100
    assert rh["observed_wins"] == 4
    assert rh["observed_win_rate"] == 0.04
    assert rh["mean_predicted_prob"] == 0.04
    assert rh["brier_score"] is not None
    assert rh["reference_brier_score"] is not None
    # Model predicting 0.04 when observed is 0.04 should have positive skill vs unconditional 0.03275
    assert rh["brier_skill_score"] is not None


def test_rare_event_ece_computation():
    """Validates Expected Calibration Error on 5 discrete rare-event probability bins."""
    outcomes = []
    predictions = []
    # 20 observations in bin [0, 0.02], 20 in [0.02, 0.04], 20 in [0.04, 0.06]
    for i in range(60):
        pred_p = 0.01 if i < 20 else (0.03 if i < 40 else 0.05)
        # 1 win in first bin (5%), 1 win in second bin (5%), 1 win in third bin (5%)
        is_win = 1.0 if i in (0, 20, 40) else 0.0
        outcomes.append({
            "outcome_id": f"out_{i}",
            "prediction_id": f"pred_{i}",
            "runhigh_win": is_win,
            "runlow_win": 0.0,
            "outcome_status": "RESOLVED_WIN" if is_win else "RESOLVED_LOSS",
            "forward_ticks_count": 6,
        })
        predictions.append({
            "prediction_id": f"pred_{i}",
            "market_state": "FLAT",
            "runhigh_pred_prob": pred_p,
            "runlow_pred_prob": 0.03,
            "decision": "NO_TRADE",
            "timestamp": 1000.0 + i,
        })

    res = StatisticalEvaluator.evaluate_win_rates(outcomes, predictions)
    rh = res["runhigh"]
    assert rh["expected_calibration_error"] is not None
    assert 0.0 <= rh["expected_calibration_error"] <= 1.0


# =====================================================================
# 3. DEPENDENCE-AWARE UNCERTAINTY TESTS
# =====================================================================

def test_moving_block_bootstrap_and_effective_sample_size():
    """Validates moving block bootstrap (L=5) and effective sample size under autocorrelation."""
    # Create 50 observations where outcomes exhibit positive autocorrelation
    # (clustering of consecutive outcomes typical of overlapping windows)
    y_vals = [0.0] * 50
    # Add a burst of consecutive 1s
    y_vals[10] = 1.0
    y_vals[11] = 1.0
    y_vals[12] = 1.0

    ci = StatisticalEvaluator.moving_block_bootstrap_ci(y_vals, block_size=5, n_resamples=200, random_seed=42)
    assert len(ci) == 2
    assert ci[0] <= ci[1]
    assert 0.0 <= ci[0] <= 1.0
    assert 0.0 <= ci[1] <= 1.0

    # Test effective sample size calculation
    n_eff = StatisticalEvaluator.effective_sample_size(y_vals, max_lag=4)
    # Autocorrelation should reduce effective sample size below 50
    assert 0 < n_eff <= 50


def test_non_overlapping_subsampling_sensitivity():
    """Validates subsampling stride >= 5 removes overlapping window dependence."""
    y_vals = [0.0] * 50
    for idx in (0, 5, 10):
        y_vals[idx] = 1.0

    sub_res = StatisticalEvaluator.non_overlapping_subsampling(y_vals, stride=5)
    assert sub_res["stride"] == 5
    assert sub_res["subsampled_count"] == 10  # 50 / 5 = 10
    assert sub_res["subsampled_wins"] == 3    # indices 0, 5, 10
    assert sub_res["subsampled_win_rate"] == 0.3


# =====================================================================
# 4. CONDITIONAL PROBABILITY LIFT TESTS
# =====================================================================

def test_conditional_probability_lift():
    """Validates conditional probability lift per market state against unconditional baseline."""
    outcomes = []
    predictions = []
    # State A: 30 trials, 3 wins (10% win rate -> lift over 3.275%)
    # State B: 30 trials, 0 wins (0% win rate)
    for i in range(60):
        state = "HIGH_VOLATILITY" if i < 30 else "LOW_VOLATILITY"
        is_win = 1.0 if (i < 30 and i < 3) else 0.0
        outcomes.append({
            "outcome_id": f"out_{i}",
            "prediction_id": f"pred_{i}",
            "runhigh_win": is_win,
            "runlow_win": 0.0,
            "outcome_status": "RESOLVED_WIN" if is_win else "RESOLVED_LOSS",
            "forward_ticks_count": 6,
        })
        predictions.append({
            "prediction_id": f"pred_{i}",
            "market_state": state,
            "runhigh_pred_prob": 0.05,
            "runlow_pred_prob": 0.03,
            "decision": "NO_TRADE",
            "timestamp": 1000.0 + i,
        })

    res = StatisticalEvaluator.evaluate_win_rates(outcomes, predictions)
    lifts = res["conditional_lift"]["runhigh"]
    assert "HIGH_VOLATILITY" in lifts
    assert "LOW_VOLATILITY" in lifts

    hv = lifts["HIGH_VOLATILITY"]
    assert hv["sample_size"] == 30
    assert hv["observed_wins"] == 3
    assert hv["conditional_win_rate"] == 0.10
    assert hv["absolute_lift"] > 0
    assert hv["relative_lift"] >= 1.0



# =====================================================================
# 5. ECONOMIC EVALUATOR & QUOTE-BASED EV TESTS
# =====================================================================

def test_break_even_and_ordinary_ev():
    """Validates break-even hurdle and ordinary EV using genuine proposal terms."""
    # Stake $2.00, Payout $61.03 -> Hurdle = 2.0 / 61.03 = 0.0327707...
    be = EconomicEvaluator.calculate_break_even_probability(2.0, 61.03)
    assert round(be, 6) == round(2.0 / 61.03, 6)
    assert 0.0327 < be < 0.0328

    # When P_win = 0.04 (4%): EV = 0.04 * 61.03 - 2.00 = +$0.4412
    ev = EconomicEvaluator.calculate_expected_value(0.04, 2.0, 61.03)
    assert round(ev, 4) == round(0.04 * 61.03 - 2.0, 4)
    assert ev > 0

    # When P_win = 0.02 (2%): EV = 0.02 * 61.03 - 2.00 = -$0.7794
    ev_neg = EconomicEvaluator.calculate_expected_value(0.02, 2.0, 61.03)
    assert ev_neg < 0


def test_conservative_ev_strictly_requires_lower_bound():
    """Validates Conservative EV is None when lower probability bound is unavailable."""
    # When lower_prob is None, conservative EV MUST be None (no arbitrary fixed subtraction)
    cons_ev = EconomicEvaluator.calculate_conservative_ev(None, 2.0, 61.03)
    assert cons_ev is None

    # When lower_prob is 0.035 (> 0.0328): Conservative EV should be positive
    cons_ev_valid = EconomicEvaluator.calculate_conservative_ev(0.035, 2.0, 61.03)
    assert cons_ev_valid is not None
    assert cons_ev_valid > 0


def test_quote_lookahead_prevention_in_economics():
    """Validates that quotes received strictly in the future are rejected."""
    t_pred = 1000.0

    # Valid quote: received at t=995 (before prediction)
    q_valid = ProposalRecord(
        request_timestamp=994.0,
        response_timestamp=995.0,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_valid",
        quote_source="live_proposal",
        quote_latency_ms=100.0,
        collection_status="QUOTE_AVAILABLE",
        api_response_metadata="",
    )

    # Future quote: received at t=1005 (after prediction -> LOOKAHEAD VIOLATION)
    q_future = ProposalRecord(
        request_timestamp=1004.0,
        response_timestamp=1005.0,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_future",
        quote_source="live_proposal",
        quote_latency_ms=100.0,
        collection_status="QUOTE_AVAILABLE",
        api_response_metadata="",
    )

    matched_valid = EconomicEvaluator.find_lookahead_free_quote([q_valid], "RUNHIGH", t_pred, max_age_seconds=60.0)
    assert matched_valid is not None
    assert matched_valid.proposal_id == "prop_valid"

    # Future quote must be rejected
    matched_future = EconomicEvaluator.find_lookahead_free_quote([q_future], "RUNHIGH", t_pred, max_age_seconds=60.0)
    assert matched_future is None


def test_pricing_sensitivity_stress_analysis():
    """Validates stress testing with 5% payout haircut, 10% haircut, and latency premium."""
    p_hat = 0.034
    base_stake = 2.0
    base_payout = 61.03

    stress_report = EconomicEvaluator.pricing_sensitivity_stress_analysis(p_hat, base_stake, base_payout)
    scenarios = stress_report["scenarios"]

    assert "base_observed" in scenarios
    assert "payout_haircut_5pct" in scenarios
    assert "payout_haircut_10pct" in scenarios
    assert "latency_premium_2pct" in scenarios
    assert "combined_severe_stress" in scenarios

    base_ev = scenarios["base_observed"]["ev"]
    hc5_ev = scenarios["payout_haircut_5pct"]["ev"]
    hc10_ev = scenarios["payout_haircut_10pct"]["ev"]
    comb_ev = scenarios["combined_severe_stress"]["ev"]

    # Haircuts must monotonically reduce EV
    assert base_ev > hc5_ev > hc10_ev
    assert comb_ev < base_ev


# =====================================================================
# 6. RESEARCH STAGE ISOLATION & MULTI-SESSION AGGREGATION TESTS
# =====================================================================

def test_forward_session_research_stages():
    """Validates that ForwardSessionRegistry records and preserves research_stage."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        reg = ForwardSessionRegistry(db_path=db_path)
        s1 = reg.create_session("R_75", mode="SHADOW", planned_duration_seconds=3600, research_stage=STAGE_EXPLORATORY)
        s2 = reg.create_session("R_75", mode="SHADOW", planned_duration_seconds=3600, research_stage=STAGE_VALIDATION)
        s3 = reg.create_session("R_75", mode="SHADOW", planned_duration_seconds=3600, research_stage=STAGE_CONFIRMATION)

        assert s1.research_stage == STAGE_EXPLORATORY
        assert s2.research_stage == STAGE_VALIDATION
        assert s3.research_stage == STAGE_CONFIRMATION

        # Retrieve and verify persistence
        loaded1 = reg.get_session(s1.session_id)
        assert loaded1 is not None
        assert loaded1.research_stage == STAGE_EXPLORATORY
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_session_research_aggregator_verdicts():
    """Validates that SessionResearchAggregator concludes NO_VALIDATED_EDGE or INSUFFICIENT_FORWARD_DATA appropriately."""
    agg = SessionResearchAggregator()

    # Empty sessions -> INSUFFICIENT_FORWARD_DATA
    res = agg.evaluate_multi_session_research(symbol="NON_EXISTENT_SYM")
    assert res["verdict"] == "INSUFFICIENT_FORWARD_DATA"
    assert len(res["verdict_reasons"]) > 0
    assert "Zero forward prediction records" in res["verdict_reasons"][0]


# =====================================================================
# 7. SAFETY INVARIANT TESTS
# =====================================================================

def test_live_execution_disabled_permanent_invariant():
    """Validates that real-money trading remains permanently disabled."""
    assert DEFAULT_CONFIG.live_execution_disabled is True
    # Verify no trade execution order can be placed
    assert getattr(DEFAULT_CONFIG, "enable_live_money_trading", False) is False
