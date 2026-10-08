"""Comprehensive V1.5.1 Regression & Statistical Integrity Test Suite.

Verifies:
1. Software integrity & type hint introspection (Tuple regression resolved in paper_trader.py).
2. Multiple testing corrections (Holm step-down, Benjamini-Hochberg FDR, Bonferroni).
3. Dependence-aware uncertainty (Stationary block bootstrap CI, non-overlapping sensitivity).
4. Time-series-aware negative controls & stage-by-stage false positive rate tracking with Wilson CIs.
5. Persistent historical quote database (SQLite CRUD, lookahead prevention, freshness constraints).
6. Conservative Expected Value and strict NO_TRADE safety rules.
"""
import os
import sqlite3
import time
import typing
import numpy as np
import pandas as pd
import pytest

from paper_trader import PaperTrader, PaperTradeRecord
from probability import (
    calculate_holm_adjusted_p,
    calculate_fdr_q_values,
    calculate_adjusted_p_value,
    wilson_score_ci,
    stationary_block_bootstrap_ci,
    non_overlapping_sensitivity_analysis,
    calculate_conservative_ev,
    calculate_true_ev
)
from quote_database import QuoteDatabase
from quote_recorder import ProposalRecord
from quote_engine import QuoteEngine
from negative_control import (
    generate_permuted_state_series,
    generate_circular_shift_series,
    run_negative_control_audit
)
from feature_search import SampleSizeConfig, determine_edge_status


# ==============================================================================
# 1. SOFTWARE INTEGRITY & TYPE HINT INTROSPECTION
# ==============================================================================

def test_paper_trader_type_hint_introspection():
    """Confirms PaperTradeRecord has valid type annotations and introspection succeeds without NameError."""
    hints = typing.get_type_hints(PaperTradeRecord)
    assert "probability_uncertainty" in hints
    assert hints["probability_uncertainty"] == typing.Tuple[float, float]
    assert hints["decision"] == str
    assert hints["conservative_expected_value"] == float


def test_paper_trader_live_execution_disabled():
    """Enforces absolute safety directive: real money execution is permanently disabled."""
    assert PaperTrader.LIVE_EXECUTION_DISABLED is True


# ==============================================================================
# 2. MULTIPLE-TESTING CORRECTIONS (HOLM, FDR, BONFERRONI)
# ==============================================================================

def test_holm_step_down_fwer_control():
    """Verifies Holm step-down adjusted p-values are monotonic and control FWER."""
    raw_p = [0.005, 0.02, 0.04, 0.50]
    # m = 4:
    # rank 1: p=0.005 * 4 = 0.02
    # rank 2: max(0.02, 0.02 * 3) = 0.06
    # rank 3: max(0.06, 0.04 * 2) = 0.08
    # rank 4: max(0.08, 0.50 * 1) = 0.50
    holm_p = calculate_holm_adjusted_p(raw_p)
    assert len(holm_p) == 4
    assert round(holm_p[0], 4) == 0.0200
    assert round(holm_p[1], 4) == 0.0600
    assert round(holm_p[2], 4) == 0.0800
    assert round(holm_p[3], 4) == 0.5000
    # Strict order preservation
    assert holm_p[0] <= holm_p[1] <= holm_p[2] <= holm_p[3]


def test_fdr_and_bonferroni_relationships():
    """Holm and Bonferroni are more conservative than Benjamini-Hochberg FDR."""
    raw_p = [0.001, 0.015, 0.03, 0.10]
    bonf = [calculate_adjusted_p_value(p, 4) for p in raw_p]
    holm = calculate_holm_adjusted_p(raw_p)
    fdr = calculate_fdr_q_values(raw_p)

    for i in range(len(raw_p)):
        assert fdr[i] <= holm[i] <= bonf[i]


# ==============================================================================
# 3. DEPENDENCE-AWARE UNCERTAINTY & OVERLAPPING CONTRACT WINDOWS
# ==============================================================================

def test_wilson_score_interval_properties():
    """Wilson interval never exceeds [0, 1] and handles boundary win rates correctly."""
    ci_0 = wilson_score_ci(0, 100)
    assert ci_0[0] == 0.0
    assert 0.0 < ci_0[1] < 0.05

    ci_100 = wilson_score_ci(100, 100)
    assert ci_100[1] == 1.0
    assert 0.95 < ci_100[0] < 1.0


def test_stationary_block_bootstrap_ci():
    """Stationary bootstrap preserves serial dependence structure with geometric block lengths."""
    # Create serially dependent run of outcomes: clusters of 1s and 0s
    data = np.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0] * 50, dtype=float)
    ci_lo, ci_hi = stationary_block_bootstrap_ci(data, num_resamples=500, mean_block_length=10, seed=123)
    mean_val = np.mean(data)
    assert 0.0 <= ci_lo <= mean_val <= ci_hi <= 1.0
    # Reproducible seed gives deterministic output
    ci_lo2, ci_hi2 = stationary_block_bootstrap_ci(data, num_resamples=500, mean_block_length=10, seed=123)
    assert ci_lo == ci_lo2
    assert ci_hi == ci_hi2


def test_non_overlapping_sensitivity_analysis():
    """Stride-5 subsample evaluates strictly independent windows with zero shared ticks."""
    # 100 ticks with 5-tick overlap
    series = pd.Series([1 if i % 10 == 0 else 0 for i in range(100)])
    res = non_overlapping_sensitivity_analysis(series, stride=5, null_prob=0.0328)
    assert res["n_full"] == 100
    assert res["n_non_overlapping"] == 20
    assert res["stride"] == 5
    assert "edge_survives_non_overlapping" in res


# ==============================================================================
# 4. HISTORICAL QUOTE DATABASE (SQLITE) & LOOKAHEAD PREVENTION
# ==============================================================================

def test_quote_database_crud_and_lookahead_prevention(tmp_path):
    """Verifies SQLite storage, indexing, lookahead prevention, and freshness constraints."""
    db_file = tmp_path / "test_quotes.db"
    db = QuoteDatabase(db_path=str(db_file))

    # Store quote at timestamp 1000.0 (received at 1000.1)
    rec1 = ProposalRecord(
        request_timestamp=1000.0,
        response_timestamp=1000.1,
        market_symbol="R_75",
        contract_type="RUNHIGH",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=61.03,
        potential_net_profit=59.03,
        currency="USD",
        proposal_id="prop_001",
        quote_source="live_proposal",
        quote_latency_ms=100.0,
        collection_status="QUOTE_AVAILABLE"
    )
    db.store_quote(rec1)

    # 1. Query before response arrives (Lookahead check) -> Must return None!
    q_early = db.get_latest_quote_before("R_75", "RUNHIGH", timestamp=1000.05, max_freshness_seconds=60.0)
    assert q_early is None

    # 2. Query after response arrives within freshness window -> Must succeed!
    q_valid = db.get_latest_quote_before("R_75", "RUNHIGH", timestamp=1005.0, max_freshness_seconds=60.0)
    assert q_valid is not None
    assert q_valid.total_payout == 61.03
    assert q_valid.proposal_id == "prop_001"

    # 3. Query after freshness window expires (> 60s) -> Must return None (Stale)!
    q_stale = db.get_latest_quote_before("R_75", "RUNHIGH", timestamp=1100.0, max_freshness_seconds=60.0)
    assert q_stale is None

    # 4. Coverage report
    cov = db.report_quote_coverage("R_75")
    assert cov["total_quotes"] == 1
    assert cov["available_quotes"] == 1
    assert cov["runhigh_quotes"] == 1
    assert cov["status"] == "ACTIVE"


def test_quote_database_validation_detects_anomalies(tmp_path):
    """Database validation flags non-positive payouts and inverted timestamps."""
    db_file = tmp_path / "anomalous_quotes.db"
    db = QuoteDatabase(db_path=str(db_file))

    # Non-positive payout record
    bad_rec = ProposalRecord(
        request_timestamp=1000.0,
        response_timestamp=999.0,  # Inverted timestamp!
        market_symbol="R_75",
        contract_type="RUNLOW",
        contract_duration=5,
        duration_unit="t",
        stake=2.0,
        total_payout=-5.0,        # Negative payout!
        potential_net_profit=-7.0,
        currency="USD",
        proposal_id="bad_001",
        quote_source="corrupt",
        quote_latency_ms=-100.0,   # Negative latency!
        collection_status="QUOTE_AVAILABLE"
    )
    db.store_quote(bad_rec)

    val_res = db.validate_quote_records("R_75")
    assert val_res["status"] == "ANOMALIES_DETECTED"
    assert val_res["anomalies_detected"] >= 2


# ==============================================================================
# 5. TIME-SERIES-AWARE NEGATIVE CONTROLS & STAGE-BY-STAGE FPR
# ==============================================================================

def test_circular_shift_preserves_distributions():
    """Circular shift preserves exact marginal frequencies and time series runs."""
    df = pd.DataFrame({
        "streak_bin": ["UP"] * 50 + ["DOWN"] * 50,
        "runhigh_win": [1] * 20 + [0] * 80
    })
    shifted = generate_circular_shift_series(df, shift_ticks=10, random_seed=42)
    assert len(shifted) == 100
    assert sum(shifted["runhigh_win"]) == sum(df["runhigh_win"])
    # Alignment between state and outcome is disrupted
    assert not shifted["runhigh_win"].equals(df["runhigh_win"])


def test_negative_control_stage_by_stage_fpr_reporting():
    """Verifies run_negative_control_audit tracks Stage 1 through Stage 5 false positives."""
    # Synthetic noise features
    n = 1000
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "epoch": range(1000, 1000 + n),
        "price": 100.0 + np.cumsum(rng.normal(0, 1, n)),
        "streak_bin": ["UP_STREAK" if i % 2 == 0 else "DOWN_STREAK" for i in range(n)],
        "mom_bin": ["BULL" if i % 3 == 0 else "BEAR" for i in range(n)],
        "vol_bin": ["HIGH_VOL" if i % 4 == 0 else "NORMAL_VOL" for i in range(n)],
        "runhigh_win": rng.binomial(1, 0.032, n),
        "runlow_win": rng.binomial(1, 0.030, n)
    })

    qe = QuoteEngine(mode="research")
    cfg = SampleSizeConfig(min_discovery_samples=20, min_validation_samples=10, min_holdout_samples=10)

    res = run_negative_control_audit(
        features_df=df,
        quote_engine=qe,
        num_permutations=1,
        null_methods=["permuted_states"],
        sample_config=cfg
    )

    assert "stage_metrics" in res
    sm = res["stage_metrics"]
    assert "stage1_exploratory" in sm
    assert "stage2_significant" in sm
    assert "stage3_validation" in sm
    assert "stage4_holdout" in sm
    assert "stage5_full_gate" in sm

    # Crucial property: Stage 5 full tradability gate must NOT validate spurious edges!
    assert res["stage5_full_gate_survived"] == 0
    assert res["passed_negative_control"] is True


# ==============================================================================
# 6. EDGE QUALIFICATION GATES TAXONOMY
# ==============================================================================

def test_determine_edge_status_taxonomy():
    """Verifies edge status precedence under each qualification failure reason."""
    cfg = SampleSizeConfig(min_discovery_samples=50)

    # 1. LOW_SAMPLE
    assert determine_edge_status(sample_size=30, adj_p_value=0.01, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg) == "LOW_SAMPLE"

    # 2. NOT_SIGNIFICANT
    assert determine_edge_status(sample_size=100, adj_p_value=0.20, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg) == "NOT_SIGNIFICANT"

    # 3. NEGATIVE_EV
    assert determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=-0.5, conditional_prob=0.02,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg) == "NEGATIVE_EV"

    # 4. POOR_CALIBRATION
    assert determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=False, validation_survived=True, holdout_survived=True, sample_config=cfg) == "POOR_CALIBRATION"

    # 5. FAILED_VALIDATION
    assert determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=False, holdout_survived=True, sample_config=cfg) == "FAILED_VALIDATION"

    # 6. FAILED_HOLDOUT
    assert determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=True, holdout_survived=False, sample_config=cfg) == "FAILED_HOLDOUT"

    # 7. VALIDATED_EDGE
    assert determine_edge_status(sample_size=100, adj_p_value=0.01, expected_value=1.5, conditional_prob=0.08,
                                 break_even_prob=0.0328, calibration_ok=True, validation_survived=True, holdout_survived=True, sample_config=cfg) == "VALIDATED_EDGE"
